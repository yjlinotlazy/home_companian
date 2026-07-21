from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from datetime import datetime, time
from threading import Lock
from urllib.parse import parse_qs, quote, urlencode, urlparse

from .checklists import ChecklistItem
from .config import ConfigError, FontChoice, load_config
from .devices import get_device_profile
from .service import DisplayService, RenderedDisplay, RewardStatus


DISPLAY_BIN_DEVICE_ID = "wall_panel"


@dataclass(frozen=True)
class DevicePage:
    id: str
    profile_id: str
    width: int
    height: int
    confirmed: bool
    item_controls: bool = True


def device_preview_png(rendered: RenderedDisplay) -> bytes:
    """Return the logical display image for browser preview."""
    output = BytesIO()
    rendered.image.convert("L").save(output, format="PNG")
    return output.getvalue()


def reward_payload(status: RewardStatus) -> dict[str, object]:
    return {
        "id": status.reward.id,
        "name": status.reward.name,
        "cost": status.reward.cost,
        "score": status.score,
        "redeemable": status.redeemable,
    }


def index_html(
    fonts: tuple[FontChoice, ...],
    selected_font: Path,
    latin_fonts: tuple[FontChoice, ...],
    selected_latin_font: Path,
    devices: tuple[DevicePage, ...],
    checklist_items: tuple[tuple[str, ChecklistItem, bool], ...] = (),
    reward_status: RewardStatus | None = None,
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

    def render_device(device: DevicePage) -> str:
        device_id = escape(device.id, quote=True)
        encoded_id = quote(device.id, safe="")
        label = escape(device_label(device.id, device.profile_id))
        unconfirmed = " hidden" if device.confirmed else ""
        controls = ""
        if device.item_controls:
            controls = f"""<div class="controls-grid">
        <div>随机预览 <button type="button" data-action="random-preview">换一个</button>
        <button type="button" data-action="change" disabled>更改</button>
        <span data-change-status></span></div>
        <div><label>定时预览 <input type="time" data-preview-time value="{current_time}"></label>
        <button type="button" data-action="time-preview">预览</button></div>
      </div>"""
        return f"""<section class="device-section" data-device-id="{device_id}"
         style="--device-width:{device.width}px">
  <h2>{label} <small>{device_id}</small></h2>
  <div class="display-layout">
    <div class="display-main">
      <img class="device-preview" data-current-preview
           src="/v1/devices/{encoded_id}/preview.png"
           width="{device.width}" height="{device.height}"
           alt="{label} display preview">
      <p data-unconfirmed{unconfirmed}>设备尚未确认显示画面</p>
      {controls}
    </div>
    <aside class="next-refresh">
      <span>下次刷新：<span data-next-refresh-time>加载中</span></span>
      <img data-next-preview alt="{label} next frame preview">
    </aside>
  </div>
</section>"""

    device_sections = '<hr class="device-divider">'.join(
        render_device(device) for device in devices
    )
    grouped_checklists: dict[str, list[tuple[ChecklistItem, bool]]] = {}
    for group, item, completed in checklist_items:
        grouped_checklists.setdefault(group, []).append((item, completed))
    checklist_groups = "".join(
        f'<fieldset><legend>{escape(group)}</legend>'
        + "".join(
            f'<label><input type="checkbox" data-checklist-id="{item.id}"'
            f'{" checked" if completed else ""}> {escape(item.text)}</label>'
            for item, completed in items
        )
        + "</fieldset>"
        for group, items in grouped_checklists.items()
    )
    reward_controls = ""
    if reward_status is not None:
        reward = reward_status.reward
        disabled = "" if reward_status.redeemable else " disabled"
        reward_controls = f"""<div class="reward-control" data-reward-id="{escape(reward.id, quote=True)}">
<span>{escape(reward.name)}</span>
<progress data-reward-progress max="{reward.cost}" value="{reward_status.score}"></progress>
<button type="button" data-action="redeem-reward"{disabled}>兑换</button>
</div>"""
    checklist_controls = f"""<section class="checklist-controls">
<h2>今日清单</h2>
<div class="checklist-grid">{checklist_groups}</div>
{reward_controls}
<p data-checklist-status></p>
</section>"""
    font_controls = f"""<section class="font-controls">
<h2>全局字体</h2>
<div class="controls-grid">
  <div><label>中文字体 <select id="chinese-font-select">{chinese_options}</select></label>
  <button type="button" data-font-apply="chinese">应用</button>
  <span id="chinese-font-status"></span></div>
  <div><label>英文字体 <select id="latin-font-select">{latin_options}</select></label>
  <button type="button" data-font-apply="latin">应用</button>
  <span id="latin-font-status"></span></div>
</div>
</section>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Home Companian</title>
<style>
.display-layout {{ display:grid; grid-template-columns:minmax(0,var(--device-width)) 160px; gap:1rem; align-items:start; }}
.display-main {{ max-width:var(--device-width); }}
.controls-grid {{ display:grid; grid-template-columns:minmax(0,1fr); gap:.75rem; margin-top:1rem; }}
.controls-grid > div {{ min-width:0; }}
.next-refresh {{ display:grid; gap:.5rem; }}
.next-refresh img {{ width:160px; height:auto; border:1px solid #aaa; }}
.device-divider {{ margin:2.5rem 0; border:0; border-top:1px solid #999; }}
.device-preview {{ display:block; width:100%; height:auto; border:1px solid #888; }}
.device-section small {{ font-size:.55em; font-weight:normal; color:#555; }}
.font-controls {{ margin-top:2.5rem; }}
.checklist-controls {{ margin-top:2rem; width:fit-content; max-width:100%; }}
.checklist-grid {{ display:grid; grid-template-columns:repeat(3,minmax(140px,190px)); gap:.5rem; justify-content:start; }}
.checklist-grid fieldset {{ display:grid; gap:.3rem; margin:0; padding:.35rem .55rem .5rem; }}
.checklist-grid label {{ white-space:nowrap; }}
.reward-control {{ display:grid; grid-template-columns:auto 150px auto; gap:.5rem; align-items:center; margin-top:.65rem; width:fit-content; }}
.reward-control progress {{ width:150px; }}
@media (max-width: 760px) {{
  .display-layout {{ grid-template-columns:minmax(0,1fr); }}
  .checklist-grid {{ grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); }}
}}
</style></head>
<body style="font-family:sans-serif;margin:2rem;background:#eee">
  <h1>Home Companian</h1>
  {device_sections}
  {checklist_controls}
  {font_controls}
<script>
const nextRefreshTimers = new Map();

function devicePath(section, action) {{
  return '/v1/devices/' + encodeURIComponent(section.dataset.deviceId) + '/' + action;
}}

function refreshed(url) {{
  return url + (url.includes('?') ? '&' : '?') + 'refresh=' + Date.now();
}}

async function preview(section, query) {{
  const response = await fetch(devicePath(section, 'preview-selection') + '?' + query);
  if (!response.ok) throw new Error(await response.text());
  const selection = await response.json();
  section.dataset.previewItemId = selection.item_id;
  section.querySelector('[data-current-preview]').src = refreshed(selection.image_url);
  section.querySelector('[data-action="change"]').disabled = false;
  section.querySelector('[data-change-status]').textContent = '仅预览';
}}

async function loadNextRefresh(section) {{
  const response = await fetch(devicePath(section, 'next-refresh'));
  if (!response.ok) throw new Error(await response.text());
  const result = await response.json();
  const nextAt = new Date(result.next_at);
  section.querySelector('[data-next-refresh-time]').textContent = nextAt.toLocaleString('zh-CN', {{
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }});
  section.querySelector('[data-next-preview]').src = refreshed(result.image_url);
  const delay = Math.max(1000, nextAt.getTime() - Date.now() + 5000);
  window.clearTimeout(nextRefreshTimers.get(section.dataset.deviceId));
  nextRefreshTimers.set(
    section.dataset.deviceId,
    window.setTimeout(() => loadNextRefresh(section), delay)
  );
}}

document.querySelectorAll('.device-section').forEach(section => {{
  const randomButton = section.querySelector('[data-action="random-preview"]');
  if (randomButton) {{
    randomButton.addEventListener('click', () => preview(section, 'mode=random'));
    section.querySelector('[data-action="time-preview"]').addEventListener('click', () => {{
      const value = section.querySelector('[data-preview-time]').value;
      if (value) preview(section, 'time=' + encodeURIComponent(value));
    }});
    section.querySelector('[data-action="change"]').addEventListener('click', async () => {{
      const itemId = section.dataset.previewItemId;
      if (!itemId) return;
      const response = await fetch(
        devicePath(section, 'change') + '?item=' + encodeURIComponent(itemId),
        {{method: 'POST'}}
      );
      if (!response.ok) throw new Error(await response.text());
      delete section.dataset.previewItemId;
      section.querySelector('[data-action="change"]').disabled = true;
      section.querySelector('[data-change-status]').textContent = '已设为下次刷新';
      loadNextRefresh(section);
    }});
  }}
  loadNextRefresh(section);
}});

document.querySelectorAll('[data-checklist-id]').forEach(checkbox => {{
  checkbox.addEventListener('change', async () => {{
    const response = await fetch('/v1/checklists/' + checkbox.dataset.checklistId, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{completed: checkbox.checked}})
    }});
    if (!response.ok) {{
      checkbox.checked = !checkbox.checked;
      throw new Error(await response.text());
    }}
    const result = await response.json();
    updateReward(result.reward);
    document.querySelector('[data-checklist-status]').textContent = '已保存；Kindle 下次唤醒时更新';
    document.querySelectorAll('.device-section').forEach(loadNextRefresh);
  }});
}});

function updateReward(reward) {{
  if (!reward) return;
  const control = document.querySelector('[data-reward-id]');
  if (!control) return;
  control.querySelector('[data-reward-progress]').value = reward.score;
  control.querySelector('[data-action="redeem-reward"]').disabled = !reward.redeemable;
}}

document.querySelectorAll('[data-action="redeem-reward"]').forEach(button => {{
  button.addEventListener('click', async () => {{
    const control = button.closest('[data-reward-id]');
    const rewardId = encodeURIComponent(control.dataset.rewardId);
    const response = await fetch('/v1/rewards/' + rewardId + '/redeem', {{method: 'POST'}});
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    updateReward(result.reward);
    document.querySelector('[data-checklist-status]').textContent = '已兑换；积分已清零';
    document.querySelectorAll('.device-section').forEach(loadNextRefresh);
  }});
}});

document.querySelectorAll('[data-font-apply]').forEach(button => {{
  button.addEventListener('click', async () => {{
    const group = button.dataset.fontApply;
    const name = document.querySelector('#' + group + '-font-select').value;
    const query = 'group=' + encodeURIComponent(group) + '&name=' + encodeURIComponent(name);
    const response = await fetch('/font?' + query, {{method: 'POST'}});
    if (!response.ok) throw new Error(await response.text());
    document.querySelector('#' + group + '-font-status').textContent = '已应用';
    document.querySelectorAll('.device-section').forEach(loadNextRefresh);
  }});
}});
</script>
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


def parse_checklist_route(path: str) -> int | None:
    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[:2] != ["v1", "checklists"]:
        return None
    try:
        item_id = int(parts[2])
    except ValueError as exc:
        raise ValueError("checklist item id must be a positive integer") from exc
    if item_id <= 0:
        raise ValueError("checklist item id must be a positive integer")
    return item_id


def parse_reward_route(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) != 4 or parts[:2] != ["v1", "rewards"] or parts[3] != "redeem":
        return None
    if not parts[2]:
        raise ValueError("reward id must be provided")
    return parts[2]


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

    def refresh_prepared_checklists(self) -> None:
        configured = load_config(self.config_path)
        for device in configured.devices:
            self.get(device.id).refresh_prepared_checklists()


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
                selection_device_id = parse_device_route(
                    request.path, "preview-selection"
                )
                next_refresh_device_id = parse_device_route(
                    request.path, "next-refresh"
                )
                next_preview_device_id = parse_device_route(
                    request.path, "next-preview.png"
                )
                next_device_id = parse_device_route(request.path, "next")
                if preview_device_id is not None:
                    device_service = device_services.get(preview_device_id)
                    preview_time = parse_preview_time(request.query)
                    preview_random = is_random_preview(request.query)
                    preview_item_id = parse_item_id(request.query)
                    temporary = (
                        preview_time is not None
                        or preview_random
                        or preview_item_id is not None
                    )
                    if temporary:
                        rendered = device_service.render(
                            preview_time=preview_time,
                            preview_random=preview_random,
                            preview_item_id=preview_item_id,
                        )
                        confirmed = False
                    else:
                        rendered = device_service.render_current()
                        confirmed = rendered is not None
                        if rendered is None:
                            rendered = device_service.preview_next_delivery()
                    self._send(
                        HTTPStatus.OK,
                        "image/png",
                        device_preview_png(rendered),
                        {"X-Display-Confirmed": "true" if confirmed else "false"},
                    )
                elif selection_device_id is not None:
                    device_service = device_services.get(selection_device_id)
                    preview_time = parse_preview_time(request.query)
                    rendered = device_service.render(
                        preview_time=preview_time,
                        preview_random=is_random_preview(request.query),
                    )
                    image_query = {"item": rendered.item_id}
                    if preview_time is not None:
                        image_query["time"] = preview_time.strftime("%H:%M")
                    encoded_id = quote(selection_device_id, safe="")
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "item_id": rendered.item_id,
                            "image_url": (
                                f"/v1/devices/{encoded_id}/preview.png?"
                                f"{urlencode(image_query)}"
                            ),
                        },
                    )
                elif next_refresh_device_id is not None:
                    device_service = device_services.get(next_refresh_device_id)
                    now = datetime.now()
                    rendered = device_service.preview_next_delivery(now)
                    encoded_id = quote(next_refresh_device_id, safe="")
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "next_at": device_service.next_check_at(now).isoformat(),
                            "item_id": rendered.item_id,
                            "image_url": (
                                f"/v1/devices/{encoded_id}/next-preview.png"
                            ),
                        },
                    )
                elif next_preview_device_id is not None:
                    rendered = device_services.get(
                        next_preview_device_id
                    ).preview_next_delivery()
                    self._send(
                        HTTPStatus.OK,
                        "image/png",
                        device_preview_png(rendered),
                    )
                elif next_device_id is not None:
                    device_service = device_services.get(next_device_id)
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
                                DevicePage(
                                    id=device.id,
                                    profile_id=device.profile,
                                    width=get_device_profile(device.profile).width,
                                    height=get_device_profile(device.profile).height,
                                    confirmed=(
                                        device_services.get(
                                            device.id
                                        ).render_current()
                                        is not None
                                    ),
                                    item_controls=any(
                                        slot.module == "items"
                                        for panel in device.presentation.panels
                                        for slot in panel.slots
                                    ),
                                )
                                for device in config.devices
                            ),
                            service.checklist_items(),
                            service.reward_status(),
                        ),
                    )
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
                ack_device_id = parse_device_route(request.path, "ack")
                change_device_id = parse_device_route(request.path, "change")
                checklist_item_id = parse_checklist_route(request.path)
                reward_id = parse_reward_route(request.path)
                if ack_device_id is not None:
                    body = self._read_json()
                    frame_id = body.get("frame_id")
                    status = body.get("status")
                    if not isinstance(frame_id, str) or not frame_id:
                        raise ValueError("frame_id must be provided")
                    if not isinstance(status, str):
                        raise ValueError("ack status must be provided")
                    device_services.get(ack_device_id).acknowledge(frame_id, status)
                    self._send_json(HTTPStatus.OK, {"frame_id": frame_id, "status": status})
                elif change_device_id is not None:
                    item_id = parse_item_id(request.query)
                    if item_id is None:
                        raise ValueError("item must be provided")
                    next_at = device_services.get(change_device_id).change(item_id)
                    self._send_json(
                        HTTPStatus.OK,
                        {"item_id": item_id, "next_at": next_at.isoformat()},
                    )
                elif checklist_item_id is not None:
                    body = self._read_json()
                    completed = body.get("completed")
                    if type(completed) is not bool:
                        raise ValueError("completed must be a boolean")
                    service.set_checklist_completed(checklist_item_id, completed)
                    device_services.refresh_prepared_checklists()
                    status = service.reward_status()
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "item_id": checklist_item_id,
                            "completed": completed,
                            "reward": reward_payload(status),
                        },
                    )
                elif reward_id is not None:
                    status = service.redeem_reward(reward_id)
                    device_services.refresh_prepared_checklists()
                    self._send_json(
                        HTTPStatus.OK,
                        {"reward": reward_payload(status)},
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
