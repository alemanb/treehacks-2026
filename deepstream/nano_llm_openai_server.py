from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


class NanoLLMBridge:
    def __init__(
        self,
        model: str,
        api: str,
        vision_api: str,
        max_context_len: int,
    ) -> None:
        self.model_name = model
        self.api = api
        self.vision_api = vision_api
        self.max_context_len = int(max_context_len)
        self.lock = threading.Lock()

        try:
            from nano_llm import ChatHistory, NanoLLM
        except Exception as exc:
            raise RuntimeError(
                "Failed to import nano_llm. Run this script inside the nano_llm container."
            ) from exc

        self._chat_history_cls = ChatHistory
        self._model = self._load_model(NanoLLM)

    def _load_model(self, nano_llm_cls):
        loaders = [
            lambda: nano_llm_cls.from_pretrained(
                self.model_name,
                api=self.api,
                vision_api=self.vision_api,
                max_context_len=self.max_context_len,
            ),
            lambda: nano_llm_cls.from_pretrained(
                model=self.model_name,
                api=self.api,
                vision_api=self.vision_api,
                max_context_len=self.max_context_len,
            ),
            lambda: nano_llm_cls.from_pretrained(
                self.model_name,
                api=self.api,
                vision_api=self.vision_api,
            ),
            lambda: nano_llm_cls.from_pretrained(
                model=self.model_name,
                api=self.api,
                vision_api=self.vision_api,
            ),
        ]
        last_error: Optional[Exception] = None
        for load in loaders:
            try:
                model = load()
                print(
                    "[server] loaded model "
                    f"model={self.model_name} api={self.api} vision_api={self.vision_api}"
                )
                return model
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(f"Failed loading model: {last_error}")

    def _new_chat_history(self):
        constructors = [
            lambda: self._chat_history_cls(self._model),
            lambda: self._chat_history_cls(model=self._model),
        ]
        for ctor in constructors:
            try:
                return ctor()
            except Exception:
                continue
        raise RuntimeError("Failed constructing ChatHistory")

    @staticmethod
    def _decode_image_bytes(raw: bytes) -> Optional[np.ndarray]:
        arr = np.frombuffer(raw, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _decode_data_url(value: str) -> Optional[np.ndarray]:
        if not value.startswith("data:image/"):
            return None
        marker = ";base64,"
        idx = value.find(marker)
        if idx < 0:
            return None
        b64 = value[idx + len(marker) :]
        try:
            raw = base64.b64decode(b64, validate=True)
        except binascii.Error:
            return None
        return NanoLLMBridge._decode_image_bytes(raw)

    @staticmethod
    def _decode_plain_base64(value: str) -> Optional[np.ndarray]:
        try:
            raw = base64.b64decode(value, validate=True)
        except binascii.Error:
            return None
        return NanoLLMBridge._decode_image_bytes(raw)

    @staticmethod
    def _load_image_url(url: str) -> Optional[np.ndarray]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ("http", "https"):
            with urllib.request.urlopen(url, timeout=8) as resp:
                raw = resp.read()
            return NanoLLMBridge._decode_image_bytes(raw)
        if parsed.scheme == "file":
            file_path = urllib.request.url2pathname(parsed.path)
            if not file_path:
                return None
            with open(file_path, "rb") as f:
                raw = f.read()
            return NanoLLMBridge._decode_image_bytes(raw)
        return None

    @staticmethod
    def _load_image_path(path: str) -> Optional[np.ndarray]:
        if not path:
            return None
        if not os.path.isfile(path):
            return None
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _decode_any_image(value: Any) -> Optional[np.ndarray]:
        if isinstance(value, dict):
            value = value.get("url")
        if not isinstance(value, str):
            return None
        v = value.strip()
        if not v:
            return None
        if v.startswith("data:image/"):
            return NanoLLMBridge._decode_data_url(v)
        if v.startswith("http://") or v.startswith("https://") or v.startswith("file://"):
            try:
                return NanoLLMBridge._load_image_url(v)
            except Exception:
                return None
        from_path = NanoLLMBridge._load_image_path(v)
        if from_path is not None:
            return from_path
        return NanoLLMBridge._decode_plain_base64(v)

    @staticmethod
    def _append_text(chat, role: str, text: str) -> None:
        appenders = [
            lambda: chat.append(role=role, text=text),
            lambda: chat.append(role, text=text),
            lambda: chat.append(role=role, content=text),
            lambda: chat.append({"role": role, "text": text}),
        ]
        for append in appenders:
            try:
                append()
                return
            except Exception:
                continue
        raise RuntimeError("Unable to append text")

    @staticmethod
    def _append_image(chat, role: str, image_rgb: np.ndarray) -> None:
        appenders = [
            lambda: chat.append(role=role, image=image_rgb),
            lambda: chat.append(role, image=image_rgb),
            lambda: chat.append({"role": role, "image": image_rgb}),
        ]
        for append in appenders:
            try:
                append()
                return
            except Exception:
                continue
        raise RuntimeError("Unable to append image")

    @staticmethod
    def _cleanup_text_output(text: Any) -> str:
        if isinstance(text, str):
            out = text
        elif text is None:
            out = ""
        elif isinstance(text, (tuple, list)):
            out = "".join(str(x) for x in text)
        else:
            out = str(text)
        cleaned = out.strip()
        for tok in ("</s>", "<|eot_id|>", "<|endoftext|>"):
            cleaned = cleaned.replace(tok, "")
        return cleaned.strip()

    @staticmethod
    def _parse_messages(
        messages: List[Dict[str, Any]],
    ) -> List[Tuple[str, Optional[str], Optional[np.ndarray]]]:
        events: List[Tuple[str, Optional[str], Optional[np.ndarray]]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "user"))
            content = msg.get("content")

            if isinstance(content, str):
                text = content.strip()
                if text:
                    events.append((role, text, None))
            elif isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get("type")
                    if part_type == "text" and isinstance(part.get("text"), str):
                        text = part["text"].strip()
                        if text:
                            events.append((role, text, None))
                    elif part_type == "image_url":
                        image = NanoLLMBridge._decode_any_image(part.get("image_url"))
                        if image is not None:
                            events.append((role, None, image))
            elif isinstance(content, dict):
                image = NanoLLMBridge._decode_any_image(content.get("image_url"))
                if image is not None:
                    events.append((role, None, image))

            images = msg.get("images")
            if isinstance(images, list):
                for item in images:
                    image = NanoLLMBridge._decode_any_image(item)
                    if image is not None:
                        events.append((role, None, image))
        return events

    def chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        messages = payload.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")

        max_tokens = int(payload.get("max_tokens", 128) or 128)
        events = self._parse_messages(messages)
        if not events:
            raise ValueError("No usable content in messages")

        with self.lock:
            chat = self._new_chat_history()
            text_count = 0
            image_count = 0
            for role, text, image in events:
                if text is not None:
                    self._append_text(chat, role=role, text=text)
                    text_count += 1
                elif image is not None:
                    self._append_image(chat, role=role, image_rgb=image)
                    image_count += 1

            response_format = payload.get("response_format")
            if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
                self._append_text(
                    chat,
                    role="user",
                    text="Return only a valid JSON object. Do not include markdown.",
                )

            print(
                "[server][request] "
                f"text_parts={text_count} images={image_count} max_tokens={max_tokens}"
            )
            embedded = chat.embed_chat()
            embedding = embedded[0] if isinstance(embedded, (tuple, list)) else embedded
            generated = self._model.generate(
                embedding,
                streaming=False,
                max_new_tokens=max_tokens,
            )

        content = self._cleanup_text_output(generated)
        now = int(time.time())
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": now,
            "model": str(payload.get("model", self.model_name)),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


