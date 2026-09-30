import os
import shutil
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.config import CACHE_DIR, LIBRARY_DIR
from app.core.apk_library import (
    list_library_apks,
    get_library_apk,
    save_to_library,
    delete_from_library,
)

logger = logging.getLogger("patchium.api.library")

router = APIRouter(prefix="/api/library", tags=["Library"])

class SaveUploadedRequest(BaseModel):
    temp_path: str
    custom_filename: Optional[str] = None

@router.get("")
async def get_all_library_apks():
    """Returns list of all persistent base APKs stored in the library."""
    try:
        return list_library_apks()
    except Exception as e:
        logger.error(f"Error listing library APKs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{filename}")
async def get_single_library_apk(filename: str):
    """Retrieves metadata of a specific APK in the library."""
    item = get_library_apk(filename)
    if not item:
        raise HTTPException(status_code=404, detail="APK not found in library.")
    return item

@router.post("/upload")
async def upload_to_library(file: UploadFile = File(...)):
    """Uploads an APK directly into the persistent library."""
    if not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only .apk files are supported.")

    safe_name = Path(file.filename).name
    temp_dest = CACHE_DIR / f"lib_upload_{safe_name}"

    try:
        with open(temp_dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        saved_item = save_to_library(temp_dest, safe_name)
        return {"success": True, "apk": saved_item}

    except Exception as e:
        logger.error(f"Failed to upload to library: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)

@router.post("/save-uploaded")
async def save_uploaded_to_library(payload: SaveUploadedRequest):
    """Saves an already uploaded/downloaded temporary APK into the persistent library."""
    source_path = Path(payload.temp_path)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Source file not found: {payload.temp_path}")

    try:
        saved_item = save_to_library(source_path, payload.custom_filename)
        return {"success": True, "apk": saved_item}
    except Exception as e:
        logger.error(f"Failed to save to library: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{filename}")
async def remove_from_library(filename: str):
    """Deletes a base APK from the persistent library."""
    success = delete_from_library(filename)
    if not success:
        raise HTTPException(status_code=404, detail="APK not found or could not be deleted.")
    return {"success": True, "message": f"Deleted '{filename}' from library."}
