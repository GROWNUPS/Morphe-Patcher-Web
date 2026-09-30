import asyncio
import os
import re
import shlex
import logging
from pathlib import Path
from typing import AsyncGenerator, Callable, Optional, Dict, Any, List

from app.config import (
    MORPHE_JAR,
    PATCHES_FILE,
    JAVA_CMD,
    JAVA_OPTS,
    CACHE_DIR,
)
from app.core.keystore import get_keystore_cli_args

logger = logging.getLogger("morphe.runner")

PHASE_PATTERNS = [
    (re.compile(r"(reading|loading)\s+(apk|dex)", re.IGNORECASE), "READING_APK", 15),
    (re.compile(r"decompil", re.IGNORECASE), "DECOMPILING", 30),
    (re.compile(r"executing\s+patch|applying\s+patch", re.IGNORECASE), "PATCHING", 55),
    (re.compile(r"compil|rebuild", re.IGNORECASE), "COMPILING", 75),
    (re.compile(r"signing\s+apk|aligning", re.IGNORECASE), "SIGNING", 90),
    (re.compile(r"finished|success|completed", re.IGNORECASE), "FINISHED", 100),
]

class MorpheRunner:
    def __init__(self):
        self.current_process: Optional[asyncio.subprocess.Process] = None
        self._canceled = False

    def build_command(
        self,
        input_apk: Path,
        output_apk: Path,
        options_file: Optional[Path] = None,
        include_patches: Optional[List[str]] = None,
        exclude_patches: Optional[List[str]] = None,
        custom_patches_mpp: Optional[Path] = None,
        strip_libs: Optional[str] = None,
        patch_options: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[str]:
        cmd = [JAVA_CMD]

        if JAVA_OPTS:
            cmd.extend(shlex.split(JAVA_OPTS))

        cmd.extend(["-jar", str(MORPHE_JAR)])
        cmd.append("patch")

        if custom_patches_mpp:
            cmd.extend(["--patches", str(custom_patches_mpp)])
        elif Path(PATCHES_FILE).exists():
            cmd.extend(["--patches", str(PATCHES_FILE)])

        cmd.extend(["--out", str(output_apk)])

        keystore_args = get_keystore_cli_args()
        cmd.extend(keystore_args)

        cmd.append("--force")
        cmd.append("--continue-on-error")

        if strip_libs:
            cmd.append(f"--striplibs={strip_libs}")

        if options_file and options_file.exists():
            cmd.extend(["--options-file", str(options_file)])

        if patch_options:
            for patch_name, opts in patch_options.items():
                for opt_key, opt_val in opts.items():
                    cmd.append(f"-O={opt_key}={opt_val}")
                cmd.extend(["--enable", patch_name])

        if include_patches:
            for p in include_patches:
                cmd.extend(["--enable", p])
        if exclude_patches:
            for p in exclude_patches:
                cmd.extend(["--disable", p])

        temp_dir = CACHE_DIR / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["-t", str(temp_dir)])

        cmd.append(str(input_apk))
        return cmd

    async def run_patch(
        self,
        input_apk: Path,
        output_apk: Path,
        options_file: Optional[Path] = None,
        include_patches: Optional[List[str]] = None,
        exclude_patches: Optional[List[str]] = None,
        custom_patches_mpp: Optional[Path] = None,
        strip_libs: Optional[str] = None,
        patch_options: Optional[Dict[str, Dict[str, Any]]] = None,
        log_callback: Optional[Callable[[str, Optional[int], Optional[str]], None]] = None,
    ) -> Dict[str, Any]:
        self._canceled = False

        if not Path(MORPHE_JAR).exists():
            msg = f"Morphe JAR file not found at {MORPHE_JAR}. Please place morphe-desktop.jar in /config or /app."
            logger.error(msg)
            if log_callback:
                log_callback(f"[ERROR] {msg}", 0, "ERROR")
            return {"success": False, "returncode": -1, "error": msg}

        cmd = self.build_command(
            input_apk=input_apk,
            output_apk=output_apk,
            options_file=options_file,
            include_patches=include_patches,
            exclude_patches=exclude_patches,
            custom_patches_mpp=custom_patches_mpp,
            strip_libs=strip_libs,
            patch_options=patch_options,
        )

        cmd_display = " ".join([c if " " not in c else f'"{c}"' for c in cmd])
        logger.info(f"Executing: {cmd_display}")
        if log_callback:
            log_callback(f"[INFO] Command: {cmd_display}", 5, "INITIALIZING")

        try:
            morphe_data_dir = CACHE_DIR / "morphe"
            morphe_tmp_dir = CACHE_DIR / "tmp"
            morphe_data_dir.mkdir(parents=True, exist_ok=True)
            morphe_tmp_dir.mkdir(parents=True, exist_ok=True)

            sub_env = os.environ.copy()
            sub_env["MORPHE_DATA_DIR"] = str(morphe_data_dir)

            self.current_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(CACHE_DIR),
                env=sub_env,
            )

            current_phase = "STARTING"
            current_progress = 10

            while True:
                line_bytes = await self.current_process.stdout.readline()
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")

                for pattern, phase, progress in PHASE_PATTERNS:
                    if pattern.search(line):
                        current_phase = phase
                        current_progress = max(current_progress, progress)
                        break

                if log_callback:
                    log_callback(line, current_progress, current_phase)

            await self.current_process.wait()
            returncode = self.current_process.returncode

            if self._canceled:
                return {"success": False, "returncode": -99, "error": "Job was canceled by user"}

            success = (returncode == 0) and output_apk.exists() and output_apk.stat().st_size > 0
            if success:
                if log_callback:
                    log_callback("[SUCCESS] Patching completed successfully!", 100, "COMPLETED")
            else:
                if log_callback:
                    log_callback(f"[ERROR] Morphe exited with code {returncode}", current_progress, "FAILED")

            return {
                "success": success,
                "returncode": returncode,
                "output_apk": str(output_apk) if success else None,
                "output_size": output_apk.stat().st_size if success else 0,
            }

        except Exception as e:
            logger.exception("Error executing Morphe CLI:")
            if log_callback:
                log_callback(f"[EXCEPTION] {e}", 0, "FAILED")
            return {"success": False, "returncode": -1, "error": str(e)}
        finally:
            self.current_process = None

    def cancel(self):
        self._canceled = True
        if self.current_process:
            try:
                self.current_process.terminate()
            except ProcessLookupError:
                pass

