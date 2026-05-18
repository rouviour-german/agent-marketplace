"""Comprehensive tests for agent-mesh."""

import json
from pathlib import Path

import pytest
import yaml

from agent_mesh.models import AgentBase, AgentManifest, SearchResult
from agent_mesh.manifest import (
    generate_template, parse_manifest, validate_manifest,
)
from agent_mesh.registry import LocalRegistry


# ─────────────────────────────────────────────
# Mock Agent
# ─────────────────────────────────────────────

class MockAgent(AgentBase):
    async def run(self, input: str) -> str:
        return f"Mock result for: {input}"


# ─────────────────────────────────────────────
# Manifest Helpers
# ─────────────────────────────────────────────

def _write_manifest(tmp_path: Path, overrides: dict = None) -> Path:
    data = {
        "name": "test-agent",
        "version": "1.0.0",
        "description": "A test agent for unit tests",
        "author": "test-user",
        "license": "MIT",
        "entrypoint": "test_agent:TestAgent",
        "capabilities": ["testing"],
        "tags": ["test", "mock"],
        "requirements": {
            "models": ["gpt-4o-mini"],
            "tools": ["web_search"],
            "api_keys": ["OPENAI_API_KEY"],
            "python_packages": ["openai>=1.0"],
        },
        "profile": {
            "avg_cost_per_run": 0.03,
            "avg_latency_seconds": 5,
            "avg_tokens_per_run": 3000,
            "quality_score": 8.0,
        },
        "frameworks": ["direct", "langgraph"],
        "input": {
            "type": "string",
            "description": "Test input",
            "examples": ["Test query"],
        },
        "output": {
            "type": "string",
            "format": "text",
            "description": "Test output",
        },
        "compose": {
            "role": "tester",
            "connects_to": ["reviewer"],
        },
    }
    if overrides:
        data.update(overrides)
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.dump(data))
    return path


# ─────────────────────────────────────────────
# Manifest Parsing
# ─────────────────────────────────────────────

class TestManifestParsing:
    def test_parse_valid_manifest(self, tmp_path):
        path = _write_manifest(tmp_path)
        m = parse_manifest(path)
        assert m.name == "test-agent"
        assert m.version == "1.0.0"
        assert m.author == "test-user"
        assert m.entrypoint == "test_agent:TestAgent"
        assert "testing" in m.capabilities
        assert "gpt-4o-mini" in m.models
        assert m.avg_cost_per_run == 0.03

    def test_parse_compose_fields(self, tmp_path):
        path = _write_manifest(tmp_path)
        m = parse_manifest(path)
        assert m.compose_role == "tester"
        assert m.compose_connects_to == ["reviewer"]

    def test_parse_missing_file(self):
        with pytest.raises(FileNotFoundError):
            parse_manifest("/nonexistent/agent.yaml")

    def test_parse_minimal(self, tmp_path):
        path = tmp_path / "agent.yaml"
        path.write_text(yaml.dump({"name": "minimal", "entrypoint": "m:C"}))
        m = parse_manifest(path)
        assert m.name == "minimal"
        assert m.version == "0.1.0"  # Default


# ─────────────────────────────────────────────
# Manifest Validation
# ─────────────────────────────────────────────

class TestManifestValidation:
    def test_valid_manifest(self, tmp_path):
        path = _write_manifest(tmp_path)
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert errors == []

    def test_missing_name(self, tmp_path):
        path = _write_manifest(tmp_path, {"name": ""})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("name" in e for e in errors)

    def test_invalid_name_format(self, tmp_path):
        path = _write_manifest(tmp_path, {"name": "UPPERCASE_AGENT"})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("name" in e.lower() for e in errors)

    def test_invalid_version(self, tmp_path):
        path = _write_manifest(tmp_path, {"version": "v1"})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("version" in e for e in errors)

    def test_missing_description(self, tmp_path):
        path = _write_manifest(tmp_path, {"description": ""})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("description" in e for e in errors)

    def test_missing_entrypoint(self, tmp_path):
        path = _write_manifest(tmp_path, {"entrypoint": ""})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("entrypoint" in e for e in errors)

    def test_invalid_entrypoint_format(self, tmp_path):
        path = _write_manifest(tmp_path, {"entrypoint": "no-colon-here"})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("entrypoint" in e for e in errors)

    def test_missing_capabilities(self, tmp_path):
        path = _write_manifest(tmp_path, {"capabilities": []})
        m = parse_manifest(path)
        errors = validate_manifest(m)
        assert any("capabilities" in e for e in errors)


# ─────────────────────────────────────────────
# Template Generation
# ─────────────────────────────────────────────

class TestTemplateGeneration:
    def test_generate_template(self, tmp_path):
        path = generate_template(str(tmp_path / "agent.yaml"))
        assert path.exists()
        m = parse_manifest(path)
        assert m.name == "my-agent"
        assert m.version == "0.1.0"

    def test_template_is_valid_yaml(self, tmp_path):
        path = generate_template(str(tmp_path / "agent.yaml"))
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict)
        assert "name" in data


# ─────────────────────────────────────────────
# AgentManifest Model
# ─────────────────────────────────────────────

