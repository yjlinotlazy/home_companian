from __future__ import annotations

import json
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from datetime import datetime, time
from threading import Lock
from urllib.parse import parse_qs, quote, urlencode, urlparse

from .config import ConfigError, FontChoice, load_config
from .service import DisplayService


DISPLAY_BIN_DEVICE_ID = "wall_panel"


def index_html(
    fonts: tuple[FontChoice, ...],
    selected_font: Path,
    latin_fonts: tuple[FontChoice, ...],
    selected_latin_font: Path,
    devices: tuple[tuple[str, str], ...],
    default_device: str,
) -> bytes:
    current_time = datetime.now().strftime("%H:%M")
    def font_options(choices: tuple[FontChoice, ...], selected: Path | None) -> str:
        return "".join(
            f'<option value="{escape(choice.name, quote=True)}"'
            f'{" selected" if choice.path == selected else ""}>'
            f'{escape(choice.name)}</option>'
            for choice in choices
        )

    chinese_options = font_options(fonts, selected_font)
    latin_options = font_options(latin_fonts, selected_latin_font)
    def device_label(device_id: str, profile_id: str) -> str:
        if profile_id.startswith("crowpanel"):
            return "CrowPanel"
        if profile_id.startswith("kindle"):
            return "Kindle"
        return device_id

    configured_devices = devices
    selected_device = default_device
    selected_profile = next(
        profile_id
        for device_id, profile_id in configured_devices
        if device_id == selected_device
    )
    default_label = device_label(selected_device, selected_profile)
    secondary_sections = "".join(
        f"""<hr class="device-divider">
<section class="device-section">
  <h2>{escape(device_label(device_id, profile_id))}</h2>
  <img class="device-preview portrait-preview"
       src="/v1/devices/{quote(device_id, safe='')}/preview.png"
       onerror="this.hidden=true;this.nextElementSibling.hidden=false"
       alt="{escape(device_label(device_id, profile_id))} current display">
  <p hidden>设备尚未确认显示画面</p>
</section>"""
        for device_id, profile_id in configured_devices
        if device_id != selected_device
    )
    controls = f"""<div class="controls-grid">
<div>随机预览 <button type="button" id="random-refresh">换一个</button>
<button type="button" id="global-change" disabled>更改</button> <span id="change-status"></span></div>
<div><label>定时预览 <input type="time" id="preview-time" value="{current_time}"></label>
<button type="button" id="time-preview">预览</button></div>
<div><label>中文字体 <select id="chinese-font-select">{chinese_options}</select></label>
<button type="button" data-font-apply="chinese">应用</button> <span id="chinese-font-status"></span></div>
<div><label>英文字体 <select id="latin-font-select">{latin_options}</select></label>
<button type="button" data-font-apply="latin">应用</button> <span id="latin-font-status"></span></div>
</div>
<script>
let previewItemId = null;
let nextRefreshTimer = null;
async function preview(query) {{
  const response = await fetch('/preview-selection?' + query);
  if (!response.ok) throw new Error(await response.text());
  const selection = await response.json();
  previewItemId = selection.item_id;
  document.querySelector('#preview').src = selection.image_url + '&refresh=' + Date.now();
  document.querySelector('#global-change').disabled = false;
  document.querySelector('#change-status').textContent = '仅预览';
}}
document.querySelector('#random-refresh').addEventListener('click', async () => {{
  await preview('mode=random');
}});
document.querySelector('#time-preview').addEventListener('click', async () => {{
  const value = document.querySelector('#preview-time').value;
  if (value) await preview('time=' + encodeURIComponent(value));
}});
document.querySelector('#global-change').addEventListener('click', async () => {{
  if (previewItemId === null) return;
  const response = await fetch('/change?item=' + previewItemId, {{method: 'POST'}});
  if (!response.ok) throw new Error(await response.text());
  const result = await response.json();
  previewItemId = null;
  document.querySelector('#global-change').disabled = true;
  document.querySelector('#change-status').textContent = '已设为下次刷新';
  loadNextRefresh();
}});
document.querySelectorAll('[data-font-apply]').forEach(button => {{
  button.addEventListener('click', async () => {{
    const group = button.dataset.fontApply;
    const name = document.querySelector('#' + group + '-font-select').value;
    const query = 'group=' + encodeURIComponent(group) + '&name=' + encodeURIComponent(name);
    const response = await fetch('/font?' + query, {{method: 'POST'}});
    if (!response.ok) throw new Error(await response.text());
    document.querySelector('#' + group + '-font-status').textContent = '已应用';
    document.querySelector('#preview').src = '/preview.png?refresh=' + Date.now();
    loadNextRefresh();
  }});
}});
async function loadNextRefresh() {{
  const response = await fetch('/next-refresh');
  if (!response.ok) throw new Error(await response.text());
  const result = await response.json();
  const nextAt = new Date(result.next_at);
  document.querySelector('#next-refresh-time').textContent = nextAt.toLocaleString('zh-CN', {{
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }});
  document.querySelector('#next-preview').src = result.image_url + '?refresh=' + Date.now();
  const delay = Math.max(1000, nextAt.getTime() - Date.now() + 5000);
  window.clearTimeout(nextRefreshTimer);
  nextRefreshTimer = window.setTimeout(loadNextRefresh, delay);
}}
window.addEventListener('DOMContentLoaded', loadNextRefresh);
</script>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Home Companian</title>
<style>
.display-layout {{ display:grid; grid-template-columns:minmax(0,792px) 160px; gap:1rem; align-items:start; }}
.main-preview {{ width:100%; height:auto; border:1px solid #888; }}
.controls-grid {{ display:grid; grid-template-columns:minmax(0,1fr); gap:.75rem; margin-top:1rem; }}
.controls-grid > div {{ min-width:0; }}
.next-refresh {{ display:grid; gap:.5rem; }}
.next-refresh img {{ width:160px; height:auto; border:1px solid #aaa; }}
.device-divider {{ margin:2.5rem 0; border:0; border-top:1px solid #999; }}
.device-preview {{ display:block; width:100%; height:auto; border:1px solid #888; }}
.portrait-preview {{ max-width:758px; }}
@media (max-width: 760px) {{ .display-layout {{ grid-template-columns:minmax(0,1fr); }} }}
</style></head>
<body style="font-family:sans-serif;margin:2rem;background:#eee">
  <h1>Home Companian</h1>
  <h2>{escape(default_label)}</h2>
  <div class="display-layout">
    <div>
      <img class="main-preview" id="preview" src="/preview.png" width="792" height="272" alt="e-paper preview">
      {controls}
    </div>
    <aside class="next-refresh">
      <span>下次刷新：<span id="next-refresh-time">加载中</span></span>
      <img id="next-preview" alt="next e-paper preview">
    </aside>
  </div>
  {secondary_sections}
</body>
</html>
""".encode("utf-8")


