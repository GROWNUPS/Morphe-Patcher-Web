import os
import time
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.config import LIBRARY_DIR
from app.core.apk_inspector import inspect_apk, format_file_size
from app.core.version_checker import check_apk_compatibility

logger = logging.getLogger("patchium.apk_library")

# In-memory metadata cache: (filename, mtime, size) -> metadata dict
_LIBRARY_CACHE: Dict[str, Any] = {}

def get_library_dir() -> Path:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    return LIBRARY_DIR

def list_library_apks() -> List[Dict[str, Any]]:
    """Lists all persistent base APKs in the library with parsed metadata and compatibility."""
    lib_dir = get_library_dir()
    apks: List[Dict[str, Any]] = []

    for file_path in lib_dir.glob("*.apk"):
        try:
            stat = file_path.stat()
            cache_key = f"{file_path.name}:{stat.st_mtime}:{stat.st_size}"

            if cache_key in _LIBRARY_CACHE:
                apks.append(_LIBRARY_CACHE[cache_key])
                continue

            metadata = inspect_apk(file_path)
            pkg = metadata.get("package_name")
            ver = metadata.get("version_name")

            compat_info = None
            if pkg and ver:
                try:
                    compat_info = check_apk_compatibility(pkg, ver)
                except Exception as e:
                    logger.debug(f"Compatibility check skipped for {file_path.name}: {e}")

            item = {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "temp_path": str(file_path), # Compatible with inspect / create_job pipeline
                "file_size": stat.st_size,
                "file_size_human": format_file_size(stat.st_size),
                "modified_at": stat.st_mtime,
                "app_name": metadata.get("app_name") or file_path.stem,
                "package_name": pkg or "unknown.package",
                "version_name": ver or "unknown",
                "icon_base64": metadata.get("icon_base64"),
                "is_valid_apk": metadata.get("is_valid_apk", False),
                "compatibility": compat_info,
            }

            _LIBRARY_CACHE[cache_key] = item
            apks.append(item)

        except Exception as e:
            logger.warning(f"Error reading library APK {file_path.name}: {e}")

    # Sort newest modified first
    apks.sort(key=lambda x: x.get("modified_at", 0), reverse=True)
    return apks

def get_library_apk(filename: str) -> Optional[Dict[str, Any]]:
    """Gets details of a single APK in the library."""
    safe_name = Path(filename).name
    file_path = get_library_dir() / safe_name
    if not file_path.exists():
        return None

    for item in list_library_apks():
        if item["file_name"] == safe_name:
            return item
    return None

def save_to_library(source_path: Path, custom_filename: Optional[str] = None) -> Dict[str, Any]:
    """Copies an APK file into the persistent library."""
    lib_dir = get_library_dir()
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    filename = Path(custom_filename or source_path.name).name
    if not filename.lower().endswith(".apk"):
        filename += ".apk"

    dest_path = lib_dir / filename
    # Avoid overwriting different files with the same name
    if dest_path.exists() and dest_path.resolve() != source_path.resolve():
        stem = dest_path.stem
        dest_path = lib_dir / f"{stem}_{int(time.time())}.apk"

    if dest_path.resolve() != source_path.resolve():
        shutil.copy2(str(source_path), str(dest_path))

    # Inspect to ensure validity
    meta = inspect_apk(dest_path)
    if not meta.get("is_valid_apk"):
        dest_path.unlink(missing_ok=True)
        raise ValueError("Uploaded file is not a valid Android APK package.")

    pkg = meta.get("package_name")
    ver = meta.get("version_name")
    compat_info = check_version_compatibility(pkg, ver) if pkg and ver else None

    stat = dest_path.stat()
    item = {
        "file_name": dest_path.name,
        "file_path": str(dest_path),
        "temp_path": str(dest_path),
        "file_size": stat.st_size,
        "file_size_human": format_file_size(stat.st_size),
        "modified_at": stat.st_mtime,
        "app_name": meta.get("app_name") or dest_path.stem,
        "package_name": pkg or "unknown.package",
        "version_name": ver or "unknown",
        "icon_base64": meta.get("icon_base64"),
        "is_valid_apk": True,
        "compatibility": compat_info,
    }

    cache_key = f"{dest_path.name}:{stat.st_mtime}:{stat.st_size}"
    _LIBRARY_CACHE[cache_key] = item
    return item

def delete_from_library(filename: str) -> bool:
    """Deletes an APK from the persistent library."""
    safe_name = Path(filename).name
    file_path = get_library_dir() / safe_name
    if file_path.exists():
        file_path.unlink()
        # Invalidate cache entries
        keys_to_del = [k for k in _LIBRARY_CACHE if k.startswith(f"{safe_name}:")]
        for k in keys_to_del:
            _LIBRARY_CACHE.pop(k, None)
        return True
    return False
