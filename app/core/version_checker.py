import re
import time
import logging
import subprocess
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.config import MORPHE_JAR, PATCHES_FILE

logger = logging.getLogger("morphe.version_checker")

KNOWN_APP_NAMES = {
    "com.google.android.youtube": "YouTube",
    "com.google.android.apps.youtube.music": "YouTube Music",
    "com.reddit.frontpage": "Reddit",
    "com.twitter.android": "Twitter / X",
    "tv.twitch.android.app": "Twitch",
    "com.spotify.music": "Spotify",
    "com.duolingo": "Duolingo",
    "org.telegram.messenger": "Telegram",
}

# In-memory cache for parsed compatible versions
_CACHE: Dict[str, Any] = {}
_CACHE_KEY: Optional[str] = None
_CACHE_TIMESTAMP: float = 0.0

def _parse_list_versions_output(output: str) -> Dict[str, Dict[str, Any]]:
    packages: Dict[str, Dict[str, Any]] = {}
    current_pkg: Optional[str] = None

    for line in output.splitlines():
        line = line.strip()
        if "Package name:" in line:
            current_pkg = line.split("Package name:")[-1].strip()
            packages[current_pkg] = {
                "package_name": current_pkg,
                "app_name": KNOWN_APP_NAMES.get(current_pkg, current_pkg.split(".")[-1].capitalize()),
                "versions": [],
                "recommended": None,
                "patch_count": 0,
            }
        elif current_pkg and "(" in line and "patches)" in line:
            # Pattern: 21.16.256 (83 patches)
            m = re.match(r"^([\d\.\w\-_]+)\s*\((\d+)\s+patches?\)", line)
            if m:
                ver = m.group(1)
                count = int(m.group(2))
                packages[current_pkg]["versions"].append({
                    "version": ver,
                    "patch_count": count
                })
                if not packages[current_pkg]["recommended"]:
                    packages[current_pkg]["recommended"] = ver
                    packages[current_pkg]["patch_count"] = count

    return packages

def get_compatible_versions_data(patches_file: Optional[Path] = None, force_refresh: bool = False) -> Dict[str, Any]:
    global _CACHE, _CACHE_KEY, _CACHE_TIMESTAMP

    p_file = Path(patches_file) if patches_file else Path(PATCHES_FILE)
    jar_file = Path(MORPHE_JAR)

    if not p_file.exists() or not jar_file.exists():
        return {}

    try:
        current_mtime = p_file.stat().st_mtime
    except Exception:
        current_mtime = 0.0

    cache_key = f"{p_file}_{current_mtime}"
    if not force_refresh and cache_key == _CACHE_KEY and (time.time() - _CACHE_TIMESTAMP < 300):
        return _CACHE

    try:
        # Run list-versions for stable versions
        cmd_stable = [
            "java", "-jar", str(jar_file),
            "list-versions",
            "--patches", str(p_file)
        ]
        res_stable = subprocess.run(cmd_stable, capture_output=True, text=True, timeout=20)
        stable_data = _parse_list_versions_output(res_stable.stdout)

        # Run list-versions with experimental versions
        cmd_exp = [
            "java", "-jar", str(jar_file),
            "list-versions",
            "--patches", str(p_file),
            "--include-experimental"
        ]
        res_exp = subprocess.run(cmd_exp, capture_output=True, text=True, timeout=20)
        exp_data = _parse_list_versions_output(res_exp.stdout)

        results: Dict[str, Any] = {}

        all_pkg_keys = set(list(stable_data.keys()) + list(exp_data.keys()))
        for pkg in all_pkg_keys:
            st = stable_data.get(pkg, {})
            ex = exp_data.get(pkg, {})

            app_name = KNOWN_APP_NAMES.get(pkg) or st.get("app_name") or ex.get("app_name") or pkg.split(".")[-1].capitalize()
            rec = st.get("recommended") or ex.get("recommended")
            patch_count = st.get("patch_count") or ex.get("patch_count", 0)

            stable_vers = [v["version"] for v in st.get("versions", [])]
            all_vers = [v["version"] for v in ex.get("versions", [])]
            exp_vers = [v for v in all_vers if v not in stable_vers]

            search_query = urllib.parse.quote_plus(f"{app_name} {rec}" if rec else app_name)
            apkmirror_url = f"https://www.apkmirror.com/?post_type=app_release&searchtype=apk&s={search_query}"

            results[pkg] = {
                "package_name": pkg,
                "app_name": app_name,
                "recommended_version": rec,
                "patch_count": patch_count,
                "stable_versions": stable_vers,
                "experimental_versions": exp_vers,
                "all_compatible_versions": all_vers if all_vers else stable_vers,
                "apkmirror_url": apkmirror_url,
            }

        _CACHE = results
        _CACHE_KEY = cache_key
        _CACHE_TIMESTAMP = time.time()
        logger.info(f"Loaded compatible version rules for {len(results)} packages from {p_file.name}")
        return results

    except Exception as e:
        logger.warning(f"Failed to fetch compatible versions from Morphe CLI: {e}")
        return _CACHE or {}

