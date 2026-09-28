import os
import zipfile
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("morphe.apk_inspector")

KNOWN_PACKAGES = {
    "com.google.android.youtube": "YouTube",
    "com.google.android.apps.youtube.music": "YouTube Music",
    "com.reddit.frontpage": "Reddit",
    "com.twitter.android": "Twitter / X",
    "com.instagram.android": "Instagram",
    "com.spotify.music": "Spotify",
    "com.duolingo": "Duolingo",
    "tv.twitch.android.app": "Twitch",
    "org.telegram.messenger": "Telegram",
}

def inspect_apk(file_path: str | Path) -> Dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    file_size = path.stat().st_size
    info: Dict[str, Any] = {
        "file_name": path.name,
        "file_size": file_size,
        "file_size_human": format_file_size(file_size),
        "package_name": None,
        "version_name": None,
        "version_code": None,
        "app_name": path.stem,
        "icon_base64": None,
        "is_valid_apk": False,
    }

    try:
        from pyaxmlparser import APK
        apk = APK(str(path))
        if apk.is_valid_APK():
            info["package_name"] = apk.package
            info["version_name"] = apk.version_name
            info["version_code"] = apk.version_code
            info["is_valid_apk"] = True

            if apk.package in KNOWN_PACKAGES:
                info["app_name"] = KNOWN_PACKAGES[apk.package]
            elif apk.application:
                info["app_name"] = apk.application
    except Exception as e:
        logger.debug(f"pyaxmlparser inspection skipped or failed: {e}")

    try:
        with zipfile.ZipFile(path, "r") as z:
            info["is_valid_apk"] = "AndroidManifest.xml" in z.namelist()

            if not info["package_name"] and "AndroidManifest.xml" in z.namelist():
                manifest_bytes = z.read("AndroidManifest.xml")
                extracted = extract_metadata_from_axml_bytes(manifest_bytes)
                info.update({k: v for k, v in extracted.items() if v is not None})

            icon_data = extract_best_icon(z)
            if icon_data:
                info["icon_base64"] = f"data:image/png;base64,{base64.b64encode(icon_data).decode('utf-8')}"

    except Exception as e:
        logger.warning(f"Error inspecting APK zip contents: {e}")

    if info["package_name"] and info["package_name"] in KNOWN_PACKAGES:
        info["app_name"] = KNOWN_PACKAGES[info["package_name"]]

    return info

def extract_best_icon(z: zipfile.ZipFile) -> Optional[bytes]:
    candidates = []
    for name in z.namelist():
        lower = name.lower()
        if (
            ("mipmap" in lower or "drawable" in lower)
            and ("ic_launcher" in lower or "app_icon" in lower or "icon" in lower)
            and lower.endswith(".png")
        ):
            score = 0
            if "xxxhdpi" in lower:
                score = 5
            elif "xxhdpi" in lower:
                score = 4
            elif "xhdpi" in lower:
                score = 3
            elif "hdpi" in lower:
                score = 2
            elif "mdpi" in lower:
                score = 1
            candidates.append((score, name))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_icon_path = candidates[0][1]
        try:
            return z.read(best_icon_path)
        except Exception:
            pass
    return None

def extract_metadata_from_axml_bytes(data: bytes) -> Dict[str, Optional[str]]:
    res: Dict[str, Optional[str]] = {
        "package_name": None,
        "version_name": None,
    }

    strings = []
    current = bytearray()
    for b in data:
        if 32 <= b <= 126:
            current.append(b)
        else:
            if len(current) >= 3:
                strings.append(current.decode("ascii", errors="ignore"))
            current = bytearray()

    for s in strings:
        if "." in s and not s.startswith("http") and not s.endswith(".xml"):
            parts = s.split(".")
            if len(parts) >= 2 and parts[0] in ("com", "org", "net", "io", "tv", "app"):
                if all(p.isalnum() or "_" in p for p in parts):
                    res["package_name"] = s
                    break

    for s in strings:
        if any(char.isdigit() for char in s) and "." in s:
            parts = s.split(".")
            if len(parts) in (2, 3, 4) and parts[0].isdigit():
                res["version_name"] = s
                break

    return res

def format_file_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

