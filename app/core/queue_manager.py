import asyncio
import uuid
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.core.morphe_runner import MorpheRunner
from app.core.notifier import send_notification
from app.config import OUTPUT_DIR

logger = logging.getLogger("morphe.queue")

class Job:
    def __init__(
        self,
        input_path: Path,
        output_filename: Optional[str] = None,
        source: str = "WEB_UPLOAD",
        package_name: Optional[str] = None,
        version_name: Optional[str] = None,
        options_file: Optional[Path] = None,
        include_patches: Optional[List[str]] = None,
        exclude_patches: Optional[List[str]] = None,
        strip_libs: Optional[str] = None,
        patch_options: Optional[Dict[str, Dict[str, Any]]] = None,
        custom_patches_mpp: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.input_path = input_path
        self.input_filename = input_path.name
        self.package_name = package_name or "Unknown"
        self.version_name = version_name or "Unknown"
        self.source = source
        self.options_file = options_file
        self.include_patches = include_patches or []
        self.exclude_patches = exclude_patches or []
        self.strip_libs = strip_libs
        self.patch_options = patch_options
        self.custom_patches_mpp = custom_patches_mpp

        if not output_filename:
            base = input_path.stem.replace(".apk", "")
            output_filename = f"{base}-morphe-patched.apk"

        safe_out = Path(output_filename).name
        if not safe_out.lower().endswith(".apk"):
            safe_out += ".apk"

        self.output_filename = safe_out
        self.output_path = OUTPUT_DIR / safe_out

        self.status = "QUEUED"
        self.progress = 0
        self.current_phase = "QUEUED"
        self.logs: List[str] = []
        self.listeners: List[asyncio.Queue] = []
        self.error: Optional[str] = None

        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None

    def add_log(self, line: str, progress: Optional[int] = None, phase: Optional[str] = None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {line}"
        self.logs.append(entry)

        if progress is not None:
            self.progress = progress
        if phase is not None:
            self.current_phase = phase

        payload = {
            "type": "log",
            "job_id": self.id,
            "line": entry,
            "progress": self.progress,
            "phase": self.current_phase,
            "status": self.status,
        }
        for q in list(self.listeners):
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "input_filename": self.input_filename,
            "output_filename": self.output_filename,
            "package_name": self.package_name,
            "version_name": self.version_name,
            "source": self.source,
            "status": self.status,
            "progress": self.progress,
            "current_phase": self.current_phase,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "log_count": len(self.logs),
            "error": self.error,
        }

class QueueManager:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.current_job: Optional[Job] = None
        self.runner = MorpheRunner()
        self._worker_task: Optional[asyncio.Task] = None

    def start(self):
        if not self._worker_task:
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("Morphe Job Queue Worker started.")

    async def submit_job(self, job: Job) -> Job:
        self.jobs[job.id] = job
        await self.queue.put(job)
        job.add_log(f"Job queued (Position #{self.queue.qsize()})", 0, "QUEUED")
        return job

    async def _worker_loop(self):
        while True:
            job = await self.queue.get()
            self.current_job = job
            job.status = "RUNNING"
            job.started_at = time.time()
            job.add_log("Starting Morphe patch process...", 5, "INITIALIZING")

            def on_log(line: str, progress: Optional[int], phase: Optional[str]):
                job.add_log(line, progress, phase)

            try:
                result = await self.runner.run_patch(
                    input_apk=job.input_path,
                    output_apk=job.output_path,
                    options_file=job.options_file,
                    include_patches=job.include_patches,
                    exclude_patches=job.exclude_patches,
                    strip_libs=job.strip_libs,
                    patch_options=job.patch_options,
                    custom_patches_mpp=job.custom_patches_mpp,
                    log_callback=on_log,
                )

                job.completed_at = time.time()
                if result.get("success"):
                    job.status = "COMPLETED"
                    job.progress = 100
                    job.current_phase = "FINISHED"
                    job.add_log(f"Output APK generated: {job.output_filename}", 100, "COMPLETED")
                    asyncio.create_task(
                        send_notification(
                            title=f"Patch Succeeded: {job.output_filename}",
                            message=f"App: {job.package_name} ({job.version_name})\nSource: {job.source}\nSize: {job.output_path.stat().st_size // 1024 // 1024} MB",
                            status="success"
                        )
                    )
                else:
                    job.status = "FAILED"
                    job.error = result.get("error", "Patching process failed")
                    job.add_log(f"Patching failed: {job.error}", phase="FAILED")
                    asyncio.create_task(
                        send_notification(
                            title=f"Patch Failed: {job.input_filename}",
                            message=f"App: {job.package_name}\nError: {job.error}",
                            status="failed"
                        )
                    )

            except Exception as e:
                logger.exception(f"Unhandled error processing job {job.id}:")
                job.status = "FAILED"
                job.error = str(e)
                job.completed_at = time.time()
                job.add_log(f"Internal error: {e}", phase="FAILED")
            finally:
                for q in list(job.listeners):
                    try:
                        q.put_nowait({
                            "type": "finished",
                            "job_id": job.id,
                            "status": job.status,
                            "progress": job.progress,
                        })
                    except Exception:
                        pass

                self.current_job = None
                self.queue.task_done()

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        return [j.to_dict() for j in reversed(list(self.jobs.values()))]

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False

        if job.status == "QUEUED":
            job.status = "CANCELED"
            job.add_log("Job canceled before execution.", phase="CANCELED")
            return True

        if job.status == "RUNNING" and self.current_job and self.current_job.id == job_id:
            self.runner.cancel()
            job.status = "CANCELED"
            job.add_log("Job canceled by user.", phase="CANCELED")
            return True

        return False

queue_manager = QueueManager()
