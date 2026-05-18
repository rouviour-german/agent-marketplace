"""Internal runner script called by the Sandbox to execute agents in isolation."""

import argparse
import sys
from pathlib import Path

# Add the parent of agent_mesh to sys.path if needed
# But usually the runner will be executed in an environment where agent_mesh is installed
# or with the correct PYTHONPATH.

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--registry", default=None)
    
    args = parser.parse_args()
    
    from agent_mesh.registry import LocalRegistry
    import asyncio
    
    try:
        registry = LocalRegistry(args.registry)
        agent = registry.load_agent(args.manifest)
        
        input_data = Path(args.input).read_text()
        # Input might be raw text or JSON depending on the agent
        # For simplicity, we assume strings for now.
        
        async def _run():
            return await agent.execute(input_data)
            
        result = asyncio.run(_run())
        
        Path(args.output).write_text(result)
        sys.exit(0)
    except Exception as e:
        print(f"Runner Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
