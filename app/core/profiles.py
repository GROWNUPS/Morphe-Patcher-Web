import json
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.config import PROFILES_DIR

logger = logging.getLogger("patchium.profiles")

# Known packages mapping for quick reference
POPULAR_PACKAGES = [
    {"package": "com.google.android.youtube", "name": "YouTube", "icon": "📺"},
    {"package": "com.google.android.apps.youtube.music", "name": "YouTube Music", "icon": "🎵"},
    {"package": "com.reddit.frontpage", "name": "Reddit", "icon": "🤖"},
    {"package": "com.twitter.android", "name": "Twitter / X", "icon": "🐦"},
    {"package": "com.spotify.music", "name": "Spotify", "icon": "🎧"},
    {"package": "tv.twitch.android.app", "name": "Twitch", "icon": "🟣"},
    {"package": "*", "name": "Universal (Any App)", "icon": "🌐"},
]

def sanitize_id(name: str) -> str:
    """Convert a name into a safe filesystem-friendly slug."""
    clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name.strip().lower())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean or "profile"

def resolve_naming_template(template: str, app_name: str, version: str = "", arch: str = "") -> str:
    """
    Resolves naming placeholders like {appName} or {app_name}.
    Example: '{appName} Morphe' with app_name 'YouTube' -> 'YouTube Morphe'
    """
    if not template:
        return app_name or "App"
    
    clean_app = app_name or "App"
    res = template
    res = res.replace("{appName}", clean_app)
    res = res.replace("{app_name}", clean_app)
    res = res.replace("{app}", clean_app)
    res = res.replace("{version}", version or "")
    res = res.replace("{ver}", version or "")
    res = res.replace("{arch}", arch or "")
    return res.strip()

def resolve_filename_template(template: str, app_name: str, version: str = "", arch: str = "") -> str:
    """
    Resolves output filename placeholders.
    Example: '{appName}_{version}_{arch}_patched.apk'
    """
    clean_app = re.sub(r'[^a-zA-Z0-9]', '_', (app_name or "app").lower())
    clean_app = re.sub(r'_+', '_', clean_app).strip('_')
    
    clean_ver = re.sub(r'[^a-zA-Z0-9\.]', '_', (version or "").strip())
    
    arch_tag = ""
    if arch in ("arm64-v8a", "arm64"):
        arch_tag = "arm64"
    elif arch in ("armeabi-v7a", "arm32"):
        arch_tag = "arm32"
    elif arch:
        arch_tag = arch
    else:
        arch_tag = "universal"

    if not template:
        template = "{appName}_{version}_{arch}_patched.apk"

    out = template
    out = out.replace("{appName}", clean_app)
    out = out.replace("{app_name}", clean_app)
    out = out.replace("{app}", clean_app)
    out = out.replace("{version}", clean_ver)
    out = out.replace("{ver}", clean_ver)
    out = out.replace("{arch}", arch_tag)
    
    # Clean double underscores and sanitize
    out = re.sub(r'_+', '_', out)
    out = out.replace("._", ".").replace("_.", ".")
    if not out.lower().endswith(".apk"):
        out += ".apk"
    return out

