"""Manifest parser, validator, and template generator."""

from __future__ import annotations

import re
from pathlib import Path
import json
import yaml

from ..models import AgentManifest

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
_ENTRYPOINT_PATTERN = re.compile(r"^[\w.]+:\w+$")


def parse_manifest(path: str | Path) -> AgentManifest:
    """Parse an agent.yaml file into an AgentManifest using Pydantic."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid manifest format in {path}")

    reqs = raw.get("requirements", {})
    profile = raw.get("profile", {})
    inp = raw.get("input", {})
    out = raw.get("output", {})
    compose = raw.get("compose", {})

    # Flatten nested structures to match flat Pydantic model
    parsed_data = {
        "name": raw.get("name", ""),
        "version": raw.get("version", "0.1.0"),
        "description": raw.get("description", ""),
        "author": raw.get("author", ""),
        "license": raw.get("license", "MIT"),
        "entrypoint": raw.get("entrypoint", ""),
        "capabilities": raw.get("capabilities", []),
        "tags": raw.get("tags", []),
        "models": reqs.get("models", []),
        "tools": reqs.get("tools", []),
        "api_keys": reqs.get("api_keys", []),
        "python_packages": reqs.get("python_packages", []),
        "avg_cost_per_run": profile.get("avg_cost_per_run", 0),
        "avg_latency_seconds": profile.get("avg_latency_seconds", 0),
        "avg_tokens_per_run": profile.get("avg_tokens_per_run", 0),
        "quality_score": profile.get("quality_score", 0),
        "frameworks": raw.get("frameworks", []),
        "input_type": inp.get("type", "string"),
        "input_description": inp.get("description", ""),
        "input_examples": inp.get("examples", []),
        "output_type": out.get("type", "string"),
        "output_format": out.get("format", ""),
        "output_description": out.get("description", ""),
        "compose_role": compose.get("role", ""),
        "compose_connects_to": compose.get("connects_to", []),
        "signature": raw.get("signature", ""),
        "public_key": raw.get("public_key", ""),
        "source_path": str(path.parent),
    }
    
    # Let Pydantic validate and coerce types
    return AgentManifest.model_validate(parsed_data)


def validate_manifest(manifest: AgentManifest) -> list[str]:
    """Validate a manifest, returning a list of errors (empty = valid)."""
    errors = []

    if not manifest.name:
        errors.append("'name' is required")
    elif not _NAME_PATTERN.match(manifest.name):
        errors.append(
            f"'name' must be lowercase alphanumeric with hyphens, "
            f"got '{manifest.name}'"
        )

    if not manifest.version:
        errors.append("'version' is required")
    elif not _VERSION_PATTERN.match(manifest.version):
        errors.append(f"'version' must be semver (x.y.z), got '{manifest.version}'")

    if not manifest.description:
        errors.append("'description' is required")

    if not manifest.author:
        errors.append("'author' is required")

    if not manifest.entrypoint:
        errors.append("'entrypoint' is required (format: 'module:ClassName')")
    elif not _ENTRYPOINT_PATTERN.match(manifest.entrypoint):
        errors.append(
            f"'entrypoint' must be 'module:ClassName', got '{manifest.entrypoint}'"
        )

    if not manifest.capabilities:
        errors.append("'capabilities' must list at least one capability")

    return errors


def generate_template(output_path: str = "agent.yaml") -> Path:
    """Generate a template agent.yaml manifest."""
    template = {
        "name": "my-agent",
        "version": "0.1.0",
        "description": "A brief description of what your agent does",
        "author": "your-github-username",
        "license": "MIT",
        "entrypoint": "my_agent:MyAgent",
        "capabilities": ["research", "analysis"],
        "tags": ["research", "web-search"],
        "requirements": {
            "models": ["gpt-4o-mini"],
            "tools": ["web_search"],
            "api_keys": ["OPENAI_API_KEY"],
            "python_packages": ["openai>=1.0"],
        },
        "profile": {
            "avg_cost_per_run": 0.04,
            "avg_latency_seconds": 10,
            "avg_tokens_per_run": 5000,
            "quality_score": 8.0,
        },
        "frameworks": ["direct", "langgraph"],
        "input": {
            "type": "string",
            "description": "Research topic or question",
            "examples": [
                "Compare LangGraph vs CrewAI",
                "Analyze MCP protocol adoption",
            ],
        },
        "output": {
            "type": "string",
            "format": "markdown",
            "description": "Structured research report",
        },
        "compose": {
            "role": "researcher",
            "connects_to": ["analyst", "writer"],
        },
    }

    path = Path(output_path)
    path.write_text(yaml.dump(template, default_flow_style=False, sort_keys=False))
    return path


def verify_manifest_signature(manifest: AgentManifest) -> bool:
    """Verify the cryptographic signature of the manifest.
    
    Returns True if the signature is valid or if security is not enforced.
    """
    if not manifest.signature or not manifest.public_key:
        return False

    from cryptography.hazmat.primitives.asymmetric import ed25519
    
    try:
        pk = ed25519.Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(manifest.public_key)
        )
        # We sign the JSON representation of the manifest minified, excluding signature itself
        data = manifest.to_dict()
        data.pop("signature", None)
        message = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        
        pk.verify(bytes.fromhex(manifest.signature), message)
        return True
    except Exception:
        return False
