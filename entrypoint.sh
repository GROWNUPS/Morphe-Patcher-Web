#!/bin/bash
set -e

# User and Group ID mapping for NAS / Linux file permissions
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "[INFO] Starting Patchium Web Service (PUID=${PUID}, PGID=${PGID})..."

# Create group and user if they do not exist
if ! getent group morphe >/dev/null 2>&1; then
    groupadd -g "$PGID" morphe
fi

if ! id -u morphe >/dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -d /app -s /bin/bash morphe
fi

# Ensure critical directories exist (including morphe data working directories)
mkdir -p /app/morphe /app/cache/morphe /app/cache/tmp /app/watch /app/output /app/config /app/cache /app/config/keystore /app/config/profiles

# Fix directory ownership
chown "$PUID":"$PGID" /app
chown -R "$PUID":"$PGID" /app/morphe /app/cache /app/watch /app/output /app/config
chmod 775 /app
chmod -R 775 /app/morphe /app/cache /app/watch /app/output /app/config

# Auto-download Morphe Desktop JAR if not mounted or cached
MORPHE_VERSION=${MORPHE_VERSION:-v1.17.0}
JAR_URL="https://github.com/MorpheApp/morphe-desktop/releases/download/${MORPHE_VERSION}/morphe-desktop-${MORPHE_VERSION#v}-all.jar"

if [ ! -f "/app/morphe-desktop.jar" ] && [ ! -f "/app/config/morphe-desktop.jar" ]; then
    echo "[INFO] Downloading Morphe Desktop JAR (${MORPHE_VERSION})..."
    curl -sSL -f -o /app/morphe-desktop.jar "$JAR_URL" || echo "[WARN] Could not auto-download Morphe JAR (check internet connectivity or mount your own)."
fi

# Auto-download Morphe Patches (.mpp) if missing
if [ ! -f "/app/config/patches.mpp" ] && [ ! -f "/app/patches.mpp" ]; then
    echo "[INFO] Fetching latest Morphe Patches bundle (.mpp) from GitHub..."
    python3 -c "
import urllib.request, json, shutil
try:
    req = urllib.request.Request('https://api.github.com/repos/MorpheApp/morphe-patches/releases/latest', headers={'User-Agent': 'Patchium/1.0'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    url = None
    tag = data.get('tag_name')
    for a in data.get('assets', []):
        if a.get('name', '').endswith('.mpp'):
            url = a.get('browser_download_url')
            break
    if url:
        with urllib.request.urlopen(url, timeout=120) as resp, open('/app/config/patches.mpp', 'wb') as f:
            shutil.copyfileobj(resp, f)
        print(f'[INFO] Downloaded Morphe Patches {tag} successfully.')
except Exception as e:
    print(f'[WARN] Could not auto-download patches.mpp: {e}')
" || true
fi

# Set permissions and ownership on JAR if present
if [ -f "/app/morphe-desktop.jar" ]; then
    chown "$PUID":"$PGID" /app/morphe-desktop.jar 2>/dev/null || true
    chmod 664 /app/morphe-desktop.jar 2>/dev/null || true
fi

# Ensure MORPHE_DATA_DIR environment variable is set
export MORPHE_DATA_DIR="${MORPHE_DATA_DIR:-/app/cache/morphe}"
mkdir -p "$MORPHE_DATA_DIR"
chown -R "$PUID":"$PGID" "$MORPHE_DATA_DIR"
chmod -R 775 "$MORPHE_DATA_DIR"

echo "[INFO] Launching Uvicorn ASGI Server on port ${PORT:-8080}..."

# Execute server as the specified user with MORPHE_DATA_DIR exported
exec gosu "$PUID":"$PGID" python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"

