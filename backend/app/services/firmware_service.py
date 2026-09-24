"""Firmware service for WiCAN firmware update checking."""

import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.livelink_device import LiveLinkDevice
from app.models.livelink_firmware_cache import LiveLinkFirmwareCache
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# GitHub API endpoint for WiCAN firmware releases (plural — both tracks live here)
GITHUB_RELEASES_URL = "https://api.github.com/repos/meatpiHQ/wican-fw/releases"

# Minimum firmware version for HTTPS POST support
MIN_FIRMWARE_VERSION = "4.40"


class FirmwareService:
    """Service for WiCAN firmware version checking."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def check_firmware_updates(self) -> dict:
        """Refresh the latest STABLE firmware version for each track (obd/pro).

        Fetches the releases list (paginating up to 3 pages if a track has no
        stable release on the first), classifies each by tag, caches the
        highest stable version per track, and returns a per-track summary.
        """
        releases = await self._fetch_releases()
        if releases is None:
            return {"error": "Failed to fetch releases"}

        latest: dict[str, dict] = {}
        for rel in releases:
            if self._is_prerelease(rel):
                continue
            tag = rel.get("tag_name", "")
            version = self._extract_version(tag)
            if not version:
                continue
            track = self.classify_release_track(tag, rel.get("name", ""))
            current = latest.get(track)
            if current is None or self.compare_versions(version, current["latest_version"]) > 0:
                latest[track] = {
                    "latest_version": version,
                    "latest_tag": tag,
                    "release_url": rel.get("html_url", ""),
                    "release_notes": (rel.get("body") or "")[:2000] or None,
                }

        for track, info in latest.items():
            await self._upsert_cache(track, info)

        logger.info(
            "Firmware check complete: %s",
            ", ".join(f"{t}={i['latest_version']}" for t, i in latest.items())
            or "no stable releases",
        )
        return {"tracks": latest}

    async def _fetch_releases(self) -> list[dict] | None:
        """Fetch up to 3 pages of releases from GitHub (newest first)."""
        all_releases: list[dict] = []
        url: str | None = f"{GITHUB_RELEASES_URL}?per_page=30"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for _ in range(3):
                    if not url:
                        break
                    response = await client.get(
                        url,
                        headers={
                            "Accept": "application/vnd.github.v3+json",
                            "User-Agent": "MyGarage-LiveLink/1.0",
                        },
                    )
                    response.raise_for_status()
                    page = response.json()
                    if not page:
                        break
                    all_releases.extend(page)
                    # Stop early once both tracks have at least one stable release.
                    stable_tracks = {
                        self.classify_release_track(r.get("tag_name", ""), r.get("name", ""))
                        for r in all_releases
                        if not self._is_prerelease(r)
                    }
                    if {"obd", "pro"}.issubset(stable_tracks):
                        break
                    url = self._next_page_url(response.headers.get("link", ""))
        except httpx.HTTPStatusError as e:
            logger.error("GitHub API error: %s", e)
            return None
        except httpx.RequestError as e:
            logger.error("GitHub API request failed: %s", e)
            return None
        return all_releases

    @staticmethod
    def _next_page_url(link_header: str) -> str | None:
        """Extract the rel="next" URL from a GitHub Link header, if any."""
        for part in link_header.split(","):
            if 'rel="next"' in part:
                start = part.find("<")
                end = part.find(">")
                if start != -1 and end != -1:
                    return part[start + 1 : end]
        return None

    async def _upsert_cache(self, track: str, info: dict) -> None:
        """Insert or update the cache row for one track."""
        result = await self.db.execute(
            select(LiveLinkFirmwareCache).where(LiveLinkFirmwareCache.track == track)
        )
        cache = result.scalar_one_or_none()
        if cache is None:
            cache = LiveLinkFirmwareCache(track=track)
            self.db.add(cache)
        cache.latest_version = info["latest_version"]
        cache.latest_tag = info["latest_tag"]
        cache.release_url = info["release_url"]
        cache.release_notes = info["release_notes"]
        cache.checked_at = utc_now()
        await self.db.commit()

    async def get_cached_firmware_info(self, track: str = "pro") -> dict | None:
        """Get cached firmware info for a track (default 'pro')."""
        result = await self.db.execute(
            select(LiveLinkFirmwareCache).where(LiveLinkFirmwareCache.track == track)
        )
        cache = result.scalar_one_or_none()
        if not cache or not cache.latest_version:
            return None
        return {
            "latest_version": cache.latest_version,
            "latest_tag": cache.latest_tag,
            "release_url": cache.release_url,
            "release_notes": cache.release_notes,
            "checked_at": cache.checked_at,
            "firmware_track": cache.track,
        }

    def _extract_version(self, tag: str) -> str:
        """Extract version number from git tag.

        Examples:
            "v4.45p" -> "4.45"
            "v4.50" -> "4.50"
            "4.45p" -> "4.45"
        """
        # Remove 'v' prefix and 'p' suffix
        version = tag.strip().lstrip("v").rstrip("p")

        # Extract just the version number
        match = re.search(r"(\d+\.\d+(?:\.\d+)?)", version)
        return match.group(1) if match else version

    async def get_devices_needing_update(self) -> list[dict]:
        """Devices with an update available, each compared against its track."""
        result = await self.db.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.fw_version.isnot(None))
        )
        devices = result.scalars().all()

        cache_by_track: dict[str, dict | None] = {}
        out: list[dict] = []
        for device in devices:
            track = self.device_firmware_track(device.hw_version)
            if track is None:
                continue
            if track not in cache_by_track:
                cache_by_track[track] = await self.get_cached_firmware_info(track)
            cache_info = cache_by_track[track]
            if not cache_info:
                continue
            if self.compare_versions(device.fw_version, cache_info["latest_version"]) < 0:
                out.append(
                    {
                        "device_id": device.device_id,
                        "label": device.label,
                        "current_version": device.fw_version,
                        "latest_version": cache_info["latest_version"],
                        "release_url": cache_info.get("release_url"),
                        "sta_ip": device.sta_ip,
                        "firmware_track": track,
                        # Notification state for the daily job's notify-once /
                        # skip filtering; this method stays the pure "what
                        # needs an update" answer.
                        "notified_version": device.firmware_notified_version,
                        "skipped_version": device.firmware_skipped_version,
                    }
                )
        return out

    @staticmethod
    def compare_versions(version1: str, version2: str) -> int:
        """Compare two version strings.

        Returns:
            -1 if version1 < version2
            0 if version1 == version2
            1 if version1 > version2
        """
        # Extract just numbers
        v1_match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version1)
        v2_match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version2)

        if not v1_match or not v2_match:
            # Fall back to string comparison
            return (version1 > version2) - (version1 < version2)

        v1_parts = [int(v1_match.group(1)), int(v1_match.group(2)), int(v1_match.group(3) or 0)]
        v2_parts = [int(v2_match.group(1)), int(v2_match.group(2)), int(v2_match.group(3) or 0)]

        for p1, p2 in zip(v1_parts, v2_parts):
            if p1 < p2:
                return -1
            if p1 > p2:
                return 1

        return 0

    @staticmethod
    def is_firmware_compatible(version: str) -> bool:
        """Check if firmware version supports HTTPS POST.

        Args:
            version: Firmware version string

        Returns:
            True if version >= MIN_FIRMWARE_VERSION
        """
        return FirmwareService.compare_versions(version, MIN_FIRMWARE_VERSION) >= 0

    @staticmethod
    def classify_release_track(tag: str, title: str = "") -> str:
        """Classify a GitHub release as the 'obd' or 'pro' firmware track.

        PRO releases carry a ``p`` immediately after the numeric version
        (e.g. ``v4.50p``, ``v4.49p_beta-06``, ``v4.22p-beta``); OBD/USB
        releases are bare (``v4.21``, ``v4.20_beta-01``). The ``p`` is
        matched directly after the ``MAJOR.MINOR`` core, so any beta
        separator (``_`` or ``-``) that follows is irrelevant. Falls back to
        the release title when the tag has no numeric core.
        """
        core = tag.strip().lstrip("v")  # "4.22p-beta" | "4.50p" | "4.21"
        match = re.match(r"\d+\.\d+(p)?", core)
        if match:
            return "pro" if match.group(1) else "obd"
        return "pro" if "pro" in title.lower() else "obd"

    _PRERELEASE_TAG_RE = re.compile(r"beta|alpha|rc\d|dev|nightly|preview", re.IGNORECASE)

    @staticmethod
    def _is_prerelease(release: dict) -> bool:
        """True if a release is a pre-release/draft.

        Trusts GitHub's ``prerelease``/``draft`` flags first, but also treats
        a tag whose text says beta/alpha/rc/etc. as a pre-release — meatpi has
        shipped beta tags (e.g. ``v4.22p-beta``) without setting the flag.
        """
        if release.get("prerelease") or release.get("draft"):
            return True
        return bool(FirmwareService._PRERELEASE_TAG_RE.search(release.get("tag_name", "")))

    @staticmethod
    def device_firmware_track(hw_version: str | None) -> str | None:
        """Resolve a device's firmware track from its ``hw_version``.

        ``"PRO"`` substring (case-insensitive) → ``pro``; any other non-empty
        value → ``obd``; missing/empty → ``None`` (unknown hardware, which the
        update-comparison path skips entirely).
        """
        if not hw_version:
            return None
        return "pro" if "pro" in hw_version.lower() else "obd"

    async def check_device_firmware(self, device_id: str) -> dict:
        """Check firmware status for one device against its own track."""
        result = await self.db.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return {"error": "Device not found"}

        track = self.device_firmware_track(device.hw_version)
        result_dict: dict = {
            "device_id": device.device_id,
            "hw_version": device.hw_version,
            "current_version": device.fw_version,
            "current_tag": device.git_version,
            "firmware_track": track,
            "skipped_version": device.firmware_skipped_version,
        }

        # Unknown hardware → no comparison, no update surfaced.
        if track is None:
            result_dict.update(
                latest_version=None,
                latest_tag=None,
                release_url=None,
                checked_at=None,
                update_available=None,
                compatible=None,
            )
            return result_dict

        cache_info = await self.get_cached_firmware_info(track)
        if not cache_info:
            result_dict.update(
                latest_version=None,
                latest_tag=None,
                release_url=None,
                checked_at=None,
                update_available=None,
                compatible=None,
            )
            return result_dict

        result_dict.update(
            latest_version=cache_info["latest_version"],
            latest_tag=cache_info["latest_tag"],
            release_url=cache_info["release_url"],
            checked_at=cache_info["checked_at"],
        )
        if device.fw_version:
            result_dict["update_available"] = (
                self.compare_versions(device.fw_version, cache_info["latest_version"]) < 0
            )
            result_dict["compatible"] = self.is_firmware_compatible(device.fw_version)
        else:
            result_dict["update_available"] = None
            result_dict["compatible"] = None
        return result_dict
