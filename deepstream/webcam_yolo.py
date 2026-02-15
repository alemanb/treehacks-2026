"""
webcam_yolo.py - DeepStream webcam YOLO detections -> unique object paths.

Runs webcam inference through DeepStream, records an MKV for the tracked
session, and keeps per-object bbox history plus VLM reasoning.
"""

from __future__ import annotations

import argparse
from collections import deque
import configparser
import json
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Set, Tuple

import cv2
import gi
import numpy as np
import pyds

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

from object_tracker import ObjectTracker
from vlm_ollama import OllamaVLM


def _cfg_get(cfg: configparser.ConfigParser, section: str, key: str, fallback=None):
    try:
        return cfg.get(section, key)
    except Exception:
        return fallback


def _cfg_getint(
    cfg: configparser.ConfigParser, section: str, key: str, fallback=None
):
    try:
        return cfg.getint(section, key)
    except Exception:
        return fallback


def _safe_set(el, prop: str, value) -> None:
    try:
        if value is not None:
            el.set_property(prop, value)
    except Exception as exc:
        print(f"WARNING: could not set {el.get_name()}.{prop}={value!r}: {exc}")


class RuntimeState:
    def __init__(
        self,
        tracker: ObjectTracker,
        frames_dir: str,
        filtered_path: str,
        vlm_client: OllamaVLM,
    ):
        self.tracker = tracker
        self.frames_dir = frames_dir
        self.filtered_path = filtered_path
        self.vlm_client = vlm_client
        self.frames_processed = 0
        self.bbox_history_by_id: Dict[int, List[Dict[str, Any]]] = {}
        self.trail_points_by_id: Dict[int, List[Tuple[int, int]]] = {}
        self.trail_segments_by_id: Dict[int, List[Tuple[Tuple[int, int], Tuple[int, int]]]] = {}
        self.disappeared_object_ids: Set[int] = set()
        self.frame_history: Deque[Tuple[int, Any]] = deque(maxlen=8)
        self.id_remap: Dict[int, int] = {}
        self.filtered_objects: Dict[int, Dict[str, Any]] = {}
        self.archived_objects: Dict[int, Dict[str, Any]] = {}
        self.vlm_tasks: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=64)
        self.vlm_results: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.vlm_stop_event = threading.Event()
        self.vlm_workers: List[threading.Thread] = []
        self.vlm_dropped_tasks = 0
        self.active_snapshot: Dict[int, Dict[str, Any]] = {}


def _safe_timestamp_for_filename(timestamp: str) -> str:
    return (
        timestamp.replace(":", "-")
        .replace(".", "_")
        .replace("+", "_plus_")
        .replace("/", "_")
    )


def _save_change_frame(
    frame_bgr,
    frames_dir: str,
    timestamp: str,
    change_kind: str,
    object_id: int,
    frame_index: int,
) -> None:
    try:
        safe_ts = _safe_timestamp_for_filename(timestamp)
        filename = (
            f"{safe_ts}_chg-{change_kind}_id-{object_id}_frame-{frame_index}.jpg"
        )
        cv2.imwrite(os.path.join(frames_dir, filename), frame_bgr)
    except Exception as exc:
        print(f"WARNING: failed to save change frame: {exc}")


def _extract_frame_bgr(gst_buffer, frame_meta):
    try:
        n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
        frame_rgba = np.array(n_frame, copy=True, order="C")
        if frame_rgba.ndim == 3 and frame_rgba.shape[2] == 4:
            return cv2.cvtColor(frame_rgba, cv2.COLOR_RGBA2BGR)
        if frame_rgba.ndim == 3 and frame_rgba.shape[2] == 3:
            return cv2.cvtColor(frame_rgba, cv2.COLOR_RGB2BGR)
    except Exception:
        return None
    return None


def _get_before_frame(state: RuntimeState, frame_index: int):
    target = frame_index - 2
    fallback = None
    for idx, frame_bgr in reversed(state.frame_history):
        if idx == target:
            return frame_bgr
        if idx < frame_index and fallback is None:
            fallback = frame_bgr
    return fallback


def _iou_xywh(a: List[float], b: List[float]) -> float:
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


def _resolve_object_id(state: RuntimeState, object_id: int) -> int:
    resolved = object_id
    seen: Set[int] = set()
    while resolved in state.id_remap and resolved not in seen:
        seen.add(resolved)
        resolved = state.id_remap[resolved]
    return resolved


def _ensure_filtered_object(state: RuntimeState, object_id: int, label: str) -> Dict[str, Any]:
    if object_id not in state.filtered_objects:
        state.filtered_objects[object_id] = {
            "object_id": object_id,
            "label": label,
            "aliases": [object_id],
            "bbox_history": [],
            "move_reason_history": [],
            "non_move_reason_history": [],
            "disappear_checks": [],
            "non_disappear_reason_history": [],
            "reappearance_checks": [],
            "non_reappearance_reason_history": [],
        }
    return state.filtered_objects[object_id]


