import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.profiles import (
    list_profiles,
    get_profile,
    save_profile,
    delete_profile,
    set_default_profile,
    POPULAR_PACKAGES,
)

logger = logging.getLogger("patchium.api.profiles")

router = APIRouter(prefix="/api/profiles", tags=["Profiles"])

class ProfileModel(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, description="Human readable profile name")
    package_name: str = Field(..., description="Target Android package name, or * for universal")
    description: Optional[str] = ""
    branding: str = Field(default="custom", description="'original', 'morphe', or 'custom'")
    custom_app_name: Optional[str] = Field(default="{appName} Morphe", description="Template with {appName}")
    output_format: Optional[str] = Field(default="{appName}_{version}_{arch}_patched.apk")
    optimize_arch: bool = Field(default=True, description="Optimize for 64-bit phones")
    target_arch: str = Field(default="arm64-v8a", description="'arm64-v8a', 'armeabi-v7a', or 'universal'")
    is_default: bool = Field(default=False, description="Whether this is the default preset for the package")
    include_patches: Optional[List[str]] = Field(default_factory=list)
    exclude_patches: Optional[List[str]] = Field(default_factory=list)
    patch_options: Optional[Dict[str, Any]] = Field(default_factory=dict)

@router.get("")
async def get_all_profiles(package: Optional[str] = Query(None, description="Optional package name to filter profiles")):
    """List profiles, optionally filtered by package name."""
    try:
        return list_profiles(package_name=package)
    except Exception as e:
        logger.error(f"Error listing profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/popular-apps")
async def get_popular_apps():
    """Returns curated list of popular patchable apps for profile presets."""
    return POPULAR_PACKAGES

@router.get("/{profile_id}")
async def get_single_profile(profile_id: str):
    """Retrieve full details of a specific profile."""
    prof = get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Profile not found")
    return prof

@router.post("")
async def create_or_update_profile(payload: ProfileModel):
    """Create or update a preset profile."""
    try:
        data = payload.model_dump()
        saved = save_profile(data)
        return {"success": True, "profile": saved}
    except Exception as e:
        logger.error(f"Failed to save profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{profile_id}/set-default")
async def make_default_profile(profile_id: str):
    """Set a profile as the default for its target package."""
    success = set_default_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True, "message": f"Profile '{profile_id}' set as default"}

@router.delete("/{profile_id}")
async def remove_profile(profile_id: str):
    """Delete a profile."""
    success = delete_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found or could not be deleted")
    return {"success": True, "message": "Profile deleted successfully"}
