"""
object_tracker.py – Stability-hardened multi-frame object tracker (v3).

Edge-side tracker for Git Blame for Reality running on NVIDIA Jetson
Orin Nano Super.  Accepts YOLO detections in native xyxy format and
produces semantic "commit" events only when meaningful changes occur.

=== v3 Stability Upgrades ===

1. Temporary Detection Drop
   YOLO may fail to detect an object for a frame or two.  Instead of
   immediately logging ``object_disappeared``, we maintain an explicit
   ``missing_frame_count`` per object and only fire the event after a
   configurable number of consecutive misses (default 5).  If the object
   reappears before the threshold, the counter resets and the ID is kept.

2. Label Drift (Laptop ↔ Keyboard Problem)
   YOLO may flip an object's class across frames.  Matching now uses a
   two-pass strategy:
     Pass 1 — same-label, standard spatial thresholds
     Pass 2 — any-label, stricter spatial threshold (IoU >= 0.5)
   Each object stores a ``label_history`` and a ``canonical_label``
   (majority vote).  Events always report the stable canonical label.

3. Occlusion Handling
   If a tracked object goes missing but a *different* detection in the
   current frame overlaps its last bbox by IoU > 0.5, we assume the
   object is temporarily occluded (not gone).  The missing counter is
   NOT incremented during occlusion.

=== Carried Forward from v2 ===
- Multi-frame motion accumulation with anchor reset
- Dual matching (IoU OR center distance)
- YOLO-native xyxy input → internal xywh
- Pure Python, zero dependencies, fully in-memory

Bounding-box formats:
    xyxy : [x1, y1, x2, y2]   — input  (YOLO native)
    xywh : [x, y, w, h]       — internal storage
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union


# =====================================================================
# Inline geometry helpers (zero imports, zero dependencies)
# =====================================================================

def xyxy_to_xywh(xyxy: List[float]) -> List[float]:
    """Convert [x1, y1, x2, y2] → [x, y, width, height]."""
    x1, y1, x2, y2 = xyxy
    return [x1, y1, x2 - x1, y2 - y1]


def xywh_to_xyxy(xywh: List[float]) -> List[float]:
    """Convert [x, y, width, height] → [x1, y1, x2, y2]."""
    x, y, w, h = xywh
    return [x, y, x + w, y + h]


def xywh_center(xywh: List[float]) -> Tuple[float, float]:
    """Return (cx, cy) centre of a bounding box in xywh format."""
    x, y, w, h = xywh
    return (x + w / 2.0, y + h / 2.0)


def euclidean_distance(
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    """Euclidean distance between two 2-D points."""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def compute_iou_xywh(a: List[float], b: List[float]) -> float:
    """
    Intersection-over-Union for two boxes in [x, y, w, h] format.
    Returns float in [0.0, 1.0].
    """
    ax1, ay1 = a[0], a[1]
    ax2, ay2 = ax1 + a[2], ay1 + a[3]
    bx1, by1 = b[0], b[1]
    bx2, by2 = bx1 + b[2], by1 + b[3]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, a[2]) * max(0.0, a[3])
    area_b = max(0.0, b[2]) * max(0.0, b[3])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def _majority_vote(labels: List[str]) -> str:
    """Return the most frequent label in *labels* (ties: last seen wins)."""
    counts: Dict[str, int] = {}
    for lbl in labels:
        counts[lbl] = counts.get(lbl, 0) + 1
    best_label = labels[-1]
    best_count = 0
    for lbl, cnt in counts.items():
        if cnt > best_count:
            best_count = cnt
            best_label = lbl
    return best_label


# =====================================================================
# ObjectTracker
# =====================================================================

# Maximum label history entries to keep per object (bounded memory).
_MAX_LABEL_HISTORY = 30


class ObjectTracker:
    """
    Stateful multi-frame object tracker with motion accumulation
    and stability upgrades for detection drops, label drift, and
    occlusion.

    Parameters
    ----------
    iou_threshold : float
        Min IoU for same-label matching (default 0.3).
    center_dist_threshold : float
        Max centre distance (px) for same-label matching (default 80.0).
    motion_threshold : float
        Accumulated displacement (px) before ``object_moved`` fires
        (default 10.0).
    max_missing_frames : int
        Consecutive frames an object can be absent before
        ``object_disappeared`` fires (default 5).
    label_drift_iou : float
        Min IoU for cross-label matching during pass 2 (default 0.5).
        Must be higher than *iou_threshold* to prevent false merges.
    occlusion_iou : float
        If a missing object's last bbox overlaps a current detection
        by at least this IoU, assume occlusion (default 0.5).
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        center_dist_threshold: float = 80.0,
        motion_threshold: float = 10.0,
        max_missing_frames: int = 5,
        label_drift_iou: float = 0.5,
        occlusion_iou: float = 0.5,
    ) -> None:
        # ---- state ----
        self.objects: Dict[int, Dict[str, Any]] = {}
        self.next_id: int = 0

        # ---- configuration ----
        self.iou_threshold = iou_threshold
        self.center_dist_threshold = center_dist_threshold
        self.motion_threshold = motion_threshold
        self.max_missing_frames = max_missing_frames
        self.label_drift_iou = label_drift_iou
        self.occlusion_iou = occlusion_iou

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _allocate_id(self) -> int:
        oid = self.next_id
        self.next_id += 1
        return oid

    @staticmethod
    def _new_tracked_object(
        object_id: int,
        label: str,
        confidence: float,
        bbox_xywh: List[float],
        frame_index: int,
        timestamp: Union[str, float],
    ) -> Dict[str, Any]:
        """Create the internal dict for a newly appeared object."""
        return {
            "object_id": object_id,
            "label_history": [label],
            "canonical_label": label,
            "confidence": confidence,
            "current_bbox_xywh": list(bbox_xywh),
            "anchor_bbox_xywh": list(bbox_xywh),
            "accumulated_motion_px": 0.0,
            "last_seen_frame_index": frame_index,
            "last_seen_timestamp": timestamp,
            "missing_frame_count": 0,
        }

    # ---- matching helpers ---------------------------------------------

    def _find_best_match_same_label(
        self,
        label: str,
        bbox_xywh: List[float],
        already_matched: set,
    ) -> Optional[int]:
        """
        Pass 1: find the best stored object with the **same canonical
        label** using standard thresholds (IoU OR center distance).
        """
        best_id: Optional[int] = None
        best_score: float = -1.0
        det_center = xywh_center(bbox_xywh)

        for obj_id, obj in self.objects.items():
            if obj_id in already_matched:
                continue
            if obj["canonical_label"] != label:
                continue

            iou = compute_iou_xywh(obj["current_bbox_xywh"], bbox_xywh)
            obj_center = xywh_center(obj["current_bbox_xywh"])
            dist = euclidean_distance(det_center, obj_center)

            if iou >= self.iou_threshold or dist <= self.center_dist_threshold:
                score = iou * 1000.0 + (1.0 / (1.0 + dist))
                if score > best_score:
                    best_id = obj_id
                    best_score = score

        return best_id

    def _find_best_match_cross_label(
        self,
        bbox_xywh: List[float],
        already_matched: set,
    ) -> Optional[int]:
        """
        Pass 2 (label drift): find the best stored object with **any
        label** but require a stricter spatial criterion
        (IoU >= label_drift_iou).  This catches YOLO flipping between
        e.g. "laptop" and "keyboard" for the same physical object.
        """
        best_id: Optional[int] = None
        best_iou: float = 0.0

        for obj_id, obj in self.objects.items():
            if obj_id in already_matched:
                continue

            iou = compute_iou_xywh(obj["current_bbox_xywh"], bbox_xywh)

            if iou >= self.label_drift_iou and iou > best_iou:
                best_id = obj_id
                best_iou = iou

        return best_id

    # ---- occlusion helper ---------------------------------------------

    def _is_occluded(
        self,
        obj: Dict[str, Any],
        current_det_xywh_list: List[List[float]],
    ) -> bool:
        """
        Heuristic: if any current-frame detection *covers* a large
        fraction of the missing object's last bbox, assume occlusion.

        Uses **coverage ratio** (intersection / missing_object_area)
        instead of IoU.  This correctly handles cases where the
        occluding object is much larger than the occluded one
        (e.g., a person walking in front of a laptop — IoU would be
        low because the person is big, but coverage would be high
        because the laptop is fully inside the person's box).
        """
        obj_bbox = obj["current_bbox_xywh"]
        obj_area = max(0.0, obj_bbox[2]) * max(0.0, obj_bbox[3])
        if obj_area <= 0:
            return False

        for det_xywh in current_det_xywh_list:
            # Compute intersection area
            ax1, ay1 = obj_bbox[0], obj_bbox[1]
            ax2, ay2 = ax1 + obj_bbox[2], ay1 + obj_bbox[3]
            bx1, by1 = det_xywh[0], det_xywh[1]
            bx2, by2 = bx1 + det_xywh[2], by1 + det_xywh[3]

            inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
            inter_area = inter_w * inter_h

            coverage = inter_area / obj_area
            if coverage >= self.occlusion_iou:
                return True

        return False

    # ---- label management ---------------------------------------------

    @staticmethod
    def _update_label_history(
        obj: Dict[str, Any],
        new_label: str,
    ) -> None:
        """Append *new_label*, cap history, recompute canonical label."""
        history = obj["label_history"]
        history.append(new_label)
        # Trim to keep memory bounded
        if len(history) > _MAX_LABEL_HISTORY:
            obj["label_history"] = history[-_MAX_LABEL_HISTORY:]
        obj["canonical_label"] = _majority_vote(obj["label_history"])

    # -----------------------------------------------------------------
    # Core match-and-update (shared by both passes)
    # -----------------------------------------------------------------

    def _apply_match(
        self,
        match_id: int,
        label: str,
        confidence: float,
        bbox_xywh: List[float],
        frame_index: int,
        timestamp: Union[str, float],
        events: List[Dict[str, Any]],
    ) -> None:
        """
        Update a matched object's state, accumulate motion, and
        optionally emit an ``object_moved`` event.
        """
        obj = self.objects[match_id]

        # ---- motion accumulation ----
        prev_center = xywh_center(obj["current_bbox_xywh"])
        curr_center = xywh_center(bbox_xywh)
        displacement = euclidean_distance(prev_center, curr_center)

        obj["accumulated_motion_px"] += displacement
        obj["current_bbox_xywh"] = list(bbox_xywh)
        obj["confidence"] = confidence
        obj["last_seen_frame_index"] = frame_index
        obj["last_seen_timestamp"] = timestamp
        obj["missing_frame_count"] = 0          # seen → reset counter

        # ---- label bookkeeping ----
        self._update_label_history(obj, label)

        # ---- motion event ----
        if obj["accumulated_motion_px"] >= self.motion_threshold:
            events.append({
                "event": "object_moved",
                "object_id": match_id,
                "label": obj["canonical_label"],
                "from_bbox_xywh": obj["anchor_bbox_xywh"],
                "to_bbox_xywh": list(bbox_xywh),
                "accumulated_motion_px": round(
                    obj["accumulated_motion_px"], 2,
                ),
                "confidence": confidence,
                "timestamp": timestamp,
                "frame_index": frame_index,
            })
            obj["anchor_bbox_xywh"] = list(bbox_xywh)
            obj["accumulated_motion_px"] = 0.0

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def process_frame(
        self,
        detections: List[Dict[str, Any]],
        frame_index: int,
        timestamp: Union[str, float],
    ) -> List[Dict[str, Any]]:
        """
        Process one frame of YOLO detections.

        Parameters
        ----------
        detections : list of dict
            Each dict::

                {
                    "label":      str,
                    "confidence": float,
                    "bbox_xyxy":  [x1, y1, x2, y2]
                }

        frame_index : int
            Monotonically increasing frame counter.
        timestamp : str or float
            ISO-8601 string or UNIX epoch.

        Returns
        -------
        list of dict
            Structured events.  Empty if nothing meaningful changed.
        """
        events: List[Dict[str, Any]] = []
        matched_obj_ids: set = set()
        matched_det_indices: set = set()

        # Pre-convert all detections xyxy → xywh
        converted: List[Dict[str, Any]] = []
        for det in detections:
            converted.append({
                "label": det["label"],
                "confidence": det["confidence"],
                "bbox_xywh": xyxy_to_xywh(det["bbox_xyxy"]),
            })

        # ==============================================================
        # Pass 1: Same-label matching (standard thresholds)
        # ==============================================================
        for i, det in enumerate(converted):
            match_id = self._find_best_match_same_label(
                det["label"], det["bbox_xywh"], matched_obj_ids,
            )
            if match_id is not None:
                self._apply_match(
                    match_id, det["label"], det["confidence"],
                    det["bbox_xywh"], frame_index, timestamp, events,
                )
                matched_obj_ids.add(match_id)
                matched_det_indices.add(i)

        # ==============================================================
        # Pass 2: Cross-label matching for label drift (stricter IoU)
        # ==============================================================
        for i, det in enumerate(converted):
            if i in matched_det_indices:
                continue

            match_id = self._find_best_match_cross_label(
                det["bbox_xywh"], matched_obj_ids,
            )
            if match_id is not None:
                self._apply_match(
                    match_id, det["label"], det["confidence"],
                    det["bbox_xywh"], frame_index, timestamp, events,
                )
                matched_obj_ids.add(match_id)
                matched_det_indices.add(i)

        # ==============================================================
        # New objects (unmatched detections after both passes)
        # ==============================================================
        for i, det in enumerate(converted):
            if i in matched_det_indices:
                continue

            new_id = self._allocate_id()
            self.objects[new_id] = self._new_tracked_object(
                new_id, det["label"], det["confidence"],
                det["bbox_xywh"], frame_index, timestamp,
            )
            events.append({
                "event": "object_appeared",
                "object_id": new_id,
                "label": det["label"],
                "bbox_xywh": list(det["bbox_xywh"]),
                "confidence": det["confidence"],
                "timestamp": timestamp,
                "frame_index": frame_index,
            })
            matched_obj_ids.add(new_id)

        # ==============================================================
        # Disappearance with occlusion awareness
        # ==============================================================
        all_det_xywh = [d["bbox_xywh"] for d in converted]
        vanished_ids: List[int] = []

        for obj_id, obj in self.objects.items():
            if obj_id in matched_obj_ids:
                continue  # seen this frame — already handled

            # Not matched this frame — check occlusion
            if self._is_occluded(obj, all_det_xywh):
                # Likely hidden behind another object — don't penalise
                pass
            else:
                obj["missing_frame_count"] += 1

            # Fire disappeared only after enough consecutive misses
            if obj["missing_frame_count"] >= self.max_missing_frames:
                events.append({
                    "event": "object_disappeared",
                    "object_id": obj_id,
                    "label": obj["canonical_label"],
                    "last_bbox_xywh": obj["current_bbox_xywh"],
                    "accumulated_motion_px": round(
                        obj["accumulated_motion_px"], 2,
                    ),
                    "timestamp": timestamp,
                    "frame_index": frame_index,
                })
                vanished_ids.append(obj_id)

        for obj_id in vanished_ids:
            del self.objects[obj_id]

        return events

    # -----------------------------------------------------------------
    # Convenience helpers
    # -----------------------------------------------------------------

    def process_frame_json(
        self,
        detections: List[Dict[str, Any]],
        frame_index: int,
        timestamp: Union[str, float],
        indent: int = 2,
    ) -> str:
        """Same as ``process_frame`` but returns a JSON string."""
        events = self.process_frame(detections, frame_index, timestamp)
        return json.dumps(events, indent=indent)

    def current_state(self) -> Dict[int, Dict[str, Any]]:
        """Return a deep-ish copy of all tracked objects."""
        return {k: dict(v) for k, v in self.objects.items()}

    def reset(self) -> None:
        """Clear all tracked objects and reset the ID counter."""
        self.objects.clear()
        self.next_id = 0