def _append_filtered_bbox(
    state: RuntimeState,
    object_id: int,
    bbox_xywh: List[float],
    frame_index: int,
    timestamp: str,
    detection_confidence: float,
) -> None:
    obj = state.filtered_objects.get(object_id)
    if obj is None:
        return
    box = [float(v) for v in bbox_xywh]
    history = obj["bbox_history"]
    if history and history[-1]["bbox_xywh"] == box:
        return
    history.append(
        {
            "frame_index": int(frame_index),
            "timestamp": str(timestamp),
            "bbox_xywh": box,
            "confidence": float(detection_confidence),
        }
    )


def _write_filtered_state(state: RuntimeState) -> None:
    def _normalize_object_history(obj: Dict[str, Any]) -> None:
        bbox_history = list(obj.get("bbox_history", []))
        move_reason_history = list(obj.get("move_reason_history", []))
        disappear_checks = list(obj.get("disappear_checks", []))

        # Rule: transitions == len(bbox_history) - 1
        transitions = len(move_reason_history) + len(disappear_checks)
        required_transitions = max(0, len(bbox_history) - 1)

        if transitions > required_transitions:
            overflow = transitions - required_transitions
            while overflow > 0 and disappear_checks:
                disappear_checks.pop()
                overflow -= 1
            while overflow > 0 and move_reason_history:
                move_reason_history.pop()
                overflow -= 1

        if transitions < required_transitions:
            # Do not fabricate reasons/checks; trim unmatched bbox tail.
            keep_bbox = max(1, transitions + 1)
            bbox_history = bbox_history[:keep_bbox]

        obj["bbox_history"] = bbox_history
        obj["move_reason_history"] = move_reason_history
        obj["disappear_checks"] = disappear_checks

    merged: Dict[int, Dict[str, Any]] = {}
    merged.update(state.archived_objects)
    merged.update(state.filtered_objects)
    for obj in merged.values():
        _normalize_object_history(obj)
    payload = {
        "objects": [merged[k] for k in sorted(merged.keys())]
    }
    with open(state.filtered_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _enqueue_vlm_task(state: RuntimeState, task: Dict[str, Any]) -> None:
    try:
        state.vlm_tasks.put_nowait(task)
        return
    except queue.Full:
        pass

    # Buffer policy: drop oldest queued work, keep newest scene state.
    try:
        _ = state.vlm_tasks.get_nowait()
    except queue.Empty:
        pass

    try:
        state.vlm_tasks.put_nowait(task)
    except queue.Full:
        state.vlm_dropped_tasks += 1


def _run_vlm_workers(state: RuntimeState, num_workers: int = 2) -> None:
    def _worker() -> None:
        while not state.vlm_stop_event.is_set():
            try:
                task = state.vlm_tasks.get(timeout=0.2)
            except queue.Empty:
                continue

            kind = str(task.get("kind", ""))
            response: Dict[str, Any] = {}
            try:
                if kind == "move":
                    response = state.vlm_client.assess_move(
                        label=str(task["label"]),
                        before_bgr=task["before_bgr"],
                        current_bgr=task["current_bgr"],
                    )
                elif kind == "disappear":
                    response = state.vlm_client.assess_disappear(
                        label=str(task["label"]),
                        before_bgr=task["before_bgr"],
                        current_bgr=task["current_bgr"],
                    )
                elif kind == "reappear":
                    response = state.vlm_client.assess_reappearance(
                        new_label=str(task["new_label"]),
                        old_label=str(task["old_label"]),
                        before_bgr=task["before_bgr"],
                        current_bgr=task["current_bgr"],
                    )
            except Exception as exc:
                response = {"error": str(exc)}

            state.vlm_results.put({"task": task, "response": response})

    for idx in range(max(1, int(num_workers))):
        thread = threading.Thread(target=_worker, daemon=True, name=f"vlm-worker-{idx}")
        thread.start()
        state.vlm_workers.append(thread)


def _apply_vlm_results(state: RuntimeState, frame_index: int) -> None:
    changed = False
    while True:
        try:
            item = state.vlm_results.get_nowait()
        except queue.Empty:
            break

        task = item.get("task", {})
        response = item.get("response", {})
        kind = str(task.get("kind", ""))

        if kind == "move":
            object_id = _resolve_object_id(state, int(task.get("object_id", -1)))
            if object_id < 0:
                continue
            move_reason_text = str(response.get("move_reason", "")).strip()
            if bool(response.get("did_move", False)) and move_reason_text:
                filtered_obj = _ensure_filtered_object(
                    state, object_id, str(task.get("label", "unknown"))
                )
                _append_filtered_bbox(
                    state=state,
                    object_id=object_id,
                    bbox_xywh=task["bbox_xywh"],
                    frame_index=int(task["frame_index"]),
                    timestamp=str(task["timestamp"]),
                    detection_confidence=float(task.get("detection_confidence", 0.0)),
                )
                filtered_obj["move_reason_history"].append(
                    {
                        "frame_index": int(task["frame_index"]),
                        "reason": move_reason_text,
                        "moved_by": str(response.get("moved_by", "")),
                        "confidence": float(response.get("confidence", 0.0)),
                    }
                )
                changed = True
            elif move_reason_text:
                filtered_obj = _ensure_filtered_object(
                    state, object_id, str(task.get("label", "unknown"))
                )
                filtered_obj["non_move_reason_history"].append(
                    {
                        "frame_index": int(task["frame_index"]),
                        "reason": move_reason_text,
                        "confidence": float(response.get("confidence", 0.0)),
                    }
                )
                changed = True
            continue

        if kind == "disappear":
            object_id = _resolve_object_id(state, int(task.get("object_id", -1)))
            if object_id < 0:
                continue
            target = state.filtered_objects.get(object_id) or state.archived_objects.get(object_id)
            if target is None:
                target = _ensure_filtered_object(state, object_id, str(task.get("label", "unknown")))
            target["disappear_checks"].append(
                {
                    "frame_index": int(task["frame_index"]),
                    "did_leave_frame": bool(response.get("did_leave_frame", False)),
                    "still_exists": bool(response.get("still_exists", False)),
                    "reason": str(response.get("reason", "")),
                    "confidence": float(response.get("confidence", 0.0)),
                }
            )
            if not bool(response.get("did_leave_frame", False)):
                target["non_disappear_reason_history"].append(
                    {
                        "frame_index": int(task["frame_index"]),
                        "reason": str(response.get("reason", "")),
                        "still_exists": bool(response.get("still_exists", False)),
                        "confidence": float(response.get("confidence", 0.0)),
                    }
                )
            if object_id in state.archived_objects:
                state.archived_objects[object_id] = target
            else:
                state.filtered_objects[object_id] = target
            changed = True
            continue

        if kind == "reappear":
            new_id = int(task.get("new_id", -1))
            old_id = int(task.get("old_id", -1))
            if new_id < 0 or old_id < 0:
                continue
            new_canonical = _resolve_object_id(state, new_id)
            target = _ensure_filtered_object(
                state, new_canonical, str(task.get("new_label", "unknown"))
            )
            if bool(response.get("is_same_object", False)):
                target["reappearance_checks"].append(
                    {
                        "frame_index": int(task.get("frame_index", -1)),
                        "old_object_id": old_id,
                        "reason": str(response.get("reason", "")),
                        "confidence": float(response.get("confidence", 0.0)),
                    }
                )
            else:
                target["non_reappearance_reason_history"].append(
                    {
                        "frame_index": int(task.get("frame_index", -1)),
                        "candidate_old_object_id": old_id,
                        "reason": str(response.get("reason", "")),
                        "confidence": float(response.get("confidence", 0.0)),
                    }
                )
                changed = True
                continue
            canonical = _resolve_object_id(state, old_id)
            state.id_remap[new_id] = canonical
            old_obj = state.archived_objects.pop(canonical, None)
            if old_obj is None:
                old_obj = state.filtered_objects.get(canonical)
            if old_obj is not None:
                state.filtered_objects[canonical] = old_obj
                if new_id not in old_obj["aliases"]:
                    old_obj["aliases"].append(new_id)
                changed = True
            continue

    # Avoid rewriting file too frequently under high frame rate.
    if changed and frame_index % 2 == 0:
        _write_filtered_state(state)


def _deepstream_obj_to_detection(obj_meta: pyds.NvDsObjectMeta) -> Dict[str, Any]:
    rect = obj_meta.rect_params
    x1 = float(rect.left)
    y1 = float(rect.top)
    x2 = float(rect.left + rect.width)
    y2 = float(rect.top + rect.height)
    return {
        "label": str(obj_meta.obj_label),
        "confidence": float(obj_meta.confidence),
        "bbox_xyxy": [x1, y1, x2, y2],
    }


def _append_bbox_history(
    state: RuntimeState,
    object_id: int,
    bbox_xywh: List[float],
    frame_index: int,
    timestamp: str,
) -> None:
    history = state.bbox_history_by_id.setdefault(object_id, [])
    box = [float(v) for v in bbox_xywh]
    if history and history[-1]["bbox_xywh"] == box:
        return
    history.append(
        {
            "frame_index": int(frame_index),
            "timestamp": timestamp,
            "bbox_xywh": box,
        }
    )


def _xywh_centroid_px(bbox_xywh: List[float]) -> Tuple[int, int]:
    x, y, w, h = bbox_xywh
    return (int(round(x + (w / 2.0))), int(round(y + (h / 2.0))))


def _xywh_displacement_px(a_xywh: List[float], b_xywh: List[float]) -> float:
    ax, ay = _xywh_centroid_px(a_xywh)
    bx, by = _xywh_centroid_px(b_xywh)
    return float(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)


def _append_trail_point(
    state: RuntimeState,
    object_id: int,
    point_xy: Tuple[int, int],
) -> None:
    points = state.trail_points_by_id.setdefault(object_id, [])
    if points and points[-1] == point_xy:
        return
    points.append(point_xy)


def _append_trail_segment(
    state: RuntimeState,
    object_id: int,
    from_xy: Tuple[int, int],
    to_xy: Tuple[int, int],
) -> None:
    _append_trail_point(state, object_id, from_xy)
    _append_trail_point(state, object_id, to_xy)
    segments = state.trail_segments_by_id.setdefault(object_id, [])
    seg = (from_xy, to_xy)
    if segments and segments[-1] == seg:
        return
    segments.append(seg)


def _add_bbox_display_meta(frame_meta, batch_meta, tracked_objects: Dict[int, Dict[str, Any]]) -> None:
    box_items: List[List[float]] = []
    for obj_id, obj in tracked_objects.items():
        _ = obj_id
        box_items.append([float(v) for v in obj["current_bbox_xywh"]])

    idx = 0
    while idx < len(box_items):
        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_rects = 0
        display_meta.num_lines = 0
        display_meta.num_labels = 0

        rect_count = 0
        while idx < len(box_items) and rect_count < 16:
            x, y, w, h = box_items[idx]
            rect = display_meta.rect_params[rect_count]
            rect.left = int(round(x))
            rect.top = int(round(y))
            rect.width = max(1, int(round(w)))
            rect.height = max(1, int(round(h)))
            rect.border_width = 3
            rect.has_bg_color = 0
            rect.border_color.set(0.0, 1.0, 0.0, 1.0)
            rect_count += 1
            idx += 1

        display_meta.num_rects = rect_count
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)


