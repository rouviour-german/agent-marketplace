"""AgentMesh Orchestrator — execute complex agent pipelines from agent-compose.yaml."""

from __future__ import annotations

import logging
import yaml
from pathlib import Path
from typing import Any, Dict, Optional

from .registry import LocalRegistry
from .models import AgentBase

logger = logging.getLogger("agent-mesh.orchestrator")

class Orchestrator:
    """The execution engine for AgentMesh compositions."""

    def __init__(self, compose_file: str | Path, registry_dir: Optional[Path] = None):
        self.compose_path = Path(compose_file)
        if not self.compose_path.exists():
            raise FileNotFoundError(f"Composition file not found: {self.compose_path}")
        
        self.data = yaml.safe_load(self.compose_path.read_text())
        self.registry = LocalRegistry(registry_dir)
        self.agents: Dict[str, AgentBase] = {}
        self._initialize_agents()

    def _initialize_agents(self):
        """Map roles to actual instantiated agents."""
        agent_specs = self.data.get("agents", {})
        for role, spec in agent_specs.items():
            # In a real scenario, the 'role' maps either to an installed agent name
            # or the spec might contain an 'agent_name' field.
            # For now, we assume role == installed_agent_name if not specified.
            agent_name = spec.get("agent_name", role)
            try:
                agent = self.registry.load_agent(agent_name)
                self.agents[role] = agent
                logger.info(f"Loaded agent for role '{role}': {agent_name}")
            except Exception as e:
                logger.error(f"Failed to load agent for role '{role}': {e}")
                raise

    async def run_pipeline(self, initial_input: str) -> Dict[str, Any]:
        """Execute the pipeline starting from the first agent."""
        agent_specs = self.data.get("agents", {})
        if not agent_specs:
            return {"error": "No agents defined in composition"}

        results = {}
        visited = set()
        hops = 0

        # Find the starting agent (the one nothing connects to, or the first one)
        # For MVP: just take the first one in the dict
        roles = list(agent_specs.keys())
        current_role = roles[0]
        current_input = initial_input

        while current_role:
            # ── FAANG Audit Fix: Cycle Detection ──
            if current_role in visited:
                raise RuntimeError(f"Infinite loop detected in mesh pipeline at role: {current_role}")
            visited.add(current_role)
            
            hops += 1
            if hops > 50: # Guard for complex pipelines
                raise RuntimeError("Maximum mesh traversal depth (50) exceeded. Graph might be circular.")

            logger.info(f"Executing role: {current_role}")
            agent = self.agents.get(current_role)
            if not agent:
                raise RuntimeError(f"Agent for role '{current_role}' not found")

            # Execute with resilience
            output = await agent.execute(current_input)
            results[current_role] = output

            # Determine next agent
            spec = agent_specs[current_role]
            next_roles = spec.get("connects_to", [])
            
            if not next_roles:
                break
            
            # For MVP: sequential chaining
            current_role = next_roles[0]
            current_input = output

        return results

    async def execute(self, input_text: str) -> str:
        """Execute the full pipeline and return the final output."""
        results = await self.run_pipeline(input_text)
        # Return the last result
        if not results:
            return ""
        return list(results.values())[-1]
