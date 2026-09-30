import shutil
import logging
from pathlib import Path
from typing import Optional, List
import urllib.request
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.config import PATCHES_FILE, PATCHES_DIR
from app.core.apk_inspector import format_file_size

logger = logging.getLogger("morphe.api.patches")
router = APIRouter(prefix="/api/patches", tags=["Patches"])

class DownloadUrlRequest(BaseModel):
    url: str
    filename: Optional[str] = None

_format_size = format_file_size

@router.get("/sources")
async def list_patch_sources():
    """
    List all available patch bundles:
    1. Built-in default Morphe bundle (patches.mpp)
    2. Any custom community .mpp files in config/patches/
    3. Remote repository / URL option
    """
    sources = []

    # 1. Official default bundle
    default_p = Path(PATCHES_FILE)
    if default_p.exists():
        sources.append({
            "id": "default",
            "name": "🌟 Official Morphe Patches (Default)",
            "filename": default_p.name,
            "path": str(default_p),
            "size_human": _format_size(default_p.stat().st_size),
            "is_default": True,
            "is_custom": False,
        })

    # 2. Installed custom .mpp bundles in PATCHES_DIR
    if PATCHES_DIR.exists():
        for f in sorted(PATCHES_DIR.glob("*.mpp")):
            if f.is_file() and f != default_p:
                sources.append({
                    "id": f.name,
                    "name": f"📦 {f.stem.replace('_', ' ').replace('-', ' ').title()}",
                    "filename": f.name,
                    "path": str(f),
                    "size_human": _format_size(f.stat().st_size),
                    "is_default": False,
                    "is_custom": True,
                })

    return {
        "sources": sources,
        "default_source_id": "default",
        "custom_count": len([s for s in sources if s.get("is_custom")]),
    }

@router.post("/upload")
async def upload_patch_bundle(file: UploadFile = File(...)):
    """Upload a custom community .mpp bundle."""
    filename = file.filename or "community_patches.mpp"
    if not filename.lower().endswith(".mpp"):
        raise HTTPException(status_code=400, detail="Only .mpp (Morphe Patch Package) files are accepted.")

    safe_name = Path(filename).name
    dest_path = PATCHES_DIR / safe_name

    try:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        size = dest_path.stat().st_size
        logger.info(f"Custom patch bundle uploaded: {safe_name} ({_format_size(size)})")

        return {
            "success": True,
            "message": f"Patch bundle '{safe_name}' uploaded successfully.",
            "source": {
                "id": safe_name,
                "name": f"📦 {Path(safe_name).stem.replace('_', ' ').title()}",
                "filename": safe_name,
                "size_human": _format_size(size),
            }
        }
    except Exception as e:
        logger.exception(f"Failed to save uploaded patch bundle: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload patch bundle: {str(e)}")

@router.post("/download-url")
async def download_patch_bundle_from_url(req: DownloadUrlRequest):
    """Download a .mpp bundle directly from a remote HTTP/HTTPS URL into config/patches/."""
    url = req.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL must begin with http:// or https://")

    # Determine filename
    filename = req.filename.strip() if req.filename and req.filename.strip() else Path(url.split("?")[0]).name
    if not filename.endswith(".mpp"):
        filename = f"{filename}.mpp"

    safe_name = Path(filename).name
    dest_path = PATCHES_DIR / safe_name

    try:
        # Download file
        req_obj = urllib.request.Request(
            url,
            headers={"User-Agent": "Patchium/1.0"}
        )
        with urllib.request.urlopen(req_obj, timeout=60) as response, open(dest_path, "wb") as out_file:
            shutil.copyfileobj(response, out_file)

        size = dest_path.stat().st_size
        return {
            "success": True,
            "message": f"Downloaded patch bundle '{safe_name}' ({_format_size(size)}).",
            "source": {
                "id": safe_name,
                "name": f"📦 {Path(safe_name).stem.replace('_', ' ').title()}",
                "filename": safe_name,
                "size_human": _format_size(size),
            }
        }
    except Exception as e:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=f"Failed to download patch bundle from URL: {str(e)}")

@router.delete("/sources/{filename}")
async def delete_patch_bundle(filename: str):
    """Delete a custom community .mpp bundle."""
    safe_name = Path(filename).name
    target_path = PATCHES_DIR / safe_name

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Patch bundle not found.")

    try:
        target_path.unlink()
        logger.info(f"Custom patch bundle deleted: {safe_name}")
        return {"success": True, "message": f"Patch bundle '{safe_name}' removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete patch bundle: {str(e)}")

@router.get("/compatible-versions")
async def get_compatible_versions(refresh: bool = False):
    """
    Get recommended and compatible versions for all supported applications
    from the active patches bundle, along with active bundle metadata.
    """
    import asyncio
    from app.core.version_checker import get_compatible_versions_data
    from app.core.downloader import get_current_patches_meta
    data = await asyncio.to_thread(get_compatible_versions_data, force_refresh=refresh)
    meta = get_current_patches_meta()
    return {
        "packages": data,
        "meta": meta,
    }

@router.get("/check-update")
async def check_patch_update():
    """
    Check if a newer official Morphe Patches bundle is available on GitHub.
    """
    from app.core.downloader import fetch_latest_morphe_patches_info, get_current_patches_meta
    latest_info = await fetch_latest_morphe_patches_info()
    current_meta = get_current_patches_meta()

    if not latest_info:
        return {
            "success": False,
            "message": "Unable to check GitHub releases at this time.",
            "current_version": current_meta.get("version"),
            "has_update": False,
        }

    has_update = (current_meta.get("version") != latest_info["tag"])

    return {
        "success": True,
        "has_update": has_update,
        "current_version": current_meta.get("version"),
        "latest_version": latest_info["tag"],
        "release_name": latest_info.get("release_name"),
        "published_at": latest_info.get("published_at"),
        "html_url": latest_info.get("html_url"),
        "size_human": _format_size(latest_info.get("size", 0)),
    }

@router.post("/update-official")
async def update_official_patches_bundle():
    """
    Fetch and apply the latest official Morphe Patches bundle from GitHub.
    Refreshes compatibility data and invalidates caches.
    """
    import asyncio
    from app.core.downloader import download_latest_patches
    from app.core.version_checker import get_compatible_versions_data

    res = await download_latest_patches(force=True)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("message", "Failed to update patches."))

    new_versions = await asyncio.to_thread(get_compatible_versions_data, force_refresh=True)

    return {
        "success": True,
        "message": res.get("message"),
        "version": res.get("version"),
        "packages": new_versions,
    }

