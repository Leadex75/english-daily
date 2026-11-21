from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile

from app.db import data_dir
from ingest.fetch_feeds import http_stream


def parse_itunes_duration(value: Any) -> int | None:
    """Accept SS, MM:SS and HH:MM:SS (also plain ints from some feeds)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3 or any(not part.strip().isdigit() for part in parts):
        return None
    numbers = [int(part.strip()) for part in parts]
    seconds = 0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def audio_window(source: dict[str, Any], config: dict[str, Any], hotlink: bool = False) -> tuple[int, int]:
    """Hard sanity bounds only. Preferred bounds are applied later by the cascade."""
    minimum = config.get("audio_hard_min_sec")
    maximum = config.get("audio_hard_max_sec")
    low = 0 if minimum is None else int(minimum)
    high = 10**9 if maximum is None else int(maximum)
    return low, max(low, high)


def preferred_audio(duration: int | None, config: dict[str, Any]) -> bool:
    if duration is None:
        return False
    return int(config["audio_pref_min_sec"]) <= duration <= int(config["audio_pref_max_sec"])


def _https_candidate(url: str) -> str:
    if url.lower().startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def _verify_public_audio(url: str, config: dict[str, Any]) -> str | None:
    candidate = _https_candidate(url)
    try:
        with http_stream(
            candidate,
            config,
            headers={"Range": "bytes=0-1023"},
            raise_for_status=False,
        ) as response:
            status = response.status_code
            content_type = str(response.headers.get("content-type") or "").lower()
            final = str(response.url)
            if status not in (200, 206) or not content_type.startswith("audio/"):
                return None
            if not final.lower().startswith("https://"):
                return None
            next(response.iter_bytes(1), None)
            return final
    except Exception:
        return None


def _hotlink_audio(
    entry: dict[str, Any],
    config: dict[str, Any],
    guid_hash: str,
    minimum: int,
    maximum: int,
    announced: int | None,
) -> dict[str, Any] | None:
    url = entry.get("enclosure_url")
    if not url:
        return None
    public_url = _verify_public_audio(str(url), config)
    if not public_url:
        return None
    duration = announced
    if duration is None or bool(config.get("verify_audio_download")):
        try:
            root = data_dir(config)
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=str(root)) as temporary_dir:
                temporary = Path(temporary_dir) / f"{guid_hash}.mp3"
                with http_stream(public_url, config) as response:
                    with temporary.open("wb") as handle:
                        for chunk in response.iter_bytes(16_384):
                            handle.write(chunk)
                if temporary.stat().st_size == 0:
                    return None
                measured = MutagenFile(str(temporary))
                measured_duration = int(measured.info.length) if measured and measured.info.length else None
                duration = measured_duration or duration
        except Exception:
            duration = announced
    if duration is None or not minimum <= duration <= maximum:
        return None
    return {
        "duration_sec": duration,
        "audio_path": None,
        "audio_bytes": None,
        "audio_remote_url": public_url,
    }


def download_audio(
    entry: dict[str, Any],
    source: dict[str, Any],
    config: dict[str, Any],
    day: str,
    guid_hash: str,
) -> dict[str, Any] | None:
    """Measure one enclosure; local mode keeps the MP3, hotlink mode only stores its URL."""
    hotlink = str(config.get("audio_mode") or "local") == "hotlink"
    minimum, maximum = audio_window(source, config, hotlink=hotlink)
    feed_duration = parse_itunes_duration(entry.get("itunes_duration"))
    if feed_duration is None:
        feed_duration = parse_itunes_duration(entry.get("playtime"))
    if feed_duration is not None and not minimum <= feed_duration <= maximum:
        return None
    if not entry.get("enclosure_url"):
        return None
    if hotlink:
        return _hotlink_audio(entry, config, guid_hash, minimum, maximum, feed_duration)

    target_dir = data_dir(config) / "audio" / day
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    target = target_dir / f"{guid_hash}.mp3"
    temporary = target_dir / f"{guid_hash}.part"
    try:
        with http_stream(str(entry["enclosure_url"]), config) as response:
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes(16_384):
                    handle.write(chunk)
        if temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            return None
        measured = MutagenFile(str(temporary))
        duration = int(measured.info.length) if measured and measured.info.length else None
        if duration is None or not minimum <= duration <= maximum:
            temporary.unlink(missing_ok=True)
            return None

        if config.get("reencode_audio") and shutil.which("ffmpeg"):
            reencoded = target_dir / f"{guid_hash}.re.mp3"
            command = [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(temporary),
                "-ac", "1", "-b:a", f"{int(config['audio_bitrate_kbps'])}k", str(reencoded),
            ]
            subprocess.run(command, check=True, capture_output=True, timeout=900)
            reencoded.replace(temporary)

        temporary.replace(target)
        return {
            "duration_sec": duration,
            "audio_path": f"audio/{day}/{target.name}",
            "audio_bytes": target.stat().st_size,
            "audio_remote_url": None,
        }
    except Exception:
        for leftover in (temporary, target):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
        return None
