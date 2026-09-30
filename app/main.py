import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    WATCH_DIR,
    OUTPUT_DIR,
    CONFIG_DIR,
    CACHE_DIR,
)
from app.core.keystore import ensure_keystore
from app.core.downloader import ensure_binaries
from app.core.queue_manager import queue_manager
from app.core.watcher import hot_folder_watcher

from app.api.routes_upload import router as upload_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_files import router as files_router
from app.api.routes_system import router as system_router
from app.api.routes_keystore import router as keystore_router
from app.api.routes_patches import router as patches_router
from app.api.routes_profiles import router as profiles_router
from app.api.routes_library import router as library_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("patchium.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Patchium Web Service...")

    ensure_keystore()
    queue_manager.start()

    loop = asyncio.get_running_loop()
    hot_folder_watcher.start(loop)

    asyncio.create_task(ensure_binaries())

    yield

    logger.info("Shutting down Patchium Web Service...")
    hot_folder_watcher.stop()

app = FastAPI(
    title="Patchium",
    description="Headless Remote Web Interface & Hot-Folder Automation for Android APK Patching",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(jobs_router)
app.include_router(files_router)
app.include_router(system_router)
app.include_router(keystore_router)
app.include_router(patches_router)
app.include_router(profiles_router)
app.include_router(library_router)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(static_dir / "index.html"))
