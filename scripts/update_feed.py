#!/usr/bin/env python3
"""Publish the newest unsigned Tailnet build into this Feather source.

The app repository builds an unsigned IPA and keeps it at a stable URL:

    https://github.com/CasperOng/tailnet/releases/download/latest/Tailnet-unsigned.ipa

This script downloads that IPA, reads the version out of its Info.plist, and
rewrites the files Feather reads here:

    ipas/Tailnet-unsigned.ipa
    apps.json
    LATEST-BUILD.md

It is idempotent: nothing is written when the feed already describes the build.

Because both repositories are private, every request needs a token. Set GH_TOKEN
to a fine-grained PAT with `contents: read` on the app repository. Without it the
script falls back to an unauthenticated request, which only works if you make the
app repository public.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import plistlib
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

SOURCE_REPO = os.environ.get("SOURCE_REPO", "CasperOng/tailnet")
SOURCE_TAG = os.environ.get("SOURCE_TAG", "latest")
SOURCE_ASSET = os.environ.get("SOURCE_ASSET", "Tailnet-unsigned.ipa")
FEED_OWNER = os.environ.get("FEED_OWNER", "CasperOng")
FEED_REPO = os.environ.get("FEED_REPO", "tailnet-feather")
FEED_BRANCH = os.environ.get("FEED_BRANCH", "main")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

IPA_DIR = ROOT / "ipas"
FEED_PATH = ROOT / "apps.json"
LATEST_PATH = ROOT / "LATEST-BUILD.md"

RAW_BASE = (os.environ.get("FEED_BASE_URL")
            or f"https://casperong.is-a.dev/{FEED_REPO}")

# Everything about the app that does not change from build to build.
APP = {
    "name": "Tailnet",
    "bundleIdentifier": "com.casperong.tailnet",
    "developerName": "Casper Ong",
    "subtitle": "Tailscale and Headscale client",
    "category": "utilities",
    "tintColor": "#0A84FF",
    "localizedDescription": (
        "A Tailscale and Headscale client for iPad. Point it at your own coordination "
        "server and it joins your tailnet. Connects to directly reachable peers; DERP "
        "relay fallback is not implemented yet."
    ),
    "privacy": {},
}


def log(message: str) -> None:
    print(message, flush=True)


def request(url: str, method: str = "GET") -> Request:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "tailnet-feed"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return Request(url, method=method, headers=headers)


def release_download_url(tag: str, asset: str) -> str:
    """Asset URL for `tag`, falling back to the newest release that has it."""
    direct = f"https://github.com/{SOURCE_REPO}/releases/download/{tag}/{asset}"
    log(f"Looking for {asset} at {direct}")
    try:
        with urlopen(request(direct, method="HEAD"), timeout=30) as response:
            if response.status == 200:
                return direct
    except HTTPError as error:
        log(f"  HEAD {direct} -> {error.code}")
    except URLError as error:
        log(f"  HEAD {direct} -> {error.reason}")

    # Fall back to the newest release that carries the asset.
    log("Falling back to the newest release that has the asset")
    api = f"https://api.github.com/repos/{SOURCE_REPO}/releases"
    with urlopen(request(api), timeout=30) as response:
        releases = json.load(response)
    for release in releases:
        for asset_info in release.get("assets", []):
            if asset_info["name"] == asset:
                return asset_info["browser_download_url"]
    raise SystemExit(f"No release of {SOURCE_REPO} carries {asset}")


def download(url: str) -> bytes:
    log(f"Downloading {url}")
    with urlopen(request(url), timeout=180) as response:
        return response.read()


def read_ipa_info(data: bytes) -> dict:
    """Pull Payload/*.app/Info.plist out of the IPA."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next(
            (n for n in archive.namelist()
             if n.startswith("Payload/") and n.endswith(".app/Info.plist")),
            None,
        )
        if name is None:
            raise SystemExit("The IPA has no Payload/*.app/Info.plist")
        log(f"Reading {name}")
        return plistlib.loads(archive.read(name))


def load_existing() -> dict:
    if FEED_PATH.exists():
        try:
            return json.loads(FEED_PATH.read_text())
        except json.JSONDecodeError:
            log("apps.json is not valid JSON; rebuilding it")
    return {}


def build_feed(info: dict, ipa_name: str, ipa_bytes: bytes, commit: str) -> dict:
    version = info.get("CFBundleShortVersionString", "1.0")
    build = info.get("CFBundleVersion", "1")
    minimum = info.get("MinimumOSVersion", "17.0")
    digest = hashlib.sha256(ipa_bytes).hexdigest()

    feed = {
        "name": "Tailnet",
        "subtitle": APP["subtitle"],
        "description": "Unsigned Tailnet builds for signing with Feather.",
        "iconURL": f"{RAW_BASE}/icons/Tailnet.png",
        "tintColor": APP["tintColor"],
        "apps": [
            {
                "name": APP["name"],
                "bundleIdentifier": APP["bundleIdentifier"],
                "developerName": APP["developerName"],
                "subtitle": APP["subtitle"],
                "localizedDescription": APP["localizedDescription"],
                "iconURL": f"{RAW_BASE}/icons/Tailnet.png",
                "tintColor": APP["tintColor"],
                "category": APP["category"],
                "appPermissions": {"entitlements": [], "privacy": APP["privacy"]},
                "versions": [
                    {
                        "version": version,
                        "buildVersion": build,
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "localizedDescription": (
                            f"Version {version} (build {build}) \u2014 unsigned, "
                            "ready to sign with Feather."
                        ),
                        "downloadURL": f"{RAW_BASE}/ipas/{ipa_name}",
                        "size": len(ipa_bytes),
                        "sha256": digest,
                        "minOSVersion": minimum,
                    }
                ],
            }
        ],
    }
    return feed


def write_latest(info: dict, ipa_name: str, ipa_bytes: bytes) -> None:
    version = info.get("CFBundleShortVersionString", "1.0")
    build = info.get("CFBundleVersion", "1")
    digest = hashlib.sha256(ipa_bytes).hexdigest()
    size = len(ipa_bytes)
    LATEST_PATH.write_text(
        f"""# Latest build

| | |
| --- | --- |
| Version | {version} |
| Build | {build} |
| Bundle id | `{APP['bundleIdentifier']}` |
| Size | {size:,} bytes |
| SHA-256 | `{digest}` |
| IPA | [`ipas/{ipa_name}`](ipas/{ipa_name}) |
| Published | {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} |

Built from [`{SOURCE_REPO}`](https://github.com/{SOURCE_REPO}) release `{SOURCE_TAG}`.
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ipa", metavar="PATH",
                        help="Use a local IPA instead of downloading the release. The app "
                             "repository's CI has the artefact already, so it passes it here "
                             "rather than making this script fetch what it just built.")
    parser.add_argument("--force", action="store_true",
                        help="Rewrite the feed even when it already describes this build")
    args = parser.parse_args()

    if args.ipa:
        log(f"Using the local IPA at {args.ipa}")
        ipa_bytes = Path(args.ipa).read_bytes()
    else:
        url = release_download_url(SOURCE_TAG, SOURCE_ASSET)
        ipa_bytes = download(url)
    info = read_ipa_info(ipa_bytes)

    version = info.get("CFBundleShortVersionString", "1.0")
    build = info.get("CFBundleVersion", "1")
    ipa_name = f"Tailnet-{version}-{build}.ipa"

    existing = load_existing()
    try:
        current = existing["apps"][0]["versions"][0]
        if (not args.force
                and current.get("version") == version
                and current.get("buildVersion") == build
                and current.get("size") == len(ipa_bytes)):
            log(f"Feed already describes {version} ({build}); nothing to do")
            return 0
    except (KeyError, IndexError):
        pass

    IPA_DIR.mkdir(exist_ok=True)
    # One IPA in the tree at a time: the feed points at a single version, and
    # carrying every build would grow the repository without bound.
    for stale in IPA_DIR.glob("*.ipa"):
        if stale.name != ipa_name:
            log(f"Removing stale {stale.name}")
            stale.unlink()

    (IPA_DIR / ipa_name).write_bytes(ipa_bytes)
    FEED_PATH.write_text(json.dumps(build_feed(info, ipa_name, ipa_bytes, SOURCE_TAG), indent=2) + "\n")
    write_latest(info, ipa_name, ipa_bytes)

    log(f"Published {version} (build {build}) as {ipa_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
