import os
import time
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Set, Dict, Any, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from app.config import (
    WATCH_DIR,
    PROFILES_DIR,
    WATCH_DEBOUNCE_SECONDS,
    WATCH_ACTION_AFTER_PATCH,
    AUTO_WATCH,
)
from app.core.apk_inspector import inspect_apk
from app.core.queue_manager import queue_manager, Job
from app.core.profiles import (
    get_default_profile_for_package,
    resolve_naming_template,
    resolve_filename_template,
)

logger = logging.getLogger("morphe.watcher")

class HotFolderHandler(FileSystemEventHandler):
    def __init__(self, watcher_instance: "HotFolderWatcher"):
        super().__init__()
        self.watcher = watcher_instance

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".apk"):
            self.watcher.handle_candidate_file(Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".apk"):
            self.watcher.handle_candidate_file(Path(event.src_path))

class HotFolderWatcher:
    def __init__(self):
        self.watch_dir = Path(WATCH_DIR)
        self.processed_dir = self.watch_dir / "processed"
        self.observer: Optional[Observer] = None
        self.processing_files: Set[Path] = set()
        self.recent_events: list[dict] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self, loop: asyncio.AbstractEventLoop):
        if not AUTO_WATCH:
            logger.info("Hot-folder watcher is disabled via AUTO_WATCH=false")
            return

        self._loop = loop
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.scan_existing_files()

        event_handler = HotFolderHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        logger.info(f"Hot-Folder Watcher running on: {self.watch_dir}")

    def scan_existing_files(self):
        for item in self.watch_dir.iterdir():
            if item.is_file() and item.suffix.lower() == ".apk":
                self.handle_candidate_file(item)

    def handle_candidate_file(self, file_path: Path):
        if "processed" in file_path.parts or file_path.name.startswith("."):
            return

        if file_path in self.processing_files:
            return

        self.processing_files.add(file_path)
        logger.info(f"New APK detected in hot folder: {file_path.name}")
        self.recent_events.append({
            "timestamp": time.time(),
            "filename": file_path.name,
            "status": "DETECTED"
        })

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._process_file_with_debounce(file_path), self._loop)
        else:
            asyncio.create_task(self._process_file_with_debounce(file_path))

    async def _process_file_with_debounce(self, file_path: Path):
        try:
            stable = await self._wait_until_file_stable(file_path)
            if not stable:
                logger.warning(f"File {file_path.name} was removed or could not stabilize.")
                return

            logger.info(f"File stabilized: {file_path.name}. Inspecting package...")

            info = inspect_apk(file_path)
            pkg = info.get("package_name") or "unknown"
            ver = info.get("version_name") or "unknown"
            app_name = info.get("app_name") or file_path.stem

            profile = get_default_profile_for_package(pkg)
            options_file = None
            if profile and profile.get("is_legacy"):
                prof_file = PROFILES_DIR / f"{profile['id']}.json"
                if prof_file.exists():
                    options_file = prof_file

            strip_libs = profile.get("target_arch", "arm64-v8a") if profile and profile.get("optimize_arch") else "arm64-v8a"

            if profile and profile.get("output_format"):
                out_filename = resolve_filename_template(
                    profile["output_format"],
                    app_name=app_name,
                    version=ver,
                    arch=strip_libs,
                )
            else:
                clean_app = app_name.lower().replace(" ", "_")
                out_filename = f"{clean_app}_{ver}_morphe_patched.apk"

            branding = profile.get("branding", "custom") if profile else "custom"
            custom_app_name = profile.get("custom_app_name", "{appName} Morphe") if profile else "{appName} Morphe"

            excludes = list(profile.get("exclude_patches", [])) if profile else []
            includes = list(profile.get("include_patches", [])) if profile else []
            patch_options = None

            if branding == "original":
                if "Custom branding" not in excludes:
                    excludes.append("Custom branding")
                if "Change header" not in excludes:
                    excludes.append("Change header")
            elif branding == "custom" and custom_app_name:
                resolved_app_name = resolve_naming_template(
                    custom_app_name,
                    app_name=app_name,
                    version=ver,
                    arch=strip_libs,
                )
                patch_options = {
                    "Custom branding": {
                        "customName": resolved_app_name
                    }
                }

            job = Job(
                input_path=file_path,
                output_filename=out_filename,
                source="HOT_FOLDER",
                package_name=pkg,
                version_name=ver,
                options_file=options_file,
                include_patches=includes if includes else None,
                exclude_patches=excludes if excludes else None,
                strip_libs=strip_libs,
                patch_options=patch_options,
            )
            prof_label = f" with profile '{profile['name']}'" if profile else ""
            job.add_log(f"Auto-detected in watch folder. Target: {pkg} ({ver}){prof_label}")
            await queue_manager.submit_job(job)

            asyncio.create_task(self._handle_post_patch_action(job, file_path))

        except Exception as e:
            logger.exception(f"Error in hot-folder processor for {file_path.name}: {e}")
        finally:
            self.processing_files.discard(file_path)

    async def _wait_until_file_stable(self, path: Path) -> bool:
        last_size = -1
        stable_count = 0
        max_attempts = 120

        for _ in range(max_attempts):
            if not path.exists():
                return False

            try:
                current_size = path.stat().st_size
                if current_size > 0 and current_size == last_size:
                    stable_count += 1
                    if stable_count >= WATCH_DEBOUNCE_SECONDS:
                        with open(path, "rb") as f:
                            pass
                        return True
                else:
                    stable_count = 0
                    last_size = current_size
            except (OSError, PermissionError):
                stable_count = 0

            await asyncio.sleep(1)

        return False

    async def _handle_post_patch_action(self, job: Job, input_path: Path):
        while job.status in ("QUEUED", "RUNNING"):
            await asyncio.sleep(2)

        if not input_path.exists():
            return

        try:
            if WATCH_ACTION_AFTER_PATCH == "delete":
                input_path.unlink(missing_ok=True)
                logger.info(f"Deleted source APK after patching: {input_path.name}")
            elif WATCH_ACTION_AFTER_PATCH == "archive":
                self.processed_dir.mkdir(parents=True, exist_ok=True)
                dest = self.processed_dir / input_path.name
                shutil.move(str(input_path), str(dest))
                logger.info(f"Moved source APK to processed folder: {dest}")
        except Exception as e:
            logger.error(f"Error executing post-patch action for {input_path.name}: {e}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": AUTO_WATCH,
            "watch_dir": str(self.watch_dir),
            "pending_files": [p.name for p in self.processing_files],
            "recent_events": self.recent_events[-10:],
        }

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()

hot_folder_watcher = HotFolderWatcher()
