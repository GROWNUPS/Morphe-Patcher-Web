import os
import json
from pathlib import Path
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

class ProfilePayload(BaseModel):
    name: str
    content: dict

@router.get("/status")
async def get_system_status():
    jar_path = Path(MORPHE_JAR)
    patches_path = Path(PATCHES_FILE)

    profiles = []
    if PROFILES_DIR.exists():
        for p in PROFILES_DIR.glob("*.json"):
            profiles.append(p.stem)

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
        "profiles": profiles,
    }

@router.post("/update-patches")
async def update_patches_bundle():
    patches_path = Path(PATCHES_FILE)
    success = await download_file(PATCHES_DOWNLOAD_URL, patches_path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update patches bundle from GitHub.")
    return {"success": True, "message": "Patches bundle updated successfully."}

@router.get("/profiles/{name}")
async def get_profile(name: str):
    safe_name = Path(name).name
    file_path = PROFILES_DIR / f"{safe_name}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/profiles")
async def save_profile(payload: ProfilePayload):
    safe_name = Path(payload.name.strip().replace(" ", "_")).name
    file_path = PROFILES_DIR / f"{safe_name}.json"
    try:
        with open(file_path, "w") as f:
            json.dump(payload.content, f, indent=2)
        return {"success": True, "profile": safe_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

