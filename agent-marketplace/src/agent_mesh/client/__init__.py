"""Client utilities — compose pipelines from installed agents."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..registry import LocalRegistry


def compose_pipeline(
    agent_names: list[str],
    output_path: str = "agent-compose.yaml",
    registry_dir=None,
) -> Path:
    """Generate an agent-compose.yaml from installed agents.

    Uses each agent's compose.role and compose.connects_to fields
    to wire the pipeline automatically.
    """
    registry = LocalRegistry(registry_dir)
    agents_yaml = {}

    for i, name in enumerate(agent_names):
        manifest = registry.get_manifest(name)
        if not manifest:
            raise ValueError(f"Agent '{name}' is not installed")

        role = manifest.compose_role or name
        spec: dict = {
            "agent_name": name,
            "model": manifest.models[0] if manifest.models else "gpt-4o-mini",
        }

        if manifest.description:
            spec["system_prompt"] = manifest.description

        if manifest.tools:
            spec["tools"] = manifest.tools

        # Auto-wire: connect to the next agent in the list
        if i < len(agent_names) - 1:
            next_manifest = registry.get_manifest(agent_names[i + 1])
            next_role = (next_manifest.compose_role if next_manifest else agent_names[i + 1])
            spec["connects_to"] = [next_role]

        agents_yaml[role] = spec

    pipeline = {
        "name": f"composed-{'-'.join(agent_names[:3])}",
        "description": f"Auto-generated pipeline from: {', '.join(agent_names)}",
        "agents": agents_yaml,
    }

    path = Path(output_path)
    path.write_text(yaml.dump(pipeline, default_flow_style=False, sort_keys=False))
    return path