def _normalize_profile(file_path: Path, raw_data: Any) -> Dict[str, Any]:
    """Normalizes raw json from disk into standard Profile structure."""
    file_id = file_path.stem
    if isinstance(raw_data, list):
        # Legacy raw Morphe options JSON
        return {
            "id": file_id,
            "name": file_id,
            "package_name": file_id if "." in file_id else "*",
            "description": "Legacy Morphe options file",
            "branding": "original",
            "custom_app_name": "",
            "output_format": "{appName}_{version}_{arch}_patched.apk",
            "optimize_arch": True,
            "target_arch": "arm64-v8a",
            "is_default": False,
            "is_legacy": True,
            "raw_options": raw_data,
        }
    
    if not isinstance(raw_data, dict):
        raw_data = {}

    profile_id = raw_data.get("id") or file_id
    package_name = raw_data.get("package_name") or (file_id if "." in file_id else "*")
    name = raw_data.get("name") or profile_id.replace("_", " ").title()

    return {
        "id": profile_id,
        "name": name,
        "package_name": package_name,
        "description": raw_data.get("description", ""),
        "branding": raw_data.get("branding", "original"),
        "custom_app_name": raw_data.get("custom_app_name", "{appName} Morphe"),
        "output_format": raw_data.get("output_format", "{appName}_{version}_{arch}_patched.apk"),
        "optimize_arch": raw_data.get("optimize_arch", True),
        "target_arch": raw_data.get("target_arch", "arm64-v8a"),
        "is_default": raw_data.get("is_default", False),
        "include_patches": raw_data.get("include_patches", []),
        "exclude_patches": raw_data.get("exclude_patches", []),
        "patch_options": raw_data.get("patch_options", {}),
        "is_legacy": False,
    }

def list_profiles(package_name: Optional[str] = None, skip_ensure: bool = False) -> List[Dict[str, Any]]:
    """List all profiles, optionally filtered by package_name (includes universal * profiles)."""
    if not skip_ensure:
        ensure_default_profiles()
    profiles: List[Dict[str, Any]] = []

    if not PROFILES_DIR.exists():
        return profiles

    for file_path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            prof = _normalize_profile(file_path, data)
            profiles.append(prof)
        except Exception as e:
            logger.warning(f"Failed to read profile {file_path.name}: {e}")

    if package_name:
        pkg_lower = package_name.strip().lower()
        filtered = [
            p for p in profiles
            if p["package_name"] == "*" or p["package_name"].lower() == pkg_lower
        ]
        # Sort so defaults and exact matches appear first
        filtered.sort(key=lambda x: (not x.get("is_default", False), x["package_name"] == "*", x["name"]))
        return filtered

    # Sort so default profiles and package matches appear first
    profiles.sort(key=lambda x: (x["package_name"] == "*", not x.get("is_default", False), x["name"]))
    return profiles

def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    """Get single profile by ID."""
    safe_id = sanitize_id(profile_id)
    file_path = PROFILES_DIR / f"{safe_id}.json"
    if not file_path.exists():
        # Check by name matching if ID didn't match directly
        for p in list_profiles():
            if p["id"] == profile_id or p["name"].lower() == profile_id.lower():
                return p
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_profile(file_path, data)
    except Exception as e:
        logger.error(f"Error loading profile {safe_id}: {e}")
        return None

def get_default_profile_for_package(package_name: str) -> Optional[Dict[str, Any]]:
    """Finds the default profile configured for a specific package, or universal default."""
    if not package_name:
        return None

    pkg_lower = package_name.strip().lower()
    profiles = list_profiles()

    # 1. Exact package match with is_default == True
    for p in profiles:
        if p["package_name"].lower() == pkg_lower and p.get("is_default"):
            return p

    # 2. Exact package match (first found)
    for p in profiles:
        if p["package_name"].lower() == pkg_lower:
            return p

    # 3. Universal profile with is_default == True
    for p in profiles:
        if p["package_name"] == "*" and p.get("is_default"):
            return p

    return None

def save_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update a profile."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    name = data.get("name", "").strip() or "Custom Profile"
    profile_id = data.get("id") or sanitize_id(name)
    profile_id = sanitize_id(profile_id)

    pkg = data.get("package_name", "*").strip()
    is_default = bool(data.get("is_default", False))

    # If this profile is marked as default, unset default for others with the same package
    if is_default:
        for existing in list_profiles(skip_ensure=True):
            if existing["id"] != profile_id and existing["package_name"].lower() == pkg.lower() and existing.get("is_default"):
                existing["is_default"] = False
                _write_profile_to_disk(existing["id"], existing)

    profile_obj = {
        "id": profile_id,
        "name": name,
        "package_name": pkg,
        "description": data.get("description", "").strip(),
        "branding": data.get("branding", "custom"),
        "custom_app_name": data.get("custom_app_name", "{appName} Morphe"),
        "output_format": data.get("output_format", "{appName}_{version}_{arch}_patched.apk"),
        "optimize_arch": bool(data.get("optimize_arch", True)),
        "target_arch": data.get("target_arch", "arm64-v8a"),
        "is_default": is_default,
        "include_patches": data.get("include_patches", []),
        "exclude_patches": data.get("exclude_patches", []),
        "patch_options": data.get("patch_options", {}),
    }

    _write_profile_to_disk(profile_id, profile_obj)
    return profile_obj

