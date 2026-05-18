"""Artifact Downloader for fetching agent code from remote repositories."""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("agent-mesh.artifacts")

class ArtifactDownloader:
    """Handles fetching and unpacking agent source code from remote URIs."""

    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir = download_dir or Path(tempfile.gettempdir()) / "agent-mesh-downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def download_from_github(self, repo_url: str, version: str = "main") -> Path:
        """Download a repository from GitHub as a ZIP archive.
        
        Example: https://github.com/user/repo
        """
        # Convert GitHub URL to ZIP download URL
        # Format: https://github.com/user/repo/archive/refs/heads/main.zip
        if not repo_url.endswith(".zip"):
            clean_url = repo_url.rstrip("/")
            download_url = f"{clean_url}/archive/refs/heads/{version}.zip"
        else:
            download_url = repo_url

        target_path = self.download_dir / f"download-{hash(download_url)}.zip"
        
        logger.info(f"Downloading artifact from: {download_url}")
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(download_url, timeout=30.0)
            response.raise_for_status()
            target_path.write_bytes(response.content)

        # Unpack
        extract_dir = self.download_dir / f"extract-{hash(download_url)}"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)

        with zipfile.ZipFile(target_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # GitHub ZIPs usually have a top-level folder like 'repo-main/'
        # We need to find the directory containing 'agent.yaml'
        for p in extract_dir.rglob("agent.yaml"):
            return p.parent

        raise FileNotFoundError(f"No agent.yaml found in the downloaded artifact from {repo_url}")

    async def fetch_artifact(self, source_path: str) -> Path:
        """Generic fetcher — detects type and downloads."""
        if "github.com" in source_path:
            return await self.download_from_github(source_path)
        
        # Local path support (for testing/monorepos)
        local_path = Path(source_path)
        if local_path.exists():
            return local_path
            
        raise ValueError(f"Unsupported or missing artifact source: {source_path}")