class Handler(BaseHTTPRequestHandler):
    bridge: NanoLLMBridge = None  # type: ignore

    def _send_json(self, status: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(
                200,
                {
                    "ok": True,
                    "model": self.bridge.model_name,
                    "api": self.bridge.api,
                    "vision_api": self.bridge.vision_api,
                },
            )
            return
        if self.path == "/v1/models":
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [{"id": self.bridge.model_name, "object": "model"}],
                },
            )
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "invalid_json"})
            return

        try:
            response = self.bridge.chat_completion(payload)
            self._send_json(200, response)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            print(f"[server][error] {exc}")
            print(traceback.format_exc())
            self._send_json(500, {"error": str(exc)})

    def log_message(self, format: str, *args) -> None:
        _ = format, args


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple NanoLLM OpenAI-compatible server")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--model", type=str, default="Efficient-Large-Model/VILA1.5-3b")
    parser.add_argument("--api", type=str, default="mlc")
    parser.add_argument("--vision-api", type=str, default="auto")
    parser.add_argument("--max-context-len", type=int, default=256)
    args = parser.parse_args()

    bridge = NanoLLMBridge(
        model=args.model,
        api=args.api,
        vision_api=args.vision_api,
        max_context_len=args.max_context_len,
    )
    Handler.bridge = bridge
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[server] listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
