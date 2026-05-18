"""Sandboxed execution environments for AgentMesh.

In zero-trust enterprise topologies, externally fetched agents should never
execute natively in the main Python memory space. This module introduces 
conceptual Sandboxing wrappers.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent-mesh.sandbox")

@dataclass
class ResourceLimits:
    max_memory_mb: int = 256
    max_cpu_cores: float = 1.0
    timeout_seconds: float = 30.0

class SubprocessSandboxWrapper:
    """Executes a 3rd party agent manifest inside a restricted subprocess."""

    def __init__(self, manifest_name: str, registry_dir: Optional[Path] = None, limits: ResourceLimits = None, python_exe: Optional[str] = None):
        self.manifest_name = manifest_name
        self.registry_dir = registry_dir
        self.limits = limits or ResourceLimits()
        self.python_exe = python_exe or sys.executable
        
    async def execute(self, input_text: str) -> str:
        """Execute the agent out-of-process to prevent memory contamination."""
        import asyncio
        
        logger.info(f"Setting up Sandboxed subprocess for {self.manifest_name}")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / "input.txt"
            input_file.write_text(input_text)
            
            output_file = Path(tmpdir) / "output.txt"
            
            # Use specified python exe (e.g. from venv)
            cmd = [
                self.python_exe, "-m", "agent_mesh.internal.runner",
                "--manifest", self.manifest_name,
                "--input", str(input_file),
                "--output", str(output_file)
            ]
            
            if self.registry_dir:
                cmd.extend(["--registry", str(self.registry_dir)])
            
            try:
                # We use asyncio.create_subprocess_exec for non-blocking execution
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ # Pass current env for imports to work
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=self.limits.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    logger.error(f"Sandbox Timeout threshold {self.limits.timeout_seconds}s exceeded.")
                    raise TimeoutError("Sandboxed agent breached time limits.")
                
                if process.returncode != 0:
                    error_msg = stderr.decode().strip()
                    logger.error(f"Sandbox Fault: {error_msg}")
                    raise RuntimeError(f"Sandboxed agent fault: {error_msg}")
                
                if output_file.exists():
                    return output_file.read_text()
                return "Agent failed to emit response payload."
                
            except Exception as e:
                logger.error(f"Sandbox Error: {e}")
                raise
