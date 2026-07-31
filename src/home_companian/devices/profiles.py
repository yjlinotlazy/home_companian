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
    frame_rotation_degrees: int = 0

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
    frame_rotation_degrees=180,
)

KINDLE_6_167PPI = DeviceProfile(
    id="kindle_6_167ppi",
    width=600,
    height=800,
    status_bar_height=40,
    encoder="png",
    mime_type="image/png",
    capabilities=("grayscale", "portrait", "touch"),
    ppi=167,
    grayscale_levels=16,
)

KINDLE_6_167PPI_LANDSCAPE = DeviceProfile(
    id="kindle_6_167ppi_landscape",
    width=800,
    height=600,
    status_bar_height=40,
    encoder="png",
    mime_type="image/png",
    capabilities=("grayscale", "landscape", "touch"),
    ppi=167,
    grayscale_levels=16,
    frame_rotation_degrees=90,
)


_PROFILES = {
    CROWPANEL_579.id: CROWPANEL_579,
    KINDLE_6_167PPI.id: KINDLE_6_167PPI,
    KINDLE_6_167PPI_LANDSCAPE.id: KINDLE_6_167PPI_LANDSCAPE,
}


def get_device_profile(profile_id: str) -> DeviceProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown device profile: {profile_id}") from exc
