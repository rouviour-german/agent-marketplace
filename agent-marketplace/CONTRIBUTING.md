# Contributing to agent-mesh

## Setup
```bash
git clone https://github.com/daniellopez882/agent-mesh.git
cd agent-mesh
pip install -e ".[dev]"
pytest tests/ -v
```

## Current Architecture (FAANG-Ready)
- **Security-First Execution** — Automatic Sandboxing for unverified agents.
- **Dependency Isolation** — Automatic `venv` creation for conflicting agent requirements.
- **Governance** — Cryptographic signing and Ed25519 signature verification.
- **Resilience** — Circuit Breaker, Bulkhead (Semaphore), and OpenTelemetry tracing.
- **Orchestration** — Complex pipelines via the Mesh Orchestrator.
- **Discovery Mesh** — Professional Dashboard for organizational discovery.

## High-Impact Contributions (Next Wave)
- **gRPC Mesh Networking** — Native cross-server remote execution.
- **WASM Runtimes** — Near-native speed with absolute WASM isolation.
- **Autonomous Error Correction** — Orchestrator retries with self-reflection.
- **Persistence** — Stateful pipeline resumption after node failure.
- **Security scanning** — Static analysis of source code before installation.
- **Publish your own verified agents** — Grow the secure mesh!
