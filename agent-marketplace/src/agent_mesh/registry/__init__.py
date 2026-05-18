"""Local registry — manage installed agents in ~/.agents/."""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import subprocess
import re
import sys
from pathlib import Path
from typing import Optional

from ..manifest import parse_manifest, validate_manifest
from ..models import AgentBase, AgentManifest, SearchResult
from .remote import RemoteRegistry
from .artifacts import ArtifactDownloader

logger = logging.getLogger("agent-mesh")

DEFAULT_REGISTRY_DIR = Path.home() / ".agents"


class LocalRegistry:
    """Manages the local agent registry at ~/.agents/."""

    def __init__(self, registry_dir: Optional[Path] = None):
        self.dir = registry_dir or DEFAULT_REGISTRY_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.dir / "registry.json"
        self.downloader = ArtifactDownloader()

    def _load_index(self) -> dict:
        if self._index_path.exists():
            return json.loads(self._index_path.read_text())
        return {"agents": {}}

    def _save_index(self, index: dict) -> None:
        self._index_path.write_text(json.dumps(index, indent=2))

    async def install(self, manifest_path: str, source_dir: Optional[str] = None) -> AgentManifest:
        """Install an agent (from local file or remote source)."""
        # ── 1. Resolve Remote Artifacts ──
        if "github.com" in manifest_path or manifest_path.startswith("http"):
            logger.info(f"Resolving remote artifact from: {manifest_path}")
            artifact_dir = await self.downloader.fetch_artifact(manifest_path)
            manifest_path = str(artifact_dir / "agent.yaml")
            source_dir = str(artifact_dir)

        # ── 2. Parse & Validate ──
        manifest = parse_manifest(manifest_path)
        errors = validate_manifest(manifest)
        if errors:
            raise ValueError(f"Invalid manifest: {'; '.join(errors)}")

        # ── 3. Check Signature ──
        from ..manifest import verify_manifest_signature
        verified = False
        if manifest.signature:
            if not verify_manifest_signature(manifest):
                logger.error(f"❌ SIGNATURE VERIFICATION FAILED for {manifest.name}")
                raise ValueError("Cryptographic verification failed. Agent may have been tampered with.")
            else:
                logger.info(f"✅ Verified signed agent: {manifest.name}")
                verified = True
        else:
            logger.warning(f"⚠️ Installing UNVERIFIED agent: {manifest.name}")

        # ── 3. Hardening: Path Traversal Protection ──
        safe_name = re.sub(r"[^a-z0-9-]", "", manifest.name.lower())
        if not safe_name:
             raise ValueError(f"Agent name '{manifest.name}' is too dangerous to install.")
        
        agent_dir = self.dir / safe_name
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Copy manifest
        shutil.copy2(manifest_path, agent_dir / "agent.yaml")

        # Copy source files from the manifest's directory
        src = Path(source_dir or manifest.source_path or Path(manifest_path).parent)
        for f in src.iterdir():
            if f.is_file() and f.suffix in {".py", ".yaml", ".yml", ".json", ".txt", ".md"}:
                shutil.copy2(f, agent_dir / f.name)

        # Update index
        index = self._load_index()
        index["agents"][manifest.name] = {
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "entrypoint": manifest.entrypoint,
            "installed_at": str(agent_dir),
            "verified": verified,
            "has_venv": False,
        }
        
        # ── 4. Dynamic Dependency Isolation (VENV) ──
        if manifest.python_packages:
            # Audit packages for malicious flags
            for pkg in manifest.python_packages:
                if not re.match(r"^[a-zA-Z0-9-_]+(==[0-9.]+)?$", pkg):
                    raise ValueError(f"Malicious or invalid dependency detected: {pkg}")
            
            logger.info(f"Creating isolated environment for {manifest.name}...")
            venv_dir = agent_dir / ".venv"
            try:
                # Create venv
                subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
                
                # Install packages
                pip_exe = str(venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / "pip")
                logger.info(f"Installing dependencies into isolated venv: {', '.join(manifest.python_packages)}")
                subprocess.run([pip_exe, "install"] + manifest.python_packages, check=True)
                
                index["agents"][manifest.name]["has_venv"] = True
            except Exception as e:
                logger.error(f"Isolated setup failed for {manifest.name}: {e}")
                # We don't fail the whole install, just mark as no-venv
        
        self._save_index(index)
        logger.info(f"Installed {manifest.name} v{manifest.version} → {agent_dir}")
        return manifest

    def uninstall(self, name: str) -> bool:
        """Remove an installed agent."""
        agent_dir = self.dir / name
        if not str(agent_dir.resolve()).startswith(str(self.dir.resolve())):
            raise ValueError("Security violation: Path traversal attempt detected.")
        if agent_dir.exists():
            shutil.rmtree(agent_dir)
        index = self._load_index()
        removed = index["agents"].pop(name, None) is not None
        self._save_index(index)
        if removed:
            logger.info(f"Uninstalled {name}")
        return removed

    def list_installed(self) -> list[AgentManifest]:
        """List all installed agents."""
        manifests = []
        for agent_dir in sorted(self.dir.iterdir()):
            manifest_path = agent_dir / "agent.yaml"
            if manifest_path.exists():
                try:
                    manifests.append(parse_manifest(manifest_path))
                except Exception as e:
                    logger.warning(f"Error reading {agent_dir.name}: {e}")
        return manifests

    def get_manifest(self, name: str) -> Optional[AgentManifest]:
        """Get the manifest for an installed agent."""
        manifest_path = self.dir / name / "agent.yaml"
        if manifest_path.exists():
            return parse_manifest(manifest_path)
        return None

    def is_installed(self, name: str) -> bool:
        return (self.dir / name / "agent.yaml").exists()

    def search(
        self,
        query: str = "",
        tag: str = "",
        framework: str = "",
        max_cost: float = 0,
    ) -> list[SearchResult]:
        """Search installed agents."""
        results = []
        for manifest in self.list_installed():
            if query and not manifest.matches_query(query):
                continue
            if tag and not manifest.matches_tag(tag):
                continue
            if framework and not manifest.matches_framework(framework):
                continue
            if max_cost > 0 and not manifest.matches_max_cost(max_cost):
                continue
            results.append(SearchResult(
                manifest=manifest,
                installed=True,
            ))
        return results

    def load_agent(self, name: str, allow_sandbox: bool = True) -> AgentBase:
        """Load and instantiate an installed agent.
        
        Automatically uses a Sandbox if the agent is unverified and allow_sandbox is True.
        """
        index = self._load_index()
        agent_info = index.get("agents", {}).get(name)
        manifest = self.get_manifest(name)
        
        if not manifest or not agent_info:
            raise ValueError(f"Agent '{name}' is not installed")

        # ── 1. Security Guard: Check if we need Sandboxing ──
        if not agent_info.get("verified", False) and allow_sandbox:
            from ..sandbox import SubprocessSandboxWrapper
            logger.info(f"🛡️ Security Policy: Wrapping UNVERIFIED agent '{name}' in a Sandbox.")
            
            # Determine python path for venv if it exists
            python_exe = sys.executable
            if agent_info.get("has_venv"):
                agent_dir = Path(agent_info["installed_at"])
                python_exe = str(agent_dir / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python")

            # Since AgentBase is abstract, we create a proxy that satisfies the interface
            class SandboxedAgentProxy(AgentBase):
                def __init__(self, manifest_name: str, registry_dir: Path, python_exe: str):
                    super().__init__()
                    self.sandbox = SubprocessSandboxWrapper(manifest_name, registry_dir, python_exe=python_exe)
                
                async def run(self, input_text: str) -> str:
                    return await self.sandbox.execute(input_text)
            
            return SandboxedAgentProxy(name, self.dir, python_exe)

        # ── 2. Native Loading (Only for Verified agents or explicitly allowed) ──
        entrypoint = manifest.entrypoint
        if ":" not in entrypoint:
            raise ValueError(
                f"Invalid entrypoint '{entrypoint}', expected 'module:ClassName'"
            )

        module_name, class_name = entrypoint.rsplit(":", 1)
        agent_dir = str(self.dir / name)

        # Add agent directory to Python path temporarily
        if agent_dir not in sys.path:
            sys.path.insert(0, agent_dir)

        try:
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            agent = cls()
            agent.setup()
            return agent
        except (ModuleNotFoundError, AttributeError) as e:
            raise RuntimeError(
                f"Cannot load agent '{name}' from entrypoint '{entrypoint}': {e}"
            )


def load_agent(name: str, registry_dir: Optional[Path] = None) -> AgentBase:
    """Convenience function to load an installed agent."""
    registry = LocalRegistry(registry_dir)
    return registry.load_agent(name)


def load_agent_from_manifest(manifest_path: str) -> AgentBase:
    """Load an agent directly from a manifest file (without installing)."""
    manifest = parse_manifest(manifest_path)
    if ":" not in manifest.entrypoint:
        raise ValueError(f"Invalid entrypoint: {manifest.entrypoint}")

    module_name, class_name = manifest.entrypoint.rsplit(":", 1)
    src_dir = str(Path(manifest_path).parent)

    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    agent = cls()
    agent.setup()
    return agent

__all__ = [
    "LocalRegistry",
    "RemoteRegistry",
    "load_agent",
    "load_agent_from_manifest",
]
