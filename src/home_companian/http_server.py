from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import ConfigError
from .service import DisplayService


INDEX_HTML = b"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Home Companian</title></head>
<body style="font-family:sans-serif;margin:2rem;background:#eee">
  <h1>Home Companian</h1>
  <p><a href="/">Refresh</a> | <a href="/display.bin">Download framebuffer</a></p>
  <img src="/preview.png" width="792" height="272" alt="e-paper preview" style="max-width:100%;height:auto;border:1px solid #888">
</body>
</html>
"""


def parse_battery(query: str) -> int | None:
    values = parse_qs(query).get("battery")
    if not values:
        return None
    try:
        battery = int(values[0])
    except ValueError as exc:
        raise ValueError("battery must be an integer from 0 to 100") from exc
    if not 0 <= battery <= 100:
        raise ValueError("battery must be an integer from 0 to 100")
    return battery


def make_handler(service: DisplayService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlparse(self.path)
            try:
                battery = parse_battery(request.query)
                if request.path == "/":
                    self._send(HTTPStatus.OK, "text/html; charset=utf-8", INDEX_HTML)
                elif request.path == "/preview.png":
                    rendered = service.render(battery)
                    output = BytesIO()
                    rendered.image.save(output, format="PNG")
                    self._send(HTTPStatus.OK, "image/png", output.getvalue())
                elif request.path == "/display.bin":
                    rendered = service.render(battery)
                    self._send(HTTPStatus.OK, "application/octet-stream", rendered.framebuffer)
                else:
                    self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
            except ConfigError as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8", f"{exc}\n".encode())
            except ValueError as exc:
                self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", f"{exc}\n".encode())

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(host: str, port: int, config_path: Path) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(DisplayService(config_path)))