def _add_trail_segment_display_meta(frame_meta, batch_meta, state: RuntimeState) -> None:
    all_segments: List[Tuple[int, int, int, int, bool]] = []
    for object_id, segments in state.trail_segments_by_id.items():
        is_disappeared = object_id in state.disappeared_object_ids
        for from_xy, to_xy in segments:
            all_segments.append(
                (from_xy[0], from_xy[1], to_xy[0], to_xy[1], is_disappeared)
            )

    idx = 0
    while idx < len(all_segments):
        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_rects = 0
        display_meta.num_lines = 0
        display_meta.num_labels = 0

        line_count = 0
        while idx < len(all_segments) and line_count < 16:
            x1, y1, x2, y2, is_disappeared = all_segments[idx]
            line = display_meta.line_params[line_count]
            line.x1 = int(x1)
            line.y1 = int(y1)
            line.x2 = int(x2)
            line.y2 = int(y2)
            line.line_width = 2
            if is_disappeared:
                line.line_color.set(0.6, 0.6, 0.6, 1.0)
            else:
                line.line_color.set(0.0, 1.0, 1.0, 1.0)
            line_count += 1
            idx += 1

        display_meta.num_lines = line_count
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)


def _add_trail_dot_display_meta(frame_meta, batch_meta, state: RuntimeState) -> None:
    all_points: List[Tuple[int, int, bool]] = []
    for object_id, points in state.trail_points_by_id.items():
        is_disappeared = object_id in state.disappeared_object_ids
        for point in points:
            all_points.append((point[0], point[1], is_disappeared))

    idx = 0
    dot_radius = 3
    dot_size = (dot_radius * 2) + 1
    while idx < len(all_points):
        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_rects = 0
        display_meta.num_lines = 0
        display_meta.num_labels = 0

        rect_count = 0
        while idx < len(all_points) and rect_count < 16:
            cx, cy, is_disappeared = all_points[idx]
            rect = display_meta.rect_params[rect_count]
            rect.left = int(cx - dot_radius)
            rect.top = int(cy - dot_radius)
            rect.width = dot_size
            rect.height = dot_size
            rect.border_width = 0
            rect.has_bg_color = 1
            if is_disappeared:
                rect.bg_color.set(0.6, 0.6, 0.6, 1.0)
            else:
                rect.bg_color.set(1.0, 0.0, 0.0, 1.0)
            rect_count += 1
            idx += 1

        display_meta.num_rects = rect_count
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)


