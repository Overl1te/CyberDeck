"""Release update checker for CyberDeck and CyberDeck-Mobile tags.

This module fetches latest GitHub release tags through GitHub REST API,
compares them against local versions, and returns normalized payloads.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib import error, request


_SEMVER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_GH_API_TEMPLATE = "https://api.github.com/repos/{repo}/releases/latest"
_CACHE_LOCK = threading.Lock()


@dataclass
class _CacheEntry:
    """Hold cached release lookup payload and its expiration timestamp."""

    expires_at: float
    payload: dict[str, Any]


_CACHE: dict[str, _CacheEntry] = {}


def normalize_version_tag(value: Any) -> str:
    """Normalize version tags by trimming spaces and dropping leading `v`."""
    text = str(value or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    return text


def _semver_triplet(value: Any) -> Optional[tuple[int, int, int]]:
    """Parse semantic version `major.minor.patch` and return numeric triplet."""
    tag = normalize_version_tag(value)
    match = _SEMVER_RE.match(tag)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_newer_version(latest_tag: Any, current_tag: Any) -> bool:
    """Return True when latest tag is semantically newer than current tag."""
    latest = _semver_triplet(latest_tag)
    current = _semver_triplet(current_tag)
    if latest is None or current is None:
        return False
    return latest > current


def _read_latest_release_payload(repo_slug: str, timeout_s: float) -> dict[str, Any]:
    """Load latest release payload from GitHub API and return decoded JSON object."""
    api_url = _GH_API_TEMPLATE.format(repo=repo_slug)
    req = request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "CyberDeck-UpdateChecker/1.3.1",
        },
    )
    with request.urlopen(req, timeout=float(timeout_s)) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid_json_shape")
    return payload


def fetch_latest_release_tag(
    repo_slug: str,
    *,
    timeout_s: float = 2.5,
    ttl_s: int = 300,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch latest GitHub release tag for the repository with in-memory TTL cache."""
    repo = str(repo_slug or "").strip()
    api_url = _GH_API_TEMPLATE.format(repo=repo)
    if not repo:
        return {
            "ok": False,
            "repo": repo,
            "api_url": api_url,
            "latest_tag": "",
            "release_url": "",
            "published_at": "",
            "error": "repo_slug_empty",
            "checked_at": int(time.time()),
        }

    now_mono = time.monotonic()
    if not force_refresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(repo)
            if cached is not None and cached.expires_at > now_mono:
                return dict(cached.payload)

    checked_at = int(time.time())
    try:
        parsed = _read_latest_release_payload(repo, timeout_s=max(0.5, float(timeout_s)))
        tag = str(parsed.get("tag_name") or "").strip()
        if not tag:
            raise ValueError("missing_tag_name")
        result = {
            "ok": True,
            "repo": repo,
            "api_url": api_url,
            "latest_tag": tag,
            "release_url": str(parsed.get("html_url") or ""),
            "published_at": str(parsed.get("published_at") or ""),
            "error": "",
            "checked_at": checked_at,
        }
    except error.HTTPError as exc:
        result = {
            "ok": False,
            "repo": repo,
            "api_url": api_url,
            "latest_tag": "",
            "release_url": "",
            "published_at": "",
            "error": f"http_{int(getattr(exc, 'code', 0) or 0)}",
            "checked_at": checked_at,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "repo": repo,
            "api_url": api_url,
            "latest_tag": "",
            "release_url": "",
            "published_at": "",
            "error": str(exc.__class__.__name__).lower() or "unknown_error",
            "checked_at": checked_at,
        }

    ttl_seconds = max(15, min(3600, int(ttl_s)))
    with _CACHE_LOCK:
        _CACHE[repo] = _CacheEntry(expires_at=now_mono + float(ttl_seconds), payload=dict(result))
    return dict(result)


def _status_from_release(current_version: str, release: dict[str, Any]) -> dict[str, Any]:
    """Build a normalized update status payload for a single target product."""
    current = str(current_version or "").strip()
    latest = str(release.get("latest_tag") or "").strip()
    ok = bool(release.get("ok"))
    return {
        "current_version": current,
        "latest_tag": latest,
        "has_update": bool(ok and latest and is_newer_version(latest, current)),
        "release_url": str(release.get("release_url") or ""),
        "published_at": str(release.get("published_at") or ""),
        "checked_at": int(release.get("checked_at") or int(time.time())),
        "error": str(release.get("error") or ""),
        "source_ok": ok,
    }


def build_update_status(
    *,
    current_server_version: str,
    current_launcher_version: str,
    current_mobile_version: str,
    server_repo: str,
    mobile_repo: str,
    timeout_s: float = 2.5,
    ttl_s: int = 300,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Build combined update status for server/launcher/mobile release channels."""
    server_release = fetch_latest_release_tag(
        server_repo,
        timeout_s=timeout_s,
        ttl_s=ttl_s,
        force_refresh=force_refresh,
    )
    mobile_release = fetch_latest_release_tag(
        mobile_repo,
        timeout_s=timeout_s,
        ttl_s=ttl_s,
        force_refresh=force_refresh,
    )

    return {
        "checked_at": int(time.time()),
        "sources": {
            "server_repo": str(server_repo or ""),
            "mobile_repo": str(mobile_repo or ""),
            "server_api_url": str(server_release.get("api_url") or ""),
            "mobile_api_url": str(mobile_release.get("api_url") or ""),
        },
        "server": _status_from_release(current_server_version, server_release),
        "launcher": _status_from_release(current_launcher_version, server_release),
        "mobile": _status_from_release(current_mobile_version, mobile_release),
    }

