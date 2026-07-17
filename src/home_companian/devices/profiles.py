from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    id: str
    width: int
    height: int
    status_bar_height: int
    encoder: str
    mime_type: str
    capabilities: tuple[str, ...] = ()
    ppi: int | None = None
    grayscale_levels: int = 2

    @property
    def content_height(self) -> int:
        return self.height - self.status_bar_height


CROWPANEL_579 = DeviceProfile(
    id="crowpanel_579",
    width=792,
    height=272,
    status_bar_height=44,
    encoder="crowpanel_1bit",
    mime_type="application/octet-stream",
    capabilities=("monochrome", "deep_sleep"),
)

KINDLE_6_212PPI = DeviceProfile(
    id="kindle_6_212ppi",
    width=758,
    height=1024,
    status_bar_height=48,
    encoder="png",
    mime_type="image/png",
    capabilities=("grayscale", "portrait", "touch"),
    ppi=212,
    grayscale_levels=16,
)


_PROFILES = {
    CROWPANEL_579.id: CROWPANEL_579,
    KINDLE_6_212PPI.id: KINDLE_6_212PPI,
}


def get_device_profile(profile_id: str) -> DeviceProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown device profile: {profile_id}") from exc