def _draw_overlay(frame_meta, batch_meta, state: RuntimeState) -> None:
    # Active objects keep bbox overlays.
    _add_bbox_display_meta(frame_meta, batch_meta, state.tracker.objects)
    # Persisted trail lines and dots are shown for full session, including disappeared objects.
    _add_trail_segment_display_meta(frame_meta, batch_meta, state)
    _add_trail_dot_display_meta(frame_meta, batch_meta, state)


def pgie_src_pad_buffer_probe(pad, info, state: RuntimeState):
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    if batch_meta is None:
        return Gst.PadProbeReturn.OK

    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        frame_index = int(frame_meta.frame_num)
        _apply_vlm_results(state, frame_index)
        timestamp = datetime.now(timezone.utc).isoformat()
        frame_bgr = _extract_frame_bgr(gst_buffer, frame_meta)
        if frame_bgr is not None:
            state.frame_history.append((frame_index, frame_bgr))
        before_bgr = _get_before_frame(state, frame_index)

        detections: List[Dict[str, Any]] = []
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            # Disable default detector overlay; we render tracker-only overlays ourselves.
            obj_meta.rect_params.border_width = 0
            det = _deepstream_obj_to_detection(obj_meta)
            if str(det.get("label", "")).lower() != "person":
                detections.append(det)
            try:
                l_obj = l_obj.next
            except StopIteration:
                l_obj = None

        state.tracker.process_frame(
            detections=detections,
            frame_index=frame_index,
            timestamp=timestamp,
        )
        current_state = state.tracker.current_state()
        current_objects: Dict[int, Dict[str, Any]] = {}
        for raw_id, obj in current_state.items():
            canonical_id = _resolve_object_id(state, int(raw_id))
            current_objects[canonical_id] = obj

        prev_objects = state.active_snapshot
        prev_ids = set(prev_objects.keys())
        current_ids = set(current_objects.keys())

        new_ids = sorted(current_ids - prev_ids)
        common_ids = sorted(current_ids & prev_ids)
        missing_ids = sorted(prev_ids - current_ids)

        for object_id in new_ids:
            obj = current_objects[object_id]
            label = str(obj.get("canonical_label", "unknown"))
            bbox_xywh = [float(v) for v in obj.get("current_bbox_xywh", [0, 0, 0, 0])]
            confidence = float(obj.get("confidence", 0.0))

            best_old_id = None
            best_iou = 0.0
            candidate_maps = [state.archived_objects, state.filtered_objects]
            for candidate_map in candidate_maps:
                for old_id, old_obj in candidate_map.items():
                    if old_id == object_id:
                        continue
                    old_hist = old_obj.get("bbox_history", [])
                    if not old_hist:
                        continue
                    old_bbox = old_hist[-1]["bbox_xywh"]
                    iou_val = _iou_xywh(bbox_xywh, old_bbox)
                    if iou_val >= 0.7 and iou_val > best_iou:
                        best_iou = iou_val
                        best_old_id = old_id

            if (
                best_old_id is not None
                and before_bgr is not None
                and frame_bgr is not None
            ):
                old_meta = (
                    state.archived_objects.get(best_old_id)
                    or state.filtered_objects.get(best_old_id)
                    or {}
                )
                old_label = str(old_meta.get("label", "unknown"))
                _enqueue_vlm_task(
                    state,
                    {
                        "kind": "reappear",
                        "new_id": int(obj.get("object_id", object_id)),
                        "old_id": best_old_id,
                        "frame_index": frame_index,
                        "new_label": label,
                        "old_label": old_label,
                        "before_bgr": before_bgr.copy(),
                        "current_bgr": frame_bgr.copy(),
                    },
                )

            filtered_obj = _ensure_filtered_object(state, object_id, label)
            if not filtered_obj.get("bbox_history"):
                _append_filtered_bbox(
                    state=state,
                    object_id=object_id,
                    bbox_xywh=bbox_xywh,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    detection_confidence=confidence,
                )

            _append_bbox_history(
                state=state,
                object_id=object_id,
                bbox_xywh=bbox_xywh,
                frame_index=frame_index,
                timestamp=timestamp,
            )
            if frame_bgr is not None:
                _save_change_frame(
                    frame_bgr=frame_bgr,
                    frames_dir=state.frames_dir,
                    timestamp=timestamp,
                    change_kind="start",
                    object_id=object_id,
                    frame_index=frame_index,
                )

        for object_id in common_ids:
            obj = current_objects[object_id]
            prev_obj = prev_objects[object_id]
            curr_bbox = [float(v) for v in obj.get("current_bbox_xywh", [0, 0, 0, 0])]
            prev_bbox = [float(v) for v in prev_obj.get("bbox_xywh", [0, 0, 0, 0])]
            displacement = _xywh_displacement_px(prev_bbox, curr_bbox)
            if displacement < float(state.tracker.motion_threshold):
                continue

            from_xy = _xywh_centroid_px(prev_bbox)
            to_xy = _xywh_centroid_px(curr_bbox)
            _append_trail_segment(state, object_id, from_xy, to_xy)
            if object_id not in state.bbox_history_by_id:
                _append_bbox_history(
                    state=state,
                    object_id=object_id,
                    bbox_xywh=prev_bbox,
                    frame_index=frame_index,
                    timestamp=timestamp,
                )

            label = str(obj.get("canonical_label", "unknown"))
            confidence = float(obj.get("confidence", 0.0))
            if before_bgr is not None and frame_bgr is not None:
                _enqueue_vlm_task(
                    state,
                    {
                        "kind": "move",
                        "object_id": object_id,
                        "label": label,
                        "bbox_xywh": curr_bbox,
                        "frame_index": frame_index,
                        "timestamp": timestamp,
                        "detection_confidence": confidence,
                        "before_bgr": before_bgr.copy(),
                        "current_bgr": frame_bgr.copy(),
                    },
                )
                if frame_bgr is not None:
                    _save_change_frame(
                        frame_bgr=frame_bgr,
                        frames_dir=state.frames_dir,
                        timestamp=timestamp,
                        change_kind="move",
                        object_id=object_id,
                        frame_index=frame_index,
                    )
                _append_bbox_history(
                    state=state,
                    object_id=object_id,
                    bbox_xywh=curr_bbox,
                    frame_index=frame_index,
                    timestamp=timestamp,
                )

        for object_id in missing_ids:
            prev_obj = prev_objects[object_id]
            prev_bbox = [float(v) for v in prev_obj.get("bbox_xywh", [0, 0, 0, 0])]
            prev_label = str(prev_obj.get("label", "unknown"))
            _append_trail_point(
                state=state,
                object_id=object_id,
                point_xy=_xywh_centroid_px(prev_bbox),
            )
            state.disappeared_object_ids.add(object_id)
            filtered_obj = _ensure_filtered_object(state, object_id, prev_label)
            if before_bgr is not None and frame_bgr is not None:
                _enqueue_vlm_task(
                    state,
                    {
                        "kind": "disappear",
                        "object_id": object_id,
                        "label": prev_label,
                        "frame_index": frame_index,
                        "before_bgr": before_bgr.copy(),
                        "current_bgr": frame_bgr.copy(),
                    },
                )
                _save_change_frame(
                    frame_bgr=frame_bgr,
                    frames_dir=state.frames_dir,
                    timestamp=timestamp,
                    change_kind="end",
                    object_id=object_id,
                    frame_index=frame_index,
                )
            state.archived_objects[object_id] = dict(filtered_obj)
            state.filtered_objects.pop(object_id, None)
            state.bbox_history_by_id.pop(object_id, None)

        state.active_snapshot = {
            object_id: {
                "bbox_xywh": [float(v) for v in obj.get("current_bbox_xywh", [0, 0, 0, 0])],
                "label": str(obj.get("canonical_label", "unknown")),
                "confidence": float(obj.get("confidence", 0.0)),
            }
            for object_id, obj in current_objects.items()
        }
        _write_filtered_state(state)

        _draw_overlay(frame_meta, batch_meta, state)

        state.frames_processed += 1

        try:
            l_frame = l_frame.next
        except StopIteration:
            l_frame = None

    return Gst.PadProbeReturn.OK


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DeepStream webcam YOLO -> ObjectTracker JSON events",
    )
    parser.add_argument(
        "--source",
        type=int,
        default=0,
        help="Webcam device index for /dev/videoN (default: 0)",
    )
    parser.add_argument(
        "--motion-threshold",
        type=float,
        default=25.0,
        help="Pixel displacement threshold for object_moved",
    )
    parser.add_argument(
        "--max-missing",
        type=int,
        default=12,
        help="Frames before object_disappeared fires",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default="captures",
        help="Directory where output files will be written",
    )
    parser.add_argument(
        "--events-file",
        type=str,
        default="",
        help="Optional explicit output path for JSONL events",
    )
    parser.add_argument(
        "--video-file",
        type=str,
        default="",
        help="Optional explicit output path for recording file",
    )
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    ds_dir = os.path.join(project_root, "deepstream")

    app_cfg_path = os.path.join(ds_dir, "deepstream_app_config.txt")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.optionxform = str
    if os.path.exists(app_cfg_path):
        cfg.read(app_cfg_path)
    else:
        raise FileNotFoundError(f"DeepStream app config missing: {app_cfg_path}")

    os.makedirs(args.save_dir, exist_ok=True)
    recordings_dir = "/mnt/nvme/recordings"
    frames_dir = "/mnt/nvme/frames"
    events_dir = "/mnt/nvme/events"
    os.makedirs(recordings_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(events_dir, exist_ok=True)

    filtered_path = os.path.join(events_dir, "filtered_events.json")

    if args.video_file:
        video_path = args.video_file
    else:
        video_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_path = os.path.join(recordings_dir, f"tracking_{video_stamp}.mkv")

    with open(filtered_path, "w", encoding="utf-8") as f:
        json.dump({"objects": []}, f, indent=2)

    tracker = ObjectTracker(
        motion_threshold=args.motion_threshold,
        max_missing_frames=args.max_missing,
    )
    vlm_client = OllamaVLM(model="ahmadwaqar/smolvlm2-2.2b-instruct:latest")
    state = RuntimeState(
        tracker=tracker,
        frames_dir=frames_dir,
        filtered_path=filtered_path,
        vlm_client=vlm_client,
    )
    _run_vlm_workers(state, num_workers=2)

    Gst.init(None)
    pipeline = Gst.Pipeline.new("deepstream-yolo-webcam")

    source = Gst.ElementFactory.make("v4l2src", "usb-cam")
    source.set_property("device", f"/dev/video{args.source}")

    vidconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    caps = Gst.ElementFactory.make("capsfilter", "filter")
    queue_infer = Gst.ElementFactory.make("queue", "queue-infer")
    pre_osd_convert = Gst.ElementFactory.make("nvvideoconvert", "pre-osd-convert")
    pre_osd_caps = Gst.ElementFactory.make("capsfilter", "pre-osd-filter")
    osd = Gst.ElementFactory.make("nvdsosd", "on-screen-display")
    post_osd_convert = Gst.ElementFactory.make("nvvideoconvert", "post-osd-convert")
    post_osd_caps = Gst.ElementFactory.make("capsfilter", "post-osd-filter")
    tee_post = Gst.ElementFactory.make("tee", "post-osd-splitter")
    queue_display = Gst.ElementFactory.make("queue", "queue-display")
    queue_record = Gst.ElementFactory.make("queue", "queue-record")

    cam_w = _cfg_getint(cfg, "source0", "camera-width", 1280)
    cam_h = _cfg_getint(cfg, "source0", "camera-height", 720)
    fps_n = _cfg_getint(cfg, "source0", "camera-fps-n", 5)
    fps_d = _cfg_getint(cfg, "source0", "camera-fps-d", 1)
    caps.set_property(
        "caps",
        Gst.Caps.from_string(
            f"video/x-raw(memory:NVMM), format=NV12, width={cam_w}, "
            f"height={cam_h}, framerate={fps_n}/{fps_d}"
        ),
    )
    pre_osd_caps.set_property(
        "caps",
        Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA"),
    )
    post_osd_caps.set_property(
        "caps",
        Gst.Caps.from_string("video/x-raw(memory:NVMM), format=NV12"),
    )

    muxer = Gst.ElementFactory.make("nvstreammux", "muxer")
    _safe_set(muxer, "gpu-id", _cfg_getint(cfg, "streammux", "gpu-id", 0))
    _safe_set(
        muxer, "live-source", bool(_cfg_getint(cfg, "streammux", "live-source", 1))
    )
    _safe_set(muxer, "batch-size", _cfg_getint(cfg, "streammux", "batch-size", 1))
    _safe_set(
        muxer,
        "batched-push-timeout",
        _cfg_getint(cfg, "streammux", "batched-push-timeout", 40000),
    )
    _safe_set(muxer, "width", _cfg_getint(cfg, "streammux", "width", 1920))
    _safe_set(muxer, "height", _cfg_getint(cfg, "streammux", "height", 1080))
    _safe_set(
        muxer,
        "enable-padding",
        bool(_cfg_getint(cfg, "streammux", "enable-padding", 0)),
    )
    _safe_set(
        muxer,
        "nvbuf-memory-type",
        _cfg_getint(cfg, "streammux", "nvbuf-memory-type", 0),
    )

    pgie = Gst.ElementFactory.make("nvinfer", "yolo-inference")
    _safe_set(pgie, "gpu-id", _cfg_getint(cfg, "primary-gie", "gpu-id", 0))
    _safe_set(
        pgie,
        "nvbuf-memory-type",
        _cfg_getint(cfg, "primary-gie", "nvbuf-memory-type", 0),
    )
    infer_cfg_name = _cfg_get(
        cfg, "primary-gie", "config-file", "config_infer_primary_yolo26.txt"
    )
    infer_cfg_path = os.path.join(ds_dir, infer_cfg_name)
    pgie.set_property("config-file-path", infer_cfg_path)

    encoder = Gst.ElementFactory.make("nvv4l2h264enc", "h264-enc")
    using_nvenc = encoder is not None
    if encoder is None:
        encoder = Gst.ElementFactory.make("x264enc", "h264-enc")
    if encoder is None:
        raise RuntimeError("Failed to create H.264 encoder")
    record_convert = None
    record_caps = None
    if using_nvenc:
        _safe_set(encoder, "bitrate", _cfg_getint(cfg, "sink0", "bitrate", 8000000))
        _safe_set(encoder, "insert-sps-pps", 1)
        _safe_set(encoder, "preset-level", 1)
    else:
        # x264enc expects system-memory raw video, not NVMM buffers.
        record_convert = Gst.ElementFactory.make("nvvideoconvert", "record-convert")
        record_caps = Gst.ElementFactory.make("capsfilter", "record-filter")
        record_caps.set_property(
            "caps", Gst.Caps.from_string("video/x-raw, format=I420")
        )
        src_bitrate = _cfg_getint(cfg, "sink0", "bitrate", 8000000)
        x264_bitrate_kbps = max(1, int(src_bitrate // 1000))
        _safe_set(encoder, "bitrate", x264_bitrate_kbps)

    h264parse = Gst.ElementFactory.make("h264parse", "h264-parser")
    container_mux = Gst.ElementFactory.make("matroskamux", "container-mux")
    file_sink = Gst.ElementFactory.make("filesink", "video-sink")
    file_sink.set_property("location", video_path)
    _safe_set(file_sink, "sync", False)
    _safe_set(file_sink, "async", False)

    sink = Gst.ElementFactory.make("fakesink", "null-sink")

    elements = [
        source,
        vidconv,
        caps,
        queue_infer,
        pre_osd_convert,
        pre_osd_caps,
        osd,
        post_osd_convert,
        post_osd_caps,
        tee_post,
        queue_display,
        queue_record,
        muxer,
        pgie,
        encoder,
        h264parse,
        container_mux,
        file_sink,
        sink,
    ]
    if record_convert is not None and record_caps is not None:
        elements.insert(elements.index(encoder), record_caps)
        elements.insert(elements.index(record_caps), record_convert)

    for el in elements:
        if el is None:
            raise RuntimeError("Failed to create one or more GStreamer elements")
        pipeline.add(el)

    if not source.link(vidconv):
        raise RuntimeError("Could not link source -> nvvideoconvert")
    if not vidconv.link(caps):
        raise RuntimeError("Could not link nvvideoconvert -> capsfilter")
    if not caps.link(queue_infer):
        raise RuntimeError("Could not link capsfilter -> queue_infer")

    if using_nvenc:
        if not queue_record.link(encoder):
            raise RuntimeError("Could not link queue_record -> encoder")
    else:
        if not queue_record.link(record_convert):
            raise RuntimeError("Could not link queue_record -> record_convert")
        if not record_convert.link(record_caps):
            raise RuntimeError("Could not link record_convert -> record_caps")
        if not record_caps.link(encoder):
            raise RuntimeError("Could not link record_caps -> encoder")
    if not encoder.link(h264parse):
        raise RuntimeError("Could not link encoder -> h264parse")
    if not h264parse.link(container_mux):
        raise RuntimeError("Could not link h264parse -> container_mux")
    if not container_mux.link(file_sink):
        raise RuntimeError("Could not link container_mux -> filesink")

    sinkpad = muxer.get_request_pad("sink_0")
    srcpad = queue_infer.get_static_pad("src")
    if srcpad.link(sinkpad) != Gst.PadLinkReturn.OK:
        raise RuntimeError("Could not link queue_infer -> nvstreammux")

    if not muxer.link(pgie):
        raise RuntimeError("Could not link nvstreammux -> nvinfer")
    if not pgie.link(pre_osd_convert):
        raise RuntimeError("Could not link nvinfer -> pre_osd_convert")
    if not pre_osd_convert.link(pre_osd_caps):
        raise RuntimeError("Could not link pre_osd_convert -> pre_osd_caps")
    if not pre_osd_caps.link(osd):
        raise RuntimeError("Could not link pre_osd_caps -> nvdsosd")
    if not osd.link(post_osd_convert):
        raise RuntimeError("Could not link nvdsosd -> post_osd_convert")
    if not post_osd_convert.link(post_osd_caps):
        raise RuntimeError("Could not link post_osd_convert -> post_osd_caps")
    if not post_osd_caps.link(tee_post):
        raise RuntimeError("Could not link post_osd_caps -> tee_post")

    tee_src_template = tee_post.get_pad_template("src_%u")
    tee_src_display = tee_post.request_pad(tee_src_template, None, None)
    tee_src_record = tee_post.request_pad(tee_src_template, None, None)
    if tee_src_display is None or tee_src_record is None:
        raise RuntimeError("Failed to request post-osd tee src pads")

    display_queue_sink = queue_display.get_static_pad("sink")
    if tee_src_display.link(display_queue_sink) != Gst.PadLinkReturn.OK:
        raise RuntimeError("Could not link tee_post -> queue_display")

    record_queue_sink = queue_record.get_static_pad("sink")
    if tee_src_record.link(record_queue_sink) != Gst.PadLinkReturn.OK:
        raise RuntimeError("Could not link tee_post -> queue_record")

    if not queue_display.link(sink):
        raise RuntimeError("Could not link queue_display -> fakesink")

    probe_pad = pre_osd_caps.get_static_pad("src")
    probe_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe, state)

    print("=" * 60)
    print("DeepStream YOLO webcam tracker running")
    print(f"Webcam device : /dev/video{args.source}")
    print(f"Filtered file : {filtered_path}")
    print(f"Video file    : {video_path}")
    print(f"Event frames  : {frames_dir}")
    print("VLM mode      : async (buffered)")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    eos_received = False

    def on_message(_, message):
        nonlocal eos_received
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"[ERROR] {err} | {debug}")
            loop.quit()
        elif message.type == Gst.MessageType.EOS:
            eos_received = True
            print("[*] EOS received")
            loop.quit()

    bus.connect("message", on_message)
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user")
        print("[*] Sending EOS to finalize recording...")
        if not pipeline.send_event(Gst.Event.new_eos()):
            print("WARNING: failed to send EOS; recording may be incomplete")
        else:
            msg = bus.timed_pop_filtered(
                5 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR
            )
            if msg is None:
                print("WARNING: timeout waiting for EOS; forcing pipeline shutdown")
            elif msg.type == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                print(f"[ERROR] {err} | {debug}")
            elif msg.type == Gst.MessageType.EOS:
                eos_received = True
                print("[*] EOS confirmed for recording branch")
    finally:
        # Drain finished VLM responses before final write.
        _apply_vlm_results(state, state.frames_processed)
        state.vlm_stop_event.set()
        for thread in state.vlm_workers:
            thread.join(timeout=0.5)
        _apply_vlm_results(state, state.frames_processed)

        written_session_end: Set[int] = set()
        for object_id, obj in tracker.objects.items():
            canonical_id = _resolve_object_id(state, object_id)
            if canonical_id in written_session_end:
                continue
            written_session_end.add(canonical_id)
            _ensure_filtered_object(state, canonical_id, str(obj["canonical_label"]))
            _append_bbox_history(
                state=state,
                object_id=canonical_id,
                bbox_xywh=[float(v) for v in obj["current_bbox_xywh"]],
                frame_index=int(obj["last_seen_frame_index"]),
                timestamp=str(obj["last_seen_timestamp"]),
            )
        _write_filtered_state(state)

        if not eos_received:
            print("WARNING: shutting down without EOS confirmation")
        pipeline.set_state(Gst.State.NULL)

        print(f"\n{'=' * 60}")
        print("Session Summary")
        print(f"Total frames processed   : {state.frames_processed}")
        print(f"Tracked objects remaining: {len(tracker.objects)}")
        print(f"Filtered file            : {filtered_path}")
        print(f"Event frames             : {frames_dir}")
        print(f"Video file               : {video_path}")
        print(f"VLM dropped tasks        : {state.vlm_dropped_tasks}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