class TestAgentManifest:
    def test_to_dict_serializable(self, tmp_path):
        path = _write_manifest(tmp_path)
        m = parse_manifest(path)
        d = m.to_dict()
        json.dumps(d)  # Must not raise
        assert d["name"] == "test-agent"
        assert d["requirements"]["models"] == ["gpt-4o-mini"]

    def test_cost_display(self):
        m = AgentManifest(avg_cost_per_run=0.04)
        assert m.cost_display == "~$0.04/run"

    def test_cost_display_unknown(self):
        m = AgentManifest()
        assert m.cost_display == "unknown"

    def test_matches_query(self):
        m = AgentManifest(
            name="research-agent",
            description="Deep research with web search",
            capabilities=["research", "synthesis"],
            tags=["web-search"],
        )
        assert m.matches_query("research") is True
        assert m.matches_query("web") is True
        assert m.matches_query("database") is False

    def test_matches_tag(self):
        m = AgentManifest(tags=["research", "web-search"], capabilities=["synthesis"])
        assert m.matches_tag("research") is True
        assert m.matches_tag("synthesis") is True
        assert m.matches_tag("finance") is False

    def test_matches_framework(self):
        m = AgentManifest(frameworks=["langgraph", "direct"])
        assert m.matches_framework("langgraph") is True
        assert m.matches_framework("crewai") is False

    def test_matches_max_cost(self):
        m = AgentManifest(avg_cost_per_run=0.05)
        assert m.matches_max_cost(0.10) is True
        assert m.matches_max_cost(0.03) is False

    def test_matches_max_cost_unknown(self):
        m = AgentManifest(avg_cost_per_run=0)
        assert m.matches_max_cost(0.01) is True  # Unknown passes


# ─────────────────────────────────────────────
# Local Registry
# ─────────────────────────────────────────────

class TestLocalRegistry:
    def test_install_and_list(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        agents = registry.list_installed()
        assert len(agents) == 1
        assert agents[0].name == "test-agent"

    def test_install_copies_manifest(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        installed_manifest = tmp_path / "registry" / "test-agent" / "agent.yaml"
        assert installed_manifest.exists()

    def test_uninstall(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))
        assert registry.is_installed("test-agent")

        registry.uninstall("test-agent")
        assert not registry.is_installed("test-agent")

    def test_uninstall_nonexistent(self, tmp_path):
        registry = LocalRegistry(tmp_path / "registry")
        assert registry.uninstall("nonexistent") is False

    def test_get_manifest(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        m = registry.get_manifest("test-agent")
        assert m is not None
        assert m.name == "test-agent"

    def test_get_manifest_not_installed(self, tmp_path):
        registry = LocalRegistry(tmp_path / "registry")
        assert registry.get_manifest("missing") is None

    def test_search_by_query(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        results = registry.search(query="test")
        assert len(results) == 1
        assert results[0].manifest.name == "test-agent"
        assert results[0].installed is True

    def test_search_no_match(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        results = registry.search(query="financial-analysis")
        assert len(results) == 0

    def test_search_by_tag(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        results = registry.search(tag="mock")
        assert len(results) == 1

    def test_search_by_framework(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        results = registry.search(framework="langgraph")
        assert len(results) == 1

        results = registry.search(framework="crewai")
        assert len(results) == 0

    def test_search_by_max_cost(self, tmp_path):
        manifest_path = _write_manifest(tmp_path / "src")
        registry = LocalRegistry(tmp_path / "registry")
        registry.install(str(manifest_path))

        results = registry.search(max_cost=0.05)
        assert len(results) == 1

        results = registry.search(max_cost=0.01)
        assert len(results) == 0

    def test_install_invalid_manifest_raises(self, tmp_path):
        path = tmp_path / "bad" / "agent.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(yaml.dump({"name": ""}))
        registry = LocalRegistry(tmp_path / "registry")
        with pytest.raises(ValueError, match="Invalid manifest"):
            registry.install(str(path))

    def test_multiple_agents(self, tmp_path):
        for name in ["agent-a", "agent-b", "agent-c"]:
            src = tmp_path / f"src-{name}"
            _write_manifest(src, {"name": name, "description": f"{name} desc"})
            registry = LocalRegistry(tmp_path / "registry")
            registry.install(str(src / "agent.yaml"))

        agents = registry.list_installed()
        assert len(agents) == 3
        names = {a.name for a in agents}
        assert names == {"agent-a", "agent-b", "agent-c"}


# ─────────────────────────────────────────────
# Compose
# ─────────────────────────────────────────────

class TestCompose:
    def test_compose_pipeline(self, tmp_path):
        from agent_mesh.client import compose_pipeline

        registry = LocalRegistry(tmp_path / "registry")
        for name in ["researcher", "analyst"]:
            src = tmp_path / f"src-{name}"
            _write_manifest(src, {
                "name": name,
                "compose": {"role": name, "connects_to": []},
            })
            registry.install(str(src / "agent.yaml"))

        output = str(tmp_path / "compose.yaml")
        path = compose_pipeline(
            ["researcher", "analyst"], output, tmp_path / "registry"
        )
        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert "agents" in data
        assert "researcher" in data["agents"]
        assert "analyst" in data["agents"]

    def test_compose_not_installed(self, tmp_path):
        from agent_mesh.client import compose_pipeline

        with pytest.raises(ValueError, match="not installed"):
            compose_pipeline(
                ["missing-agent"], "out.yaml", tmp_path / "empty-registry"
            )
