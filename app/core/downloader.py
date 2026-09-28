import os
import shutil
import logging
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

from app.config import (
    MORPHE_JAR,
    PATCHES_FILE,
    MORPHE_DOWNLOAD_URL,
    PATCHES_DOWNLOAD_URL,
    CONFIG_DIR,
    PATCHES_META_FILE,
    MORPHE_PATCHES_REPO,
    AUTO_UPDATE_PATCHES,
)

logger = logging.getLogger("morphe.downloader")


def get_current_patches_meta() -> Dict[str, Any]:
    """Return the cached or local metadata for the active patches bundle."""
    p_path = Path(PATCHES_FILE)
    if not p_path.exists():
        return {
            "version": None,
            "filename": None,
            "size": 0,
            "published_at": None,
            "updated_at": None,
            "html_url": None,
        }

    if PATCHES_META_FILE.exists():
        try:
            with open(PATCHES_META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {PATCHES_META_FILE}: {e}")

    try:
        return {
            "version": "Installed",
            "filename": p_path.name,
            "size": p_path.stat().st_size,
            "published_at": None,
            "updated_at": None,
            "html_url": None,
        }
    except Exception:
        pass

    return {
        "version": None,
        "filename": None,
        "size": 0,
        "published_at": None,
        "updated_at": None,
        "html_url": None,
    }


async def fetch_latest_morphe_patches_info() -> Optional[Dict[str, Any]]:
    """Query GitHub releases API for latest Morphe patches release."""
    api_url = f"https://api.github.com/repos/{MORPHE_PATCHES_REPO}/releases/latest"
    headers = {
        "User-Agent": "Morphe-Patcher-Web/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(api_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"GitHub API returned {resp.status_code} for {api_url}")
                return None
            data = resp.json()
            tag = data.get("tag_name")
            assets = data.get("assets", [])
            mpp_asset = next((a for a in assets if a.get("name", "").endswith(".mpp")), None)

            download_url = mpp_asset.get("browser_download_url") if mpp_asset else PATCHES_DOWNLOAD_URL
            size = mpp_asset.get("size", 0) if mpp_asset else 0
            filename = mpp_asset.get("name", "patches.mpp") if mpp_asset else "patches.mpp"

            return {
                "tag": tag,
                "release_name": data.get("name") or tag,
                "published_at": data.get("published_at"),
                "html_url": data.get("html_url"),
                "size": size,
                "filename": filename,
                "download_url": download_url,
            }
    except Exception as e:
        logger.warning(f"Failed to fetch Morphe patch release info: {e}")
        return None


async def download_file(url: str, dest_path: Path) -> bool:
    """Download a file with streaming and atomic write."""
    try:
        temp_dest = dest_path.with_suffix(".tmp")
        logger.info(f"Downloading {url} to {dest_path}...")
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    logger.error(f"Download failed with status {response.status_code} for {url}")
                    return False
                with open(temp_dest, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 64):
                        f.write(chunk)

        temp_dest.replace(dest_path)
        logger.info(f"Downloaded successfully: {dest_path} ({dest_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        logger.warning(f"Failed to download {url}: {e}")
        return False


async def download_latest_patches(force: bool = False) -> Dict[str, Any]:
    """Download latest Morphe patches from GitHub and write patches_meta.json."""
    info = await fetch_latest_morphe_patches_info()
    current_meta = get_current_patches_meta()

    if not info or not info.get("download_url"):
        return {"success": False, "message": "Could not contact GitHub releases API to retrieve patches."}

    tag = info["tag"]
    if not force and current_meta.get("version") == tag and Path(PATCHES_FILE).exists():
        return {"success": True, "message": f"Patches already up to date ({tag}).", "version": tag}

    dest_path = Path(PATCHES_FILE)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    success = await download_file(info["download_url"], dest_path)

    if not success:
        return {"success": False, "message": f"Failed to download patch bundle from {info['download_url']}."}

    meta_data = {
        "version": tag,
        "filename": info.get("filename", dest_path.name),
        "size": dest_path.stat().st_size,
        "published_at": info.get("published_at"),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "html_url": info.get("html_url"),
    }
    try:
        with open(PATCHES_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save {PATCHES_META_FILE}: {e}")

    return {
        "success": True,
        "message": f"Successfully updated Morphe patches to {tag}.",
        "version": tag,
        "meta": meta_data,
    }


async def ensure_binaries():
    """Ensure Morphe CLI JAR and patches bundle exist locally on service launch."""
    jar_path = Path(MORPHE_JAR)
    patches_path = Path(PATCHES_FILE)

    if not jar_path.exists():
        logger.info(f"Morphe JAR missing at {jar_path}. Attempting download...")
        jar_path.parent.mkdir(parents=True, exist_ok=True)
        await download_file(MORPHE_DOWNLOAD_URL, jar_path)

    if not patches_path.exists():
        logger.info(f"Patches bundle missing at {patches_path}. Attempting download...")
        patches_path.parent.mkdir(parents=True, exist_ok=True)
        res = await download_latest_patches(force=True)
        if not res.get("success"):
            await download_file(PATCHES_DOWNLOAD_URL, patches_path)
    elif AUTO_UPDATE_PATCHES:
        logger.info("Checking for updated Morphe patches on startup...")
        try:
            await download_latest_patches(force=False)
        except Exception as e:
            logger.warning(f"Background patches update check failed: {e}")
