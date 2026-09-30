import os
from pathlib import Path

# Base Paths (Can be overridden by environment variables)
BASE_DIR = Path(__file__).resolve().parent.parent

WATCH_DIR = Path(os.getenv("WATCH_DIR", "/app/watch" if os.path.exists("/app") else str(BASE_DIR / "watch")))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/output" if os.path.exists("/app") else str(BASE_DIR / "output")))
CONFIG_DIR = Path(os.getenv("CONFIG_DIR", "/app/config" if os.path.exists("/app") else str(BASE_DIR / "config")))
CACHE_DIR = Path(os.getenv("CACHE_DIR", "/app/cache" if os.path.exists("/app") else str(BASE_DIR / "cache")))
MORPHE_DATA_DIR = Path(os.getenv("MORPHE_DATA_DIR", str(CACHE_DIR / "morphe")))

KEYSTORE_DIR = CONFIG_DIR / "keystore"
PROFILES_DIR = CONFIG_DIR / "profiles"
PATCHES_DIR = CONFIG_DIR / "patches"
KEYSTORE_CONFIG_FILE = KEYSTORE_DIR / "keystore_config.json"

# Ensure directories exist
for directory in [WATCH_DIR, OUTPUT_DIR, CONFIG_DIR, CACHE_DIR, MORPHE_DATA_DIR, KEYSTORE_DIR, PROFILES_DIR, PATCHES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

os.environ["MORPHE_DATA_DIR"] = str(MORPHE_DATA_DIR)

# Morphe Desktop / CLI JAR resolution
MORPHE_JAR = os.getenv("MORPHE_JAR_PATH")
if not MORPHE_JAR:
    for candidate in [
        CONFIG_DIR / "morphe-desktop.jar",
        Path("/app/morphe-desktop.jar"),
        BASE_DIR / "morphe-desktop.jar",
    ]:
        if candidate.exists():
            MORPHE_JAR = str(candidate)
            break
if not MORPHE_JAR:
    MORPHE_JAR = str(Path("/app/morphe-desktop.jar"))

# Patches .mpp file resolution
PATCHES_FILE = os.getenv("PATCHES_PATH")
if not PATCHES_FILE:
    for candidate in [
        CONFIG_DIR / "patches.mpp",
        Path("/app/patches.mpp"),
        BASE_DIR / "patches.mpp",
    ]:
        if candidate.exists():
            PATCHES_FILE = str(candidate)
            break
if not PATCHES_FILE:
    PATCHES_FILE = str(CONFIG_DIR / "patches.mpp")

# Execution settings
JAVA_CMD = os.getenv("JAVA_CMD", "java")
JAVA_OPTS = os.getenv("JAVA_OPTS", "-Xms256m -Xmx2048m -XX:+UseContainerSupport")
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")

# Hot-Folder Watcher settings
AUTO_WATCH = os.getenv("AUTO_WATCH", "true").lower() in ("true", "1", "yes")
WATCH_DEBOUNCE_SECONDS = int(os.getenv("WATCH_DEBOUNCE_SECONDS", "5"))
WATCH_ACTION_AFTER_PATCH = os.getenv("WATCH_ACTION_AFTER_PATCH", "archive")  # 'archive', 'delete', 'keep'

# Keystore defaults
KEYSTORE_PATH = KEYSTORE_DIR / "morphe.keystore"
KEYSTORE_PASSWORD = os.getenv("KEYSTORE_PASSWORD", "morphe123")
KEYSTORE_ALIAS = os.getenv("KEYSTORE_ALIAS", "morphe")
KEYSTORE_KEY_PASSWORD = os.getenv("KEYSTORE_KEY_PASSWORD", "morphe123")

# Webhook notification settings (Discord, Telegram, ntfy.sh, Gotify, etc.)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# App Release details
MORPHE_DOWNLOAD_URL = os.getenv(
    "MORPHE_DOWNLOAD_URL",
    "https://github.com/MorpheApp/morphe-desktop/releases/download/v1.17.0/morphe-desktop-1.17.0-all.jar"
)
PATCHES_DOWNLOAD_URL = os.getenv(
    "PATCHES_DOWNLOAD_URL",
    "https://github.com/MorpheApp/morphe-patches/releases/latest/download/patches.mpp"
)
MORPHE_PATCHES_REPO = os.getenv("MORPHE_PATCHES_REPO", "MorpheApp/morphe-patches")
PATCHES_META_FILE = CONFIG_DIR / "patches_meta.json"
AUTO_UPDATE_PATCHES = os.getenv("AUTO_UPDATE_PATCHES", "true").lower() in ("true", "1", "yes")
