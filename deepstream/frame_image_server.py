#!/usr/bin/env python3
"""
Standalone frame image server:
- serves saved frame images at GET /<frame_uuid>
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib import parse as urllib_parse
import uuid


DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PORT = 8090
DEFAULT_FRAMES_DIR = "/mnt/nvme/frames"


def _detect_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        sock.close()
    return "127.0.0.1"


def _normalize_frame_uuid(raw_path_value: str) -> str:
    frame_uuid = raw_path_value.strip()
    if frame_uuid.lower().endswith(".jpg"):
        frame_uuid = frame_uuid[:-4]
    parsed = uuid.UUID(frame_uuid)
    return parsed.hex


def _resolve_frame_path(frames_dir: str, frame_uuid: str) -> str:
    frame_path = os.path.join(frames_dir, f"{frame_uuid}.jpg")
    if os.path.isfile(frame_path):
        return frame_path
    return ""


class FrameImageServer(ThreadingHTTPServer):
    def __init__(
        self,
        bind_host: str,
        port: int,
        frames_dir: str,
        advertised_host: str,
    ) -> None:
        super().__init__((bind_host, port), FrameImageHandler)
        self.frames_dir = frames_dir
        self.advertised_host = advertised_host
        self.port = int(port)


class FrameImageHandler(BaseHTTPRequestHandler):
    server_version = "FrameImageServer/1.0"

    @property
    def app(self) -> FrameImageServer:
        return self.server  # type: ignore[return-value]

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_json(
                200,
                {
                    "ok": True,
                    "host": self.app.advertised_host,
                    "port": self.app.port,
                    "frames_dir": self.app.frames_dir,
                },
            )
            return

        raw_frame_id = urllib_parse.unquote(path.lstrip("/")).strip()
        if not raw_frame_id:
            self._send_json(400, {"error": "frame_uuid is required in URL path"})
            return
        try:
            frame_uuid = _normalize_frame_uuid(raw_frame_id)
        except Exception:
            self._send_json(400, {"error": "invalid frame_uuid", "frame_uuid": raw_frame_id})
            return

        frame_path = _resolve_frame_path(self.app.frames_dir, frame_uuid)
        if not frame_path:
            self._send_json(404, {"error": "frame not found", "frame_uuid": frame_uuid})
            return

        try:
            with open(frame_path, "rb") as f:
                data = f.read()
        except Exception as exc:
            self._send_json(500, {"error": f"failed to read frame: {exc}"})
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        self._send_json(405, {"error": "POST not supported by this service"})

    def log_message(self, fmt: str, *args: Any) -> None:
        pass
        # print(f"[frame-image-server] {self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone frame image server by frame UUID.")
    parser.add_argument("--bind-host", type=str, default=DEFAULT_BIND_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--frames-dir", type=str, default=DEFAULT_FRAMES_DIR)
    parser.add_argument("--advertised-host", type=str, default="")
    args = parser.parse_args()

    os.makedirs(args.frames_dir, exist_ok=True)
    advertised_host = args.advertised_host.strip() or _detect_local_ip()

    server = FrameImageServer(
        bind_host=args.bind_host,
        port=int(args.port),
        frames_dir=args.frames_dir,
        advertised_host=advertised_host,
    )
    # print("=" * 60)
    # print("Frame image server running")
    # print(f"Bind         : {args.bind_host}:{args.port}")
    # print(f"Advertised   : {advertised_host}")
    # print(f"Frames dir   : {args.frames_dir}")
    # print("POST         : disabled")
    # print(f"Frame path   : /<frame_uuid>")
    # print(f"Link format  : {advertised_host}:{args.port}/<frame_uuid>")
    # print("=" * 60)
    server.serve_forever()


if __name__ == "__main__":
    main()
