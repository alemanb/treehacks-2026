from __future__ import annotations

import base64
import json
from typing import Any, Dict

import cv2
from ollama import chat


class OllamaVLM:
    def __init__(self, model: str = "moondream:1.8b") -> None:
        self.model = model

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

    def _ask_json(self, prompt: str, before_bgr, current_bgr) -> Dict[str, Any]:
        before_b64 = self._encode_image_b64(before_bgr)
        current_b64 = self._encode_image_b64(current_bgr)

        response = chat(
            model=self.model,
            format="json",
            options={"temperature": 0},
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [before_b64, current_b64],
                }
            ],
        )
        msg = response.get("message", {})
        content = msg.get("content", "")
        return self._safe_json_from_content(content)

    def assess_move(self, label: str, before_bgr, current_bgr) -> Dict[str, Any]:
        base_prompt = (
            f'Two frames are provided: first is earlier (about 2 frames before), second is current. '
            f'Focus on object type "{label}". '
            f"Return STRICT JSON with keys: did_move (boolean), move_reason (string), moved_by (string), confidence (number 0..1). "
            f"Set did_move true only if there is clear visual movement of that object. "
            f"If did_move is true, move_reason must be non-empty; if uncertain, use move_reason='unknown'."
        )
        prompt = base_prompt
        attempts = 0
        while attempts < 3:
            attempts += 1
            result = self._ask_json(prompt, before_bgr, current_bgr)
            did_move = bool(result.get("did_move", False))
            move_reason = str(result.get("move_reason", "")).strip()
            moved_by = str(result.get("moved_by", ""))
            confidence = float(result.get("confidence", 0.0) or 0.0)

            # Invalid: model says it moved but provides no reason -> regenerate.
            if did_move and not move_reason:
                if attempts >= 3:
                    return {
                        "did_move": True,
                        "move_reason": "unknown",
                        "moved_by": moved_by or "unknown",
                        "confidence": confidence,
                    }
                prompt = (
                    base_prompt
                    + " IMPORTANT: If did_move is true, move_reason must be a non-empty string."
                )
                continue

            return {
                "did_move": did_move,
                "move_reason": move_reason,
                "moved_by": moved_by,
                "confidence": confidence,
            }

        # Should normally return inside loop, keep safe fallback.
        return {
            "did_move": False,
            "move_reason": "",
            "moved_by": "",
            "confidence": 0.0,
        }

    def assess_disappear(self, label: str, before_bgr, current_bgr) -> Dict[str, Any]:
        prompt = (
            f'Two frames are provided: first is earlier (about 2 frames before), second is current. '
            f'Focus on object type "{label}". '
            f"Return STRICT JSON with keys: did_leave_frame (boolean), still_exists (boolean), reason (string), confidence (number 0..1). "
            f"did_leave_frame=true means object likely exited view; still_exists=true means it likely remains but is occluded/not detected."
        )
        result = self._ask_json(prompt, before_bgr, current_bgr)
        return {
            "did_leave_frame": bool(result.get("did_leave_frame", False)),
            "still_exists": bool(result.get("still_exists", False)),
            "reason": str(result.get("reason", "")),
            "confidence": float(result.get("confidence", 0.0) or 0.0),
        }

    def assess_reappearance(
        self,
        new_label: str,
        old_label: str,
        before_bgr,
        current_bgr,
    ) -> Dict[str, Any]:
        prompt = (
            f'Two frames are provided: first is earlier (about 2 frames before), second is current. '
            f"A detector claims a NEW object of type '{new_label}' appeared, but it highly overlaps a prior object of type '{old_label}'. "
            f"Return STRICT JSON with keys: is_same_object (boolean), reason (string), confidence (number 0..1). "
            f"is_same_object=true means it is likely re-detection of existing object, not a truly new one."
        )
        result = self._ask_json(prompt, before_bgr, current_bgr)
        return {
            "is_same_object": bool(result.get("is_same_object", False)),
            "reason": str(result.get("reason", "")),
            "confidence": float(result.get("confidence", 0.0) or 0.0),
        }