def _write_profile_to_disk(profile_id: str, data: Dict[str, Any]):
    file_path = PROFILES_DIR / f"{profile_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def set_default_profile(profile_id: str) -> bool:
    """Sets a profile as default for its package."""
    prof = get_profile(profile_id)
    if not prof:
        return False
    prof["is_default"] = True
    save_profile(prof)
    return True

def delete_profile(profile_id: str) -> bool:
    """Deletes a profile from disk."""
    safe_id = sanitize_id(profile_id)
    file_path = PROFILES_DIR / f"{safe_id}.json"
    if file_path.exists():
        file_path.unlink()
        return True
    return False

def ensure_default_profiles():
    """Initializes starter profiles if config/profiles is empty or needs seeding."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    existing_files = list(PROFILES_DIR.glob("*.json"))
    
    # If starter profiles don't exist yet, seed them
    youtube_path = PROFILES_DIR / "youtube_morphe.json"
    yt_music_path = PROFILES_DIR / "youtube_music_morphe.json"
    reddit_path = PROFILES_DIR / "reddit_clean.json"

    # Only seed if no modern profiles exist
    if not youtube_path.exists() and len([f for f in existing_files if not f.name.startswith("com.")]) == 0:
        logger.info("Seeding default starter profiles...")
        
        # 1. YouTube Morphe
        save_profile({
            "id": "youtube_morphe",
            "name": "YouTube Morphe",
            "package_name": "com.google.android.youtube",
            "description": "Default preset for YouTube with Morphe branding and ARM64 optimization.",
            "branding": "custom",
            "custom_app_name": "{appName} Morphe",
            "output_format": "{appName}_{version}_{arch}_patched.apk",
            "optimize_arch": True,
            "target_arch": "arm64-v8a",
            "is_default": True,
        })

        # 2. YouTube Music Morphe
        save_profile({
            "id": "youtube_music_morphe",
            "name": "YouTube Music Morphe",
            "package_name": "com.google.android.apps.youtube.music",
            "description": "Default preset for YouTube Music with Morphe branding.",
            "branding": "custom",
            "custom_app_name": "{appName} Morphe",
            "output_format": "{appName}_{version}_{arch}_patched.apk",
            "optimize_arch": True,
            "target_arch": "arm64-v8a",
            "is_default": True,
        })

        # 3. Reddit Clean
        save_profile({
            "id": "reddit_clean",
            "name": "Reddit Clean",
            "package_name": "com.reddit.frontpage",
            "description": "Ad-free Reddit with original stock branding and icon.",
            "branding": "original",
            "custom_app_name": "",
            "output_format": "{appName}_{version}_{arch}_patched.apk",
            "optimize_arch": True,
            "target_arch": "arm64-v8a",
            "is_default": True,
        })

        # 4. Universal Morphe (for any app)
        save_profile({
            "id": "universal_morphe",
            "name": "Universal Morphe Suffix",
            "package_name": "*",
            "description": "Appends 'Morphe' to the detected app name for any application.",
            "branding": "custom",
            "custom_app_name": "{appName} Morphe",
            "output_format": "{appName}_{version}_{arch}_patched.apk",
            "optimize_arch": True,
            "target_arch": "arm64-v8a",
            "is_default": False,
        })