def check_apk_compatibility(package_name: Optional[str], version_name: Optional[str], patches_file: Optional[Path] = None) -> Dict[str, Any]:
    if not package_name:
        return {
            "status": "UNKNOWN",
            "badge_text": "Universal App",
            "badge_class": "badge-info",
            "recommended_version": None,
            "is_recommended": False,
            "is_compatible": True,
            "patch_count": None,
            "message": "Universal patches will be applied.",
            "apkmirror_url": None,
        }

    all_data = get_compatible_versions_data(patches_file)
    pkg_data = all_data.get(package_name)

    if not pkg_data:
        app_name = KNOWN_APP_NAMES.get(package_name, package_name.split(".")[-1].capitalize())
        return {
            "status": "UNKNOWN",
            "app_name": app_name,
            "package_name": package_name,
            "badge_text": "Universal App",
            "badge_class": "badge-info",
            "recommended_version": None,
            "is_recommended": False,
            "is_compatible": True,
            "patch_count": None,
            "message": f"No package-specific restrictions found. Universal patches available.",
            "apkmirror_url": None,
        }

    rec = pkg_data.get("recommended_version")
    stables = pkg_data.get("stable_versions", [])
    experimentals = pkg_data.get("experimental_versions", [])
    app_name = pkg_data.get("app_name", "App")
    patch_count = pkg_data.get("patch_count", 0)

    clean_ver = (version_name or "").strip()
    apkmirror_url = pkg_data.get("apkmirror_url")

    # 1. Exact match with recommended
    if rec and clean_ver == rec:
        return {
            "status": "RECOMMENDED",
            "app_name": app_name,
            "package_name": package_name,
            "badge_text": f"Target Version ({rec})",
            "badge_class": "badge-success",
            "recommended_version": rec,
            "is_recommended": True,
            "is_compatible": True,
            "patch_count": patch_count,
            "message": f"Optimal target version! Matches Morphe's most stable recommended release ({patch_count} patches).",
            "apkmirror_url": apkmirror_url,
        }

    # 2. In stable compatible list (older verified version)
    if clean_ver in stables:
        return {
            "status": "COMPATIBLE",
            "app_name": app_name,
            "package_name": package_name,
            "badge_text": f"Compatible Version",
            "badge_class": "badge-primary",
            "recommended_version": rec,
            "is_recommended": False,
            "is_compatible": True,
            "patch_count": patch_count,
            "message": f"Tested compatible version ({patch_count} patches). Recommended version is v{rec}.",
            "apkmirror_url": apkmirror_url,
        }

    # 3. In experimental list
    if clean_ver in experimentals:
        return {
            "status": "EXPERIMENTAL",
            "app_name": app_name,
            "package_name": package_name,
            "badge_text": f"Experimental Version",
            "badge_class": "badge-warning",
            "recommended_version": rec,
            "is_recommended": False,
            "is_compatible": True,
            "patch_count": patch_count,
            "message": f"Experimental version detected. Patches may work, but recommended stable version is v{rec}.",
            "apkmirror_url": apkmirror_url,
        }

    # 4. Untested version
    return {
        "status": "UNTESTED",
        "app_name": app_name,
        "package_name": package_name,
        "badge_text": f"Untested Version (v{clean_ver or '?'})",
        "badge_class": "badge-danger",
        "recommended_version": rec,
        "is_recommended": False,
        "is_compatible": False,
        "patch_count": patch_count,
        "message": f"Untested version! Morphe has not validated v{clean_ver}. Patches may fail or crash. Recommended stable version: v{rec}.",
        "apkmirror_url": apkmirror_url,
    }
