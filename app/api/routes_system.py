import os
import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import (
    MORPHE_JAR,
    PATCHES_FILE,
    PROFILES_DIR,
    PATCHES_DOWNLOAD_URL,
)
from app.core.keystore import get_keystore_info
from app.core.watcher import hot_folder_watcher
from app.core.queue_manager import queue_manager
from app.core.downloader import download_file

router = APIRouter(prefix="/api/system", tags=["System"])

from app.core.profiles import list_profiles

@router.get("/status")
async def get_system_status():
    jar_path = Path(MORPHE_JAR)
    patches_path = Path(PATCHES_FILE)

    profiles = list_profiles()

    return {
        "morphe_jar": {
            "path": str(jar_path),
            "exists": jar_path.exists(),
            "size": jar_path.stat().st_size if jar_path.exists() else 0,
        },
        "patches_bundle": {
            "path": str(patches_path),
            "exists": patches_path.exists(),
            "size": patches_path.stat().st_size if patches_path.exists() else 0,
        },
        "keystore": get_keystore_info(),
        "watcher": hot_folder_watcher.get_status(),
        "queue": {
            "active_job": queue_manager.current_job.to_dict() if queue_manager.current_job else None,
            "queued_count": queue_manager.queue.qsize(),
            "total_jobs": len(queue_manager.jobs),
        },
        "profiles": [p["id"] for p in profiles],
        "profile_details": profiles,
    }

@router.post("/update-patches")
async def update_patches_bundle():
    patches_path = Path(PATCHES_FILE)
    success = await download_file(PATCHES_DOWNLOAD_URL, patches_path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update patches bundle from GitHub.")
    return {"success": True, "message": "Patches bundle updated successfully."}

class WatcherToggleRequest(BaseModel):
    enabled: Optional[bool] = None

@router.post("/watcher/toggle")
async def toggle_watcher(payload: Optional[WatcherToggleRequest] = None):
    """Toggle hot-folder watcher daemon on or off."""
    enabled = payload.enabled if payload else None
    state = hot_folder_watcher.toggle(enabled)
    return {"success": True, "enabled": state, "status": hot_folder_watcher.get_status()}



