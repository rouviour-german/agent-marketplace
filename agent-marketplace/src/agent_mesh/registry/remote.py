"""Remote registry client for fetching and searching agents globally."""

from __future__ import annotations

import logging
from typing import Optional, List
import httpx

from ..models import AgentManifest, SearchResult

logger = logging.getLogger("agent-mesh.remote")

DEFAULT_REMOTE_URL = "https://raw.githubusercontent.com/agent-mesh/index/main/v1/index.json"

class RemoteRegistry:
    """Interfaces with the highly available global tracking database for agents."""

    def __init__(self, remote_url: str = DEFAULT_REMOTE_URL):
        self.remote_url = remote_url
        self._cache = None

    def _fetch_index(self) -> dict:
        """Fetch the JSON index from the remote cloud repository."""
        if self._cache:
            return self._cache
        try:
            # We enforce a timeout because this is a remote call block
            response = httpx.get(self.remote_url, timeout=5.0)
            if response.status_code == 200:
                self._cache = response.json()
                return self._cache
            else:
                logger.warning(f"Failed to fetch remote registry. Code: {response.status_code}")
                return {"agents": {}}
        except httpx.RequestError as exc:
            logger.warning(f"Connection to global mesh timeout/failed: {exc}")
            return {"agents": {}}

    def list_all(self) -> List[AgentManifest]:
        """List all agents available publicly."""
        index = self._fetch_index()
        agents = []
        for name, data in index.get("agents", {}).items():
            # Construct a remote manifest outline
            manifest = AgentManifest.model_validate(data)
            agents.append(manifest)
        return agents

    def search(
        self,
        query: str = "",
        tag: str = "",
        framework: str = "",
        max_cost: float = 0,
    ) -> List[SearchResult]:
        """Search via the global remote index."""
        results = []
        for manifest in self.list_all():
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
                installed=False, # Remotely fetched manifests are NOT locally installed
            ))
        return results

    def fetch_manifest(self, name: str) -> Optional[AgentManifest]:
        """Fetch a specific agent manifest data off the remote connection."""
        index = self._fetch_index()
        agent_data = index.get("agents", {}).get(name)
        if not agent_data:
            return None
        return AgentManifest.model_validate(agent_data)

    def publish(self, manifest: AgentManifest) -> bool:
        """Publish a manifest to the remote registry.
        
        In a production environment, this would be a POST request to a 
        protected API endpoint with authentication.
        """
        logger.info(f"Publishing manifest {manifest.name} to {self.remote_url}")
        # Simulation of successful publication
        # In a real scenario: httpx.post(f"{self.remote_url}/publish", json=manifest.to_dict())
        return True
