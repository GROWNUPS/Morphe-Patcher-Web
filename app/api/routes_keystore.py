import os
import shutil
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.config import KEYSTORE_DIR
from app.core.keystore import (
    get_keystore_info,
    set_custom_keystore,
    reset_default_keystore,
    get_active_keystore_config,
)

logger = logging.getLogger("morphe.api.keystore")
router = APIRouter(prefix="/api/keystore", tags=["Keystore"])

@router.get("")
async def get_active_keystore():
    """Returns details and verification status of current active signing keystore."""
    return get_keystore_info()

@router.post("/upload")
async def upload_custom_keystore(
    file: UploadFile = File(...),
    password: str = Form(...),
    alias: Optional[str] = Form(None),
    key_password: Optional[str] = Form(None),
):
    """
    Upload and activate a custom .keystore / .jks file for persistent APK signing.
    Validates keystore integrity and credentials using keytool before activation.
    """
    filename = file.filename or "custom.keystore"
    safe_name = Path(filename).name

    dest_path = KEYSTORE_DIR / safe_name

    try:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Validate & set as persistent active keystore
        effective_alias = alias.strip() if alias and alias.strip() else None
        effective_keypass = key_password.strip() if key_password and key_password.strip() else None

        info = set_custom_keystore(
            keystore_path=dest_path,
            storepass=password,
            alias=effective_alias,
            keypass=effective_keypass,
        )

        return {
            "success": True,
            "message": f"Custom keystore '{safe_name}' verified and activated successfully.",
            "keystore": info,
        }

    except ValueError as e:
        if dest_path.exists() and dest_path.name != "morphe.keystore":
            try:
                dest_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to process uploaded keystore: {e}")
        if dest_path.exists() and dest_path.name != "morphe.keystore":
            try:
                dest_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to process keystore: {str(e)}")

@router.get("/download")
async def download_active_keystore():
    """Download the current active keystore file for local backup or mobile migration."""
    cfg = get_active_keystore_config()
    p = Path(cfg["path"])
    if not p.exists() or p.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Active keystore file not found")

    return FileResponse(
        path=str(p),
        filename=p.name,
        media_type="application/octet-stream",
    )

@router.post("/reset")
async def reset_to_default_keystore():
    """Reset to default auto-generated Morphe keystore."""
    info = reset_default_keystore()
    return {
        "success": True,
        "message": "Reset to default auto-generated keystore.",
        "keystore": info,
    }
