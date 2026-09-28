import json
import asyncio
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.queue_manager import queue_manager, Job
from app.config import PROFILES_DIR, PATCHES_DIR

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])

class CreateJobRequest(BaseModel):
    file_path: str
    output_filename: Optional[str] = None
    package_name: Optional[str] = None
    version_name: Optional[str] = None
    include_patches: Optional[List[str]] = None
    exclude_patches: Optional[List[str]] = None
    profile_name: Optional[str] = None
    strip_libs: Optional[str] = None
    branding: Optional[str] = None
    custom_app_name: Optional[str] = None
    patch_source: Optional[str] = None
    custom_patches_url: Optional[str] = None

class BatchJobRequest(BaseModel):
    jobs: List[CreateJobRequest]

def _prepare_job(req: CreateJobRequest) -> Job:
    input_path = Path(req.file_path)
    if not input_path.exists():
        raise HTTPException(status_code=404, detail=f"Input file does not exist: {req.file_path}")

    options_file = None
    if req.profile_name:
        prof = PROFILES_DIR / f"{req.profile_name}.json"
        if prof.exists():
            options_file = prof

    excludes = list(req.exclude_patches or [])
    includes = list(req.include_patches or [])
    patch_options = None

    if req.branding == "original":
        # Disabling Custom branding and Change header keeps original name & icon
        if "Custom branding" not in excludes:
            excludes.append("Custom branding")
        if "Change header" not in excludes:
            excludes.append("Change header")
    elif req.branding == "custom" and req.custom_app_name and req.custom_app_name.strip():
        patch_options = {
            "Custom branding": {
                "customName": req.custom_app_name.strip()
            }
        }

    # Resolve patch source (.mpp or URL)
    custom_patches_mpp = None
    if req.patch_source and req.patch_source != "default":
        if req.patch_source == "custom_url" and req.custom_patches_url:
            custom_patches_mpp = req.custom_patches_url.strip()
        elif req.patch_source.startswith("http://") or req.patch_source.startswith("https://"):
            custom_patches_mpp = req.patch_source.strip()
        else:
            candidate = PATCHES_DIR / req.patch_source
            if candidate.exists():
                custom_patches_mpp = str(candidate)
            elif (PATCHES_DIR / f"{req.patch_source}.mpp").exists():
                custom_patches_mpp = str(PATCHES_DIR / f"{req.patch_source}.mpp")

    return Job(
        input_path=input_path,
        output_filename=req.output_filename,
        source="WEB_UPLOAD",
        package_name=req.package_name,
        version_name=req.version_name,
        options_file=options_file,
        include_patches=includes if includes else None,
        exclude_patches=excludes if excludes else None,
        strip_libs=req.strip_libs,
        patch_options=patch_options,
        custom_patches_mpp=custom_patches_mpp,
    )

@router.post("")
async def create_patch_job(req: CreateJobRequest):
    job = _prepare_job(req)
    await queue_manager.submit_job(job)
    return job.to_dict()

@router.post("/batch")
async def create_patch_jobs_batch(batch_req: BatchJobRequest):
    if not batch_req.jobs:
        raise HTTPException(status_code=400, detail="No jobs provided in batch request.")

    created_jobs = []
    for req in batch_req.jobs:
        job = _prepare_job(req)
        await queue_manager.submit_job(job)
        created_jobs.append(job.to_dict())

    return created_jobs

@router.get("")
async def list_jobs():
    return queue_manager.get_all_jobs()

@router.get("/{job_id}")
async def get_job(job_id: str):
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    data = job.to_dict()
    data["logs"] = job.logs
    return data

@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    success = queue_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Unable to cancel job")
    return {"success": True, "message": "Job cancellation initiated"}

@router.get("/{job_id}/stream")
async def stream_job_logs(job_id: str):
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        for log_line in job.logs:
            payload = {
                "type": "log",
                "job_id": job.id,
                "line": log_line,
                "progress": job.progress,
                "phase": job.current_phase,
                "status": job.status,
            }
            yield f"data: {json.dumps(payload)}\n\n"

        if job.status in ("COMPLETED", "FAILED", "CANCELED"):
            payload = {
                "type": "finished",
                "job_id": job.id,
                "status": job.status,
                "progress": job.progress,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            return

        q: asyncio.Queue = asyncio.Queue()
        job.listeners.append(q)

        try:
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "finished":
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if q in job.listeners:
                job.listeners.remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
