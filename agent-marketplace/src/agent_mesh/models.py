"""Core data models for agent-mesh."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict

from pydantic import BaseModel, ConfigDict, Field


import time
import logging
import threading
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger("agent_mesh.agent")

class AgentBase(ABC):
    """Base interface every marketplace agent must implement.
    
    Includes native support for OpenTelemetry spans, Circuit Breaking,
    and concurrent Bulkhead isolation.
    """

    _registry_lock = threading.Lock()
    _bulkheads: Dict[str, asyncio.Semaphore] = {}

    def __init__(self, max_concurrent_runs: int = 5):
        self._circuit_state = "CLOSED"
        self._consecutive_failures = 0
        self._max_failures = 3
        self._last_failure_time = 0.0
        self._reset_timeout = 30.0  # Seconds before attempting HALF-OPEN
        self._bulkhead = None  # Lazy init in execute()
        self._max_concurrent_runs = max_concurrent_runs

    def setup(self) -> None:
        """Initialize the agent. Called once before run().
        Useful for setting up connections, API clients, or model weights.
        """

    @asynccontextmanager
    async def _execution_context(self, input_data: str):
        """Internal telemetry & resilience wrapper for agent execution."""
        from opentelemetry import trace
        tracer = trace.get_tracer(__name__)

        # ── Circuit Breaker Logic ──
        if self._circuit_state == "OPEN":
            if time.time() - self._last_failure_time > self._reset_timeout:
                self._circuit_state = "HALF-OPEN"
                logger.info(f"[{self.__class__.__name__}] Circuit Breaker HALF-OPEN (testing recoverability)")
            else:
                raise RuntimeError(f"Circuit Breaker OPEN for agent {self.__class__.__name__}. Cooling down.")
        
        # ── Bulkhead Logic ──
        with self._registry_lock:
            if self._bulkhead is None:
                self._bulkhead = asyncio.Semaphore(self._max_concurrent_runs)

        async with self._bulkhead:
            with tracer.start_as_current_span(
                f"agent.{self.__class__.__name__}.run",
                attributes={"agent.input_length": len(input_data)}
            ) as span:
                start_time = time.monotonic()
                logger.info(f"[{self.__class__.__name__}] Starting run with trace context")
                try:
                    yield span
                    self._consecutive_failures = 0
                    if self._circuit_state == "HALF-OPEN":
                        logger.info(f"[{self.__class__.__name__}] Circuit Breaker CLOSED (recovery successful)")
                        self._circuit_state = "CLOSED"
                except Exception as e:
                    self._consecutive_failures += 1
                    self._last_failure_time = time.time()
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    
                    if self._consecutive_failures >= self._max_failures:
                        self._circuit_state = "OPEN"
                        logger.error(f"[{self.__class__.__name__}] Circuit Breaker tripped (State: OPEN)!")
                    raise
                finally:
                    elapsed = time.monotonic() - start_time
                    span.set_attribute("agent.latency", elapsed)
                    logger.info(f"[{self.__class__.__name__}] Execution completed in {elapsed:.3f}s")

    @abstractmethod
    async def run(self, input: str) -> str:
        """Execute the agent on an input, return the output."""
        ...

    async def execute(self, input: str) -> str:
        """Safe execution wrapper. Applications should call this instead of run()."""
        async with self._execution_context(input):
            return await self.run(input)

    def teardown(self) -> None:
        """Cleanup. Called once after all runs."""


class AgentManifest(BaseModel):
    """Parsed agent.yaml manifest with Pydantic strict validation."""
    model_config = ConfigDict(extra='ignore')

    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    license: str = "MIT"
    entrypoint: str = ""  # module:ClassName

    # Capabilities
    capabilities: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    # Requirements
    models: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    api_keys: List[str] = Field(default_factory=list)
    python_packages: List[str] = Field(default_factory=list)

    # Performance profile
    avg_cost_per_run: float = 0.0
    avg_latency_seconds: float = 0.0
    avg_tokens_per_run: int = 0
    quality_score: float = 0.0

    # Framework compatibility
    frameworks: List[str] = Field(default_factory=list)

    # I/O
    input_type: str = "string"
    input_description: str = ""
    input_examples: List[str] = Field(default_factory=list)
    output_type: str = "string"
    output_format: str = ""
    output_description: str = ""

    # Compose integration
    compose_role: str = ""
    compose_connects_to: List[str] = Field(default_factory=list)

    # Security
    signature: str = ""
    public_key: str = "" # Hex encoded public key

    # Metadata
    source_path: str = ""  # Local path to agent files
    stars: int = 0
    downloads: int = 0

    def to_dict(self) -> dict:
        return self.model_dump()

    @property
    def cost_display(self) -> str:
        if self.avg_cost_per_run > 0:
            return f"~${self.avg_cost_per_run:.2f}/run"
        return "unknown"

    def matches_query(self, query: str) -> bool:
        """Check if this agent matches a search query."""
        q = query.lower()
        searchable = " ".join([
            self.name, self.description,
            " ".join(self.capabilities),
            " ".join(self.tags),
            self.author,
        ]).lower()
        return q in searchable

    def matches_tag(self, tag: str) -> bool:
        return tag.lower() in [t.lower() for t in self.tags + self.capabilities]

    def matches_framework(self, framework: str) -> bool:
        return framework.lower() in [f.lower() for f in self.frameworks]

    def matches_max_cost(self, max_cost: float) -> bool:
        if self.avg_cost_per_run <= 0:
            return True  # Unknown cost passes filter
        return self.avg_cost_per_run <= max_cost


class SearchResult(BaseModel):
    """A search result from the registry."""

    manifest: AgentManifest
    relevance_score: float = 0.0
    installed: bool = False

    def to_dict(self) -> dict:
        d = self.manifest.to_dict()
        d["installed"] = self.installed
        return d
