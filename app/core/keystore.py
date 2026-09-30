import json
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.config import (
    KEYSTORE_PATH,
    KEYSTORE_PASSWORD,
    KEYSTORE_ALIAS,
    KEYSTORE_KEY_PASSWORD,
    KEYSTORE_CONFIG_FILE,
)

logger = logging.getLogger("morphe.keystore")

def get_active_keystore_config() -> Dict[str, Any]:
    if KEYSTORE_CONFIG_FILE.exists():
        try:
            with open(KEYSTORE_CONFIG_FILE, "r") as f:
                data = json.load(f)
            p = Path(data.get("path", str(KEYSTORE_PATH)))
            if p.exists() and p.stat().st_size > 0:
                return {
                    "path": str(p),
                    "password": data.get("password", KEYSTORE_PASSWORD),
                    "alias": data.get("alias", KEYSTORE_ALIAS),
                    "key_password": data.get("key_password", data.get("password", KEYSTORE_KEY_PASSWORD)),
                    "is_custom": data.get("is_custom", False),
                    "filename": p.name,
                }
        except Exception as e:
            logger.warning(f"Error reading keystore config: {e}. Falling back to default.")

    return {
        "path": str(KEYSTORE_PATH),
        "password": KEYSTORE_PASSWORD,
        "alias": KEYSTORE_ALIAS,
        "key_password": KEYSTORE_KEY_PASSWORD,
        "is_custom": False,
        "filename": KEYSTORE_PATH.name,
    }

def ensure_keystore() -> bool:
    """
    Ensures that a persistent keystore exists.
    If not, creates one using keytool so that all patched APKs share
    the exact same signing key across updates.
    """
    cfg = get_active_keystore_config()
    target_path = Path(cfg["path"])
    if target_path.exists() and target_path.stat().st_size > 0:
        logger.info(f"Using active keystore at {target_path} (is_custom={cfg['is_custom']})")
        return True

    KEYSTORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Generating new persistent keystore at {KEYSTORE_PATH}...")

    cmd = [
        "keytool",
        "-genkeypair",
        "-v",
        "-keystore", str(KEYSTORE_PATH),
        "-alias", KEYSTORE_ALIAS,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", KEYSTORE_PASSWORD,
        "-keypass", KEYSTORE_KEY_PASSWORD,
        "-dname", "CN=Patchium, OU=SelfHosted, O=Patchium, L=Server, S=Global, C=US"
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Persistent keystore generated successfully: {KEYSTORE_PATH}")
        return True
    except FileNotFoundError:
        logger.warning("keytool binary not found. Will rely on Morphe's internal keystore generation.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to generate keystore: {e.stderr}")
        return False

def inspect_keystore(keystore_path: Path, storepass: str, alias: Optional[str] = None) -> Dict[str, Any]:
    if not keystore_path.exists():
        raise FileNotFoundError(f"Keystore file not found: {keystore_path}")

    cmd = ["keytool", "-list", "-v", "-keystore", str(keystore_path), "-storepass", storepass]
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode != 0:
        err = res.stdout.strip() or res.stderr.strip()
        first_line = err.splitlines()[0] if err else "Invalid keystore or incorrect password"
        if "password was incorrect" in err.lower() or "tampered" in err.lower():
            raise ValueError("Keystore password was incorrect.")
        raise ValueError(first_line)

    output = res.stdout

    # Find all aliases in keystore
    aliases = [a.strip() for a in re.findall(r"Alias name:\s*(.+)", output)]
    target_alias = alias.strip() if alias and alias.strip() else (aliases[0] if aliases else KEYSTORE_ALIAS)

    if alias and alias.strip() and target_alias not in aliases:
        raise ValueError(f"Alias '{alias}' not found in keystore. Available aliases: {', '.join(aliases)}")

    sha256_match = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", output)
    sha1_match = re.search(r"SHA1:\s*([0-9A-Fa-f:]+)", output)
    valid_match = re.search(r"Valid from:\s*(.+)", output)
    owner_match = re.search(r"Owner:\s*(.+)", output)

    return {
        "valid": True,
        "path": str(keystore_path),
        "filename": keystore_path.name,
        "alias": target_alias,
        "all_aliases": aliases,
        "sha256": sha256_match.group(1).strip() if sha256_match else None,
        "sha1": sha1_match.group(1).strip() if sha1_match else None,
        "validity": valid_match.group(1).strip() if valid_match else None,
        "owner": owner_match.group(1).strip() if owner_match else None,
        "size_bytes": keystore_path.stat().st_size,
    }

def set_custom_keystore(
    keystore_path: Path,
    storepass: str,
    alias: Optional[str] = None,
    keypass: Optional[str] = None,
) -> Dict[str, Any]:
    info = inspect_keystore(keystore_path, storepass, alias)
    chosen_alias = info["alias"]
    effective_keypass = (keypass.strip() if keypass and keypass.strip() else storepass)

    cfg = {
        "path": str(keystore_path),
        "password": storepass,
        "alias": chosen_alias,
        "key_password": effective_keypass,
        "is_custom": True,
        "filename": keystore_path.name,
    }

    KEYSTORE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYSTORE_CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

    logger.info(f"Custom keystore activated: {keystore_path.name} (alias: {chosen_alias})")
    info["is_custom"] = True
    return info

def reset_default_keystore() -> Dict[str, Any]:
    if KEYSTORE_CONFIG_FILE.exists():
        try:
            KEYSTORE_CONFIG_FILE.unlink()
        except Exception as e:
            logger.warning(f"Error removing keystore config: {e}")

    ensure_keystore()
    return get_keystore_info()

def get_keystore_cli_args() -> List[str]:
    cfg = get_active_keystore_config()
    p = Path(cfg["path"])
    if p.exists() and p.stat().st_size > 0:
        return [
            "--keystore", str(p),
            "--keystore-password", cfg["password"],
            "--keystore-entry-alias", cfg["alias"],
            "--keystore-entry-password", cfg["key_password"],
        ]
    return []

def get_keystore_info() -> Dict[str, Any]:
    cfg = get_active_keystore_config()
    p = Path(cfg["path"])
    exists = p.exists() and p.stat().st_size > 0
    details: Dict[str, Any] = {
        "exists": exists,
        "path": str(p),
        "filename": p.name,
        "alias": cfg["alias"],
        "is_custom": cfg.get("is_custom", False),
        "size_bytes": p.stat().st_size if exists else 0,
    }

    if exists:
        try:
            inspected = inspect_keystore(p, cfg["password"], cfg["alias"])
            details.update({
                "sha256": inspected.get("sha256"),
                "sha1": inspected.get("sha1"),
                "validity": inspected.get("validity"),
                "owner": inspected.get("owner"),
                "all_aliases": inspected.get("all_aliases", []),
            })
        except Exception as e:
            logger.warning(f"Could not inspect active keystore: {e}")

    return details

