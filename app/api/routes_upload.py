import os
import re
import time
import shutil
import urllib.parse
from pathlib import Path
from typing import Optional, List
import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.config import CACHE_DIR
from app.core.apk_inspector import inspect_apk

router = APIRouter(prefix="/api/upload", tags=["Upload"])

class DownloadUrlRequest(BaseModel):
    url: str
    filename: Optional[str] = None

def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\/\\:\*\?"<>\|\x00-\x1f]', '_', name)
    cleaned = cleaned.strip('. ')
    if not cleaned.lower().endswith(".apk"):
        cleaned += ".apk"
    return cleaned or "downloaded_app.apk"

def _get_unique_dest(base_name: str) -> Path:
    safe_name = _sanitize_filename(base_name)
    dest = CACHE_DIR / safe_name
    if not dest.exists():
        return dest
    stem = Path(safe_name).stem
    return CACHE_DIR / f"{stem}_{int(time.time())}.apk"

@router.post("")
async def upload_apk(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="Only .apk files are supported.")

    safe_filename = Path(file.filename).name
    upload_dest = CACHE_DIR / safe_filename
    try:
        with open(upload_dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        metadata = inspect_apk(upload_dest)
        metadata["temp_path"] = str(upload_dest)
        return metadata

    except Exception as e:
        if upload_dest.exists():
            upload_dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to process APK: {e}")

@router.post("/batch")
async def upload_batch_apks(files: List[UploadFile] = File(...)):
    results = []
    errors = []

    for file in files:
        if not file.filename.lower().endswith(".apk"):
            errors.append({"file_name": file.filename, "error": "Only .apk files are supported."})
            continue

        safe_filename = Path(file.filename).name
        upload_dest = CACHE_DIR / safe_filename
        try:
            with open(upload_dest, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            metadata = inspect_apk(upload_dest)
            metadata["temp_path"] = str(upload_dest)
            results.append(metadata)
        except Exception as e:
            if upload_dest.exists():
                upload_dest.unlink(missing_ok=True)
            errors.append({"file_name": file.filename, "error": str(e)})

    return {"results": results, "errors": errors}

@router.post("/url")
async def download_apk_url(req: DownloadUrlRequest):
    url = req.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    candidate_name = req.filename.strip() if req.filename and req.filename.strip() else None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }

    temp_dest = CACHE_DIR / f"download_{int(time.time() * 1000)}.tmp"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=180.0, headers=headers) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Remote server returned HTTP {response.status_code} ({response.reason_phrase})"
                    )

                if not candidate_name:
                    content_disp = response.headers.get("content-disposition", "")
                    if "filename*=" in content_disp:
                        match = re.search(r"filename\*=UTF-8''([^;]+)", content_disp, re.IGNORECASE)
                        if match:
                            candidate_name = urllib.parse.unquote(match.group(1))
                    if not candidate_name and "filename=" in content_disp:
                        match = re.search(r'filename="?([^";]+)"?', content_disp)
                        if match:
                            candidate_name = match.group(1)

                if not candidate_name:
                    path = urllib.parse.urlparse(str(response.url)).path
                    candidate_name = urllib.parse.unquote(Path(path).name)

                if not candidate_name or candidate_name in ("", "/"):
                    candidate_name = "downloaded_app.apk"

                with open(temp_dest, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 128):
                        f.write(chunk)

        final_dest = _get_unique_dest(candidate_name)
        temp_dest.replace(final_dest)

        metadata = inspect_apk(final_dest)
        if not metadata.get("is_valid_apk"):
            final_dest.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail="Downloaded file is not a valid Android APK package (missing AndroidManifest.xml or invalid file format)."
            )

        metadata["temp_path"] = str(final_dest)
        return metadata

    except HTTPException:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        raise
    except httpx.RequestError as e:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Network error downloading APK: {e}")
    except Exception as e:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to process downloaded APK: {e}")
