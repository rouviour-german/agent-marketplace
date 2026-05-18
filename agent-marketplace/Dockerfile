# Production Dockerfile for AgentMesh Node
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install AgentMesh itself
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source and dashboard assets
COPY src/ ./src/

# EXPOSE the Discovery Dashboard and API
EXPOSE 8000

# Set up the mesh registry inside the container
ENV AGENT_MESH_DIR=/data/.agents
RUN mkdir -p /data/.agents

# Default command: Launch the Discovery Dashboard
CMD ["agent-mesh", "dashboard", "--host", "0.0.0.0", "--port", "8000"]
