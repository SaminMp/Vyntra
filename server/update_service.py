"""
Vyntra Server-Side Update Service.
Provides a secure, dependency-free proxy and metadata service between
Vyntra desktop clients and the private GitHub repository (SaminMp/Vyntra).

All GitHub Personal Access Tokens and repository credentials remain exclusively
on this server, ensuring distributed client binaries contain zero secrets.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import sys
import time
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse
import requests

# Server-Side Configuration (from environment variables)
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "SaminMp")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "Vyntra")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
NETWORK_TIMEOUT = float(os.environ.get("NETWORK_TIMEOUT", "15.0"))

SUPPORTED_PLATFORMS = {
    "windows-x64": ["Vyntra-Windows-x64.exe", "Vyntra.exe"],
    "macos-arm64": ["Vyntra-macOS-arm64.dmg", "Vyntra-macOS.dmg"],
    "macos-x64": ["Vyntra-macOS-x64.dmg", "Vyntra-macOS.dmg"],
}

# In-memory cache: (cached_data, timestamp)
_cache: Dict[str, Tuple[Dict, float]] = {}


def _get_auth_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Vyntra-Update-Service/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _parse_semver(ver: str) -> Tuple[int, int, int]:
    cleaned = re.sub(r"^[vV]", "", ver.strip())
    parts = cleaned.split("-")[0].split("+")[0].split(".")
    nums = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def _is_newer(remote: str, current: str) -> bool:
    try:
        return _parse_semver(remote) > _parse_semver(current)
    except Exception:
        return False


def fetch_release_data() -> Dict:
    """Fetches latest release and checksums from private GitHub repository with caching."""
    now = time.time()
    cached = _cache.get("latest_release")
    if cached and (now - cached[1]) < CACHE_TTL_SECONDS:
        return cached[0]

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    resp = requests.get(url, headers=_get_auth_headers(), timeout=NETWORK_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub API returned HTTP {resp.status_code}: {resp.text}")

    data = resp.json()

    # Parse attached SHA256SUMS.txt if present
    checksums_map: Dict[str, str] = {}
    for asset in data.get("assets", []):
        name = asset.get("name", "").lower()
        if name in ("sha256sums.txt", "checksums.txt"):
            asset_api_url = asset.get("url")
            if asset_api_url:
                try:
                    headers = dict(_get_auth_headers())
                    headers["Accept"] = "application/octet-stream"
                    probe = requests.get(asset_api_url, headers=headers, allow_redirects=False, timeout=NETWORK_TIMEOUT)
                    fetch_url = probe.headers.get("Location") if probe.status_code in (301, 302, 307, 308) else asset_api_url
                    fetch_headers = dict(headers)
                    if probe.status_code in (301, 302, 307, 308):
                        fetch_headers.pop("Authorization", None)
                    c_resp = requests.get(fetch_url, headers=fetch_headers, timeout=NETWORK_TIMEOUT)
                    if c_resp.status_code == 200:
                        for line in c_resp.text.splitlines():
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                checksums_map[parts[-1].strip().lstrip("*")] = parts[0].strip().lower()
                except Exception:
                    pass

    data["_checksums_map"] = checksums_map
    _cache["latest_release"] = (data, now)
    return data


class UpdateServiceHTTPHandler(BaseHTTPRequestHandler):
    """Threaded HTTP handler for Vyntra update requests."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)

        # 1. Health check
        if path == "/health" or path == "":
            self._send_json(200, {
                "status": "ok",
                "service": "vyntra-update-service",
                "repository": f"{GITHUB_OWNER}/{GITHUB_REPO}",
                "authenticated": bool(GITHUB_TOKEN),
            })
            return

        # 2. Release metadata endpoint
        if path == "/api/v1/updates/latest":
            platform_list = query.get("platform", [])
            if not platform_list:
                self._send_json(400, {"error": "Missing 'platform' query parameter."})
                return

            platform_key = platform_list[0].lower().strip()
            if platform_key not in SUPPORTED_PLATFORMS:
                self._send_json(400, {
                    "error": f"Unsupported platform '{platform_key}'. Supported: {list(SUPPORTED_PLATFORMS.keys())}"
                })
                return

            current_ver_list = query.get("current_version", ["0.0.0"])
            current_version = current_ver_list[0]

            try:
                release = fetch_release_data()
            except Exception as e:
                self._send_json(502, {"error": f"Failed to fetch release data from GitHub: {e}"})
                return

            raw_tag = release.get("tag_name", "")
            remote_version = raw_tag.lstrip("v")
            is_newer_available = _is_newer(remote_version, current_version)

            candidate_names = SUPPORTED_PLATFORMS[platform_key]
            target_asset = None
            for a in release.get("assets", []):
                if a.get("name") in candidate_names:
                    target_asset = a
                    break

            if not target_asset:
                self._send_json(200, {
                    "update_available": False,
                    "version": remote_version,
                    "message": f"Release v{remote_version} found, but no asset published for {platform_key}.",
                })
                return

            checksums = release.get("_checksums_map", {})
            sha256 = checksums.get(target_asset.get("name"), target_asset.get("digest"))

            self._send_json(200, {
                "update_available": is_newer_available,
                "version": remote_version,
                "tag": raw_tag,
                "name": release.get("name") or raw_tag,
                "release_notes": release.get("body") or "No release notes provided.",
                "published_at": release.get("published_at", ""),
                "platform": platform_key,
                "asset_name": target_asset.get("name"),
                "download_url": f"/api/v1/updates/download/{platform_key}?version={remote_version}",
                "sha256": sha256,
                "size": target_asset.get("size", 0),
            })
            return

        # 3. Binary asset streaming proxy endpoint
        match = re.match(r"^/api/v1/updates/download/([a-zA-Z0-9_-]+)$", path)
        if match:
            platform_key = match.group(1).lower().strip()
            if platform_key not in SUPPORTED_PLATFORMS:
                self._send_json(400, {"error": "Unsupported platform."})
                return

            try:
                release = fetch_release_data()
            except Exception as e:
                self._send_json(502, {"error": f"Failed to fetch release metadata: {e}"})
                return

            candidate_names = SUPPORTED_PLATFORMS[platform_key]
            target_asset = None
            for a in release.get("assets", []):
                if a.get("name") in candidate_names:
                    target_asset = a
                    break

            if not target_asset or not target_asset.get("url"):
                self._send_json(404, {"error": "Target release asset not found."})
                return

            asset_api_url = target_asset["url"]
            headers = dict(_get_auth_headers())
            headers["Accept"] = "application/octet-stream"

            try:
                # Probe redirect
                probe = requests.get(asset_api_url, headers=headers, allow_redirects=False, timeout=NETWORK_TIMEOUT)
                fetch_url = asset_api_url
                fetch_headers = dict(headers)
                if probe.status_code in (301, 302, 307, 308):
                    fetch_url = probe.headers.get("Location")
                    fetch_headers.pop("Authorization", None)

                upstream = requests.get(fetch_url, headers=fetch_headers, stream=True, timeout=NETWORK_TIMEOUT)
                if upstream.status_code != 200:
                    self._send_json(upstream.status_code, {"error": "Failed to stream asset from backend storage."})
                    return

                # Send binary headers
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{target_asset.get("name")}"')
                if "content-length" in upstream.headers:
                    self.send_header("Content-Length", upstream.headers["content-length"])
                self.end_headers()

                # Stream chunks directly to client
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        self.wfile.write(chunk)
                return

            except Exception as e:
                self._send_json(502, {"error": f"Stream failure: {e}"})
                return

        self._send_json(404, {"error": f"Endpoint '{path}' not found."})

    def _send_json(self, status: int, data: Dict):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quiet standard HTTP access logs
        pass


def run_server(port: int = 8000, host: str = "0.0.0.0"):
    server = ThreadingHTTPServer((host, port), UpdateServiceHTTPHandler)
    print(f"[Vyntra Update Service] Listening on http://{host}:{port} (Repo: {GITHUB_OWNER}/{GITHUB_REPO})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Vyntra Update Service] Shutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    run_server(port=port)
