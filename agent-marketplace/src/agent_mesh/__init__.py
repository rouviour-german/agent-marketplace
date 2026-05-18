"""agent-mesh: npm for AI agents."""

from .models import AgentBase, AgentManifest, SearchResult
from .manifest import generate_template, parse_manifest, validate_manifest
from .registry import LocalRegistry, load_agent, load_agent_from_manifest
from .client import compose_pipeline

__version__ = "0.1.0"
__all__ = [
    "AgentBase", "AgentManifest", "LocalRegistry", "SearchResult",
    "compose_pipeline", "generate_template", "load_agent",
    "load_agent_from_manifest", "parse_manifest", "validate_manifest",
]