def parse_preview_time(query: str) -> time | None:
    values = parse_qs(query).get("time")
    if not values:
        return None
    try:
        return datetime.strptime(values[0], "%H:%M").time()
    except ValueError as exc:
        raise ValueError("time must use HH:MM") from exc


def is_random_preview(query: str) -> bool:
    return parse_qs(query).get("mode", [None])[0] == "random"


def parse_item_id(query: str) -> int | None:
    values = parse_qs(query).get("item")
    if not values:
        return None
    try:
        item_id = int(values[0])
    except ValueError as exc:
        raise ValueError("item must be a positive integer") from exc
    if item_id <= 0:
        raise ValueError("item must be a positive integer")
    return item_id


def parse_font_name(query: str) -> str | None:
    values = parse_qs(query).get("name")
    if not values or not values[0].strip():
        return None
    return values[0].strip()


def parse_device_route(path: str, action: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[:2] == ["v1", "devices"] and parts[3] == action:
        return parts[2] or None
    return None


class DeviceServices:
    def __init__(self, config_path: Path, default_service: DisplayService) -> None:
        self.config_path = config_path
        self._lock = Lock()
        default_device = default_service.settings().device_id
        self._services = {default_device: default_service}

    def get(self, device_id: str) -> DisplayService:
        configured = load_config(self.config_path)
        if device_id not in {device.id for device in configured.devices}:
            raise KeyError(device_id)
        with self._lock:
            service = self._services.get(device_id)
            if service is None:
                service = DisplayService(self.config_path, device_id=device_id)
                self._services[device_id] = service
            return service


def make_handler(
    service: DisplayService,
    device_services: DeviceServices | None = None,
) -> type[BaseHTTPRequestHandler]:
    device_services = device_services or DeviceServices(service.config_path, service)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlparse(self.path)
            try:
                preview_device_id = parse_device_route(request.path, "preview.png")
                device_id = parse_device_route(request.path, "next")
                if preview_device_id is not None:
                    device_service = device_services.get(preview_device_id)
                    rendered = device_service.render_current()
                    if rendered is None:
                        self._send(
                            HTTPStatus.NOT_FOUND,
                            "text/plain; charset=utf-8",
                            "设备尚未确认显示画面\n".encode(),
                        )
                        return
                    output = BytesIO()
                    rendered.image.save(output, format="PNG")
                    self._send(HTTPStatus.OK, "image/png", output.getvalue())
                elif device_id is not None:
                    device_service = device_services.get(device_id)
                    rendered = device_service.deliver()
                    self._send(
                        HTTPStatus.OK,
                        rendered.frame.mime_type,
                        rendered.frame.payload,
                        {
                            "ETag": f'"{rendered.frame.id}"',
                            "X-Frame-Id": rendered.frame.id,
                            "X-Scene-Id": rendered.frame.scene_id,
                            "X-Profile-Id": rendered.frame.profile_id,
                            "X-Next-Check-Seconds": str(
                                device_service.next_check_seconds()
                            ),
                        },
                    )
                elif request.path == "/":
                    config = service.config()
                    settings = config.for_device(config.default_device)
                    self._send(
                        HTTPStatus.OK,
                        "text/html; charset=utf-8",
                        index_html(
                            settings.fonts,
                            settings.font,
                            settings.latin_fonts,
                            settings.latin_font,
                            tuple(
                                (device.id, device.profile)
                                for device in config.devices
                            ),
                            config.default_device,
                        ),
                    )
                elif request.path == "/preview.png":
                    preview_time = parse_preview_time(request.query)
                    preview_random = is_random_preview(request.query)
                    preview_item_id = parse_item_id(request.query)
                    if preview_time is not None or preview_random or preview_item_id is not None:
                        rendered = service.render(
                            preview_time=preview_time,
                            preview_random=preview_random,
                            preview_item_id=preview_item_id,
                        )
                    else:
                        rendered = service.render_current()
                        if rendered is None:
                            self._send(
                                HTTPStatus.NOT_FOUND,
                                "text/plain; charset=utf-8",
                                "设备尚未请求过画面\n".encode(),
                            )
                            return
                    output = BytesIO()
                    rendered.image.save(output, format="PNG")
                    self._send(HTTPStatus.OK, "image/png", output.getvalue())
                elif request.path == "/preview-selection":
                    preview_time = parse_preview_time(request.query)
                    rendered = service.render(
                        preview_time=preview_time,
                        preview_random=is_random_preview(request.query),
                    )
                    image_query = {"item": rendered.item_id}
                    if preview_time is not None:
                        image_query["time"] = preview_time.strftime("%H:%M")
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "item_id": rendered.item_id,
                            "image_url": f"/preview.png?{urlencode(image_query)}",
                        },
                    )
                elif request.path == "/next-refresh":
                    now = datetime.now()
                    rendered = service.render_next(now)
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "next_at": service.next_check_at(now).isoformat(),
                            "item_id": rendered.item_id,
                            "image_url": "/next-preview.png",
                        },
                    )
                elif request.path == "/next-preview.png":
                    rendered = service.render_next()
                    output = BytesIO()
                    rendered.image.save(output, format="PNG")
                    self._send(HTTPStatus.OK, "image/png", output.getvalue())
                elif request.path == "/display.bin":
                    crowpanel_service = device_services.get(DISPLAY_BIN_DEVICE_ID)
                    rendered = crowpanel_service.render(device=True)
                    self._send(
                        HTTPStatus.OK,
                        "application/octet-stream",
                        rendered.frame.payload,
                        {
                            "X-Next-Check-Seconds": str(
                                crowpanel_service.next_check_seconds()
                            )
                        },
                    )
                else:
                    self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
            except KeyError:
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"unknown device\n")
            except ConfigError as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8", f"{exc}\n".encode())
            except ValueError as exc:
                self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", f"{exc}\n".encode())

        def do_POST(self) -> None:
            request = urlparse(self.path)
            try:
                device_id = parse_device_route(request.path, "ack")
                if device_id is not None:
                    body = self._read_json()
                    frame_id = body.get("frame_id")
                    status = body.get("status")
                    if not isinstance(frame_id, str) or not frame_id:
                        raise ValueError("frame_id must be provided")
                    if not isinstance(status, str):
                        raise ValueError("ack status must be provided")
                    device_services.get(device_id).acknowledge(frame_id, status)
                    self._send_json(HTTPStatus.OK, {"frame_id": frame_id, "status": status})
                elif request.path == "/change":
                    item_id = parse_item_id(request.query)
                    if item_id is None:
                        raise ValueError("item must be provided")
                    next_at = service.change(item_id)
                    self._send_json(
                        HTTPStatus.OK,
                        {"item_id": item_id, "next_at": next_at.isoformat()},
                    )
                elif request.path == "/font":
                    group = parse_qs(request.query).get("group", [None])[0]
                    if group is None:
                        raise ValueError("font group must be provided")
                    name = parse_font_name(request.query)
                    if name is None:
                        raise ValueError("font name must be provided")
                    path = service.select_font(group, name)
                    self._send_json(
                        HTTPStatus.OK,
                        {"group": group, "name": name, "path": str(path)},
                    )
                else:
                    self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")
            except KeyError:
                self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"unknown device\n")
            except ConfigError as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8", f"{exc}\n".encode())
            except ValueError as exc:
                self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8", f"{exc}\n".encode())

        def _read_json(self) -> dict[str, object]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length <= 0 or length > 64 * 1024:
                raise ValueError("JSON body must be provided")
            try:
                value = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("invalid JSON body") from exc
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def _send_json(self, status: HTTPStatus, value: object) -> None:
            self._send(
                status,
                "application/json; charset=utf-8",
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )

        def _send(
            self,
            status: HTTPStatus,
            content_type: str,
            body: bytes,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(host: str, port: int, config_path: Path) -> ThreadingHTTPServer:
    default_service = DisplayService(config_path)
    device_services = DeviceServices(config_path, default_service)
    return ThreadingHTTPServer(
        (host, port),
        make_handler(default_service, device_services),
    )
