from __future__ import annotations

import base64
import json
from typing import Any, Dict, List
from urllib import error as urllib_error
from urllib import request as urllib_request

import cv2


class NanoLLMVLM:
    def __init__(
        self,
        model: str = "Efficient-Large-Model/VILA1.5-3b",
        base_url: str = "http://127.0.0.1:8080/v1/chat/completions",
        timeout_sec: float = 15.0,
        max_new_tokens: int = 128,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout_sec = float(timeout_sec)
        self.max_new_tokens = int(max_new_tokens)

    @staticmethod
    def _encode_image_b64(image_bgr) -> str:
        ok, buf = cv2.imencode(".jpg", image_bgr)
        if not ok:
            raise RuntimeError("Failed to JPEG-encode frame for VLM")
        return base64.b64encode(buf).decode("utf-8")

    @staticmethod
    def _safe_json_from_content(content: str) -> Dict[str, Any]:
        if not content:
            return {}
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _move_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "did_move": {"type": "boolean"},
                "move_reason": {"type": "string"},
                "moved_by": {"type": "string"},
                "object_color": {"type": "string"},
                "scene_description": {"type": "string"},
                "new_label": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": [
                "did_move",
                "move_reason",
                "moved_by",
                "object_color",
                "scene_description",
                "new_label",
                "confidence",
            ],
            "additionalProperties": False,
        }

    @staticmethod
    def _disappear_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "did_leave_frame": {"type": "boolean"},
                "still_exists": {"type": "boolean"},
                "reason": {"type": "string"},
                "object_color": {"type": "string"},
                "scene_description": {"type": "string"},
                "new_label": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": [
                "did_leave_frame",
                "still_exists",
                "reason",
                "object_color",
                "scene_description",
                "new_label",
                "confidence",
            ],
            "additionalProperties": False,
        }

    @staticmethod
    def _reappearance_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "is_same_object": {"type": "boolean"},
                "reason": {"type": "string"},
                "object_color": {"type": "string"},
                "scene_description": {"type": "string"},
                "new_label": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": [
                "is_same_object",
                "reason",
                "object_color",
                "scene_description",
                "new_label",
                "confidence",
            ],
            "additionalProperties": False,
        }

    @staticmethod
    def _extract_content(payload: Dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        return str(content)

    def _post_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            url=self.base_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except urllib_error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                pass
            raise RuntimeError(
                f"HTTP {exc.code} from NanoLLM API: {err_body or str(exc)}"
            ) from exc
        return json.loads(raw) if raw else {}

    def _ask_json(
        self,
        prompt: str,
        before_bgr,
        current_bgr,
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        before_b64 = self._encode_image_b64(before_bgr)
        current_b64 = self._encode_image_b64(current_bgr)
        print(
            "[VLM request] "
            f"model={self.model} max_tokens={self.max_new_tokens} "
            f"before_b64_len={len(before_b64)} current_b64_len={len(current_b64)}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"},
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{current_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": self.max_new_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "vlm_response", "schema": schema},
            },
        }

        try:
            raw = self._post_json(payload)
            content = self._extract_content(raw)
            print(f"[VLM raw output] {content}")
            parsed = self._safe_json_from_content(content)
            if parsed:
                return parsed
            print("[VLM warn] primary payload returned non-JSON content")
        except urllib_error.URLError as exc:
            raise RuntimeError(
                "NanoLLM server not reachable. Is sidecar running on "
                f"{self.base_url}? error={exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"NanoLLM HTTP request failed: {exc}") from exc

        fallback_payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [before_b64, current_b64],
                }
            ],
            "temperature": 0,
            "max_tokens": self.max_new_tokens,
            "format": schema,
        }
        try:
            raw = self._post_json(fallback_payload)
            content = self._extract_content(raw)
            print(f"[VLM raw output][fallback] {content}")
            parsed = self._safe_json_from_content(content)
            if parsed:
                return parsed
            print("[VLM warn] fallback payload returned non-JSON content")
        except Exception:
            pass

        return {}

    @staticmethod
    def _build_content_message(kind: str, **kwargs: Any) -> str:
        if kind == "move":
            did_move = bool(kwargs.get("did_move", False))
            move_reason = str(kwargs.get("move_reason", "")).strip() or "unknown"
            moved_by = str(kwargs.get("moved_by", "")).strip() or "unknown"
            scene_description = (
                str(kwargs.get("scene_description", "")).strip() or "unknown"
            )
            return (
                f"move check: did_move={did_move}, "
                f"reason={move_reason}, moved_by={moved_by}, scene={scene_description}"
            )
        if kind == "disappear":
            did_leave = bool(kwargs.get("did_leave_frame", False))
            still_exists = bool(kwargs.get("still_exists", False))
            reason = str(kwargs.get("reason", "")).strip() or "unknown"
            scene_description = (
                str(kwargs.get("scene_description", "")).strip() or "unknown"
            )
            return (
                f"disappear check: did_leave_frame={did_leave}, "
                f"still_exists={still_exists}, reason={reason}, scene={scene_description}"
            )
        if kind == "reappear":
            same = bool(kwargs.get("is_same_object", False))
            reason = str(kwargs.get("reason", "")).strip() or "unknown"
            scene_description = (
                str(kwargs.get("scene_description", "")).strip() or "unknown"
            )
            return (
                f"reappear check: is_same_object={same}, reason={reason}, "
                f"scene={scene_description}"
            )
        return "vlm check"

    def assess_move(self, label: str, before_bgr, current_bgr) -> Dict[str, Any]:
        schema = self._move_schema()
        base_prompt = (
            f"Two frames: first is earlier, second is current. Focus on object '{label}'. "
            f"Analyze only objects of label type '{label}' when deciding movement; treat other objects only as context. "
            f"Return STRICT JSON only (no extra text) with keys: "
            f"did_move (bool; true only if clear visual movement), "
            f"move_reason (str; what CAUSED the movement / mechanism, e.g. pushed/pulled/picked up/placed down/dragged/slid/rolled/tipped/fell/bumped/rotated; "
            f"use 'unknown' if unsure; for self-propelled objects you can use walked/drove/flew), "
            f"moved_by (str; WHO/WHAT applied the force or agent, e.g. person/hand/animal/robot/vehicle/wind/gravity/collision/self/camera/unknown), "
            f"object_color (str; main color, lowercase, or 'unknown'), "
            f"scene_description (str; brief nearby context: surface + adjacent items), "
            f"new_label (str; better lowercase name if '{label}' is wrong, else '{label}'), "
            f"confidence (number 0..1; certainty)."
        )
        prompt = base_prompt
        attempts = 0
        while attempts < 3:
            attempts += 1
            result = self._ask_json(prompt, before_bgr, current_bgr, schema)
            did_move = bool(result.get("did_move", False))
            move_reason = str(result.get("move_reason", "")).strip()
            moved_by = str(result.get("moved_by", ""))
            object_color = str(result.get("object_color", "")).strip() or "unknown"
            scene_description = str(result.get("scene_description", "")).strip()
            suggested_label = str(result.get("new_label", "")).strip() or str(label).strip()
            confidence = float(result.get("confidence", 0.0) or 0.0)

            if did_move and not move_reason:
                if attempts >= 3:
                    content = self._build_content_message(
                        "move",
                        did_move=True,
                        move_reason="unknown",
                        moved_by=(moved_by or "unknown"),
                        scene_description=(scene_description or "unknown"),
                    )
                    return {
                        "did_move": True,
                        "move_reason": "unknown",
                        "moved_by": moved_by or "unknown",
                        "object_color": object_color,
                        "scene_description": scene_description,
                        "new_label": suggested_label,
                        "confidence": confidence,
                        "content": content,
                    }
                prompt = (
                    base_prompt
                    + " IMPORTANT: If did_move is true, move_reason must be a non-empty string."
                )
                continue

            content = self._build_content_message(
                "move",
                did_move=did_move,
                move_reason=move_reason,
                moved_by=moved_by,
                scene_description=scene_description,
            )
            return {
                "did_move": did_move,
                "move_reason": move_reason,
                "moved_by": moved_by,
                "object_color": object_color,
                "scene_description": scene_description,
                "new_label": suggested_label,
                "confidence": confidence,
                "content": content,
            }

        content = self._build_content_message(
            "move",
            did_move=False,
            move_reason="",
            moved_by="",
            scene_description="",
        )
        return {
            "did_move": False,
            "move_reason": "",
            "moved_by": "",
            "object_color": "unknown",
            "scene_description": "",
            "new_label": str(label).strip() or "unknown",
            "confidence": 0.0,
            "content": content,
        }

    def assess_disappear(self, label: str, before_bgr, current_bgr) -> Dict[str, Any]:
        schema = self._disappear_schema()
        prompt = (
            f"Two frames: first is earlier, second is current. Focus on object '{label}'. "
            f"Analyze only objects of label type '{label}' when deciding disappearance; treat other objects only as context. "
            f"Return STRICT JSON only (no extra text) with keys: "
            f"did_leave_frame (bool; true if object likely exited the camera view), "
            f"still_exists (bool; true if likely still present but occluded/not detected), "
            f"reason (str; short explanation), "
            f"object_color (str; main color, lowercase, or 'unknown'), "
            f"scene_description (str; brief nearby context: surface + adjacent items), "
            f"new_label (str; better lowercase name if '{label}' is wrong, else '{label}'), "
            f"confidence (number 0..1; certainty)."
        )
        result = self._ask_json(prompt, before_bgr, current_bgr, schema)
        did_leave_frame = bool(result.get("did_leave_frame", False))
        still_exists = bool(result.get("still_exists", False))
        reason = str(result.get("reason", ""))
        scene_description = str(result.get("scene_description", ""))
        content = self._build_content_message(
            "disappear",
            did_leave_frame=did_leave_frame,
            still_exists=still_exists,
            reason=reason,
            scene_description=scene_description,
        )
        return {
            "did_leave_frame": did_leave_frame,
            "still_exists": still_exists,
            "reason": reason,
            "object_color": str(result.get("object_color", "")).strip() or "unknown",
            "scene_description": scene_description,
            "new_label": str(result.get("new_label", "")).strip() or str(label).strip(),
            "confidence": float(result.get("confidence", 0.0) or 0.0),
            "content": content,
        }

    def assess_reappearance(
        self,
        new_label: str,
        old_label: str,
        before_bgr,
        current_bgr,
    ) -> Dict[str, Any]:
        schema = self._reappearance_schema()
        prompt = (
            f"Two frames: first is earlier, second is current. "
            f"A detector says a NEW '{new_label}' appeared but overlaps an old '{old_label}'. "
            f"Analyze only these candidate labels ('{new_label}' and '{old_label}') for the identity decision; treat other objects only as context. "
            f"Return STRICT JSON only (no extra text) with keys: "
            f"is_same_object (bool; true if this is the old object re-detected), "
            f"reason (str; short explanation), "
            f"object_color (str; main color, lowercase, or 'unknown'), "
            f"scene_description (str; brief nearby context: surface + adjacent items), "
            f"new_label (str; best lowercase name if label is wrong, else '{new_label}'), "
            f"confidence (number 0..1; certainty)."
        )
        result = self._ask_json(prompt, before_bgr, current_bgr, schema)
        is_same_object = bool(result.get("is_same_object", False))
        reason = str(result.get("reason", ""))
        scene_description = str(result.get("scene_description", ""))
        content = self._build_content_message(
            "reappear",
            is_same_object=is_same_object,
            reason=reason,
            scene_description=scene_description,
        )
        return {
            "is_same_object": is_same_object,
            "reason": reason,
            "object_color": str(result.get("object_color", "")).strip() or "unknown",
            "scene_description": scene_description,
            "new_label": str(result.get("new_label", "")).strip() or str(new_label).strip(),
            "confidence": float(result.get("confidence", 0.0) or 0.0),
            "content": content,
        }

