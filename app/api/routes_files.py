import os
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import OUTPUT_DIR, WATCH_DIR
from app.core.apk_inspector import format_file_size

router = APIRouter(prefix="/api/files", tags=["Files"])

@router.get("/output")
async def list_output_apks():
    files = []
    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.iterdir():
            if f.is_file() and f.suffix.lower() == ".apk":
                stat = f.stat()
                files.append({
                    "filename": f.name,
                    "size_bytes": stat.st_size,
                    "size_human": format_file_size(stat.st_size),
                    "modified": stat.st_mtime,
                    "modified_human": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "download_url": f"/api/files/download/{f.name}",
                })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return files

@router.get("/download/{filename}")
async def download_output_apk(filename: str):
    safe_filename = Path(filename).name
    file_path = OUTPUT_DIR / safe_filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type="application/vnd.android.package-archive"
    )

@router.delete("/output/{filename}")
async def delete_output_apk(filename: str):
    safe_filename = Path(filename).name
    file_path = OUTPUT_DIR / safe_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    file_path.unlink()
    return {"success": True, "message": f"Deleted {safe_filename}"}

@router.get("/watch")
async def list_watch_files():
    files = []
    if WATCH_DIR.exists():
        for f in WATCH_DIR.iterdir():
            if f.is_file():
                stat = f.stat()
                files.append({
                    "filename": f.name,
                    "size_human": format_file_size(stat.st_size),
                    "modified_human": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
    return files

