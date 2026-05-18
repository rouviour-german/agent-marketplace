import sys
import json

import click

from .client import compose_pipeline
from .manifest import generate_template, parse_manifest, validate_manifest
from .registry import LocalRegistry, RemoteRegistry


@click.group("agent-mesh")
@click.version_option(version="0.1.0", prog_name="agent-mesh")
def cli():
    """npm for AI agents. Publish, discover, and install reusable agents."""


@cli.command()
@click.argument("query", default="")
@click.option("--tag", default="", help="Filter by tag")
@click.option("--framework", default="", help="Filter by framework")
@click.option("--max-cost", type=float, default=0, help="Max cost per run")
def search(query, tag, framework, max_cost):
    """Search for agents in the global registry."""
    click.echo("🔄 Searching the global mesh network...")
    registry = RemoteRegistry()
    results = registry.search(query, tag, framework, max_cost)
    
    local = LocalRegistry()
    for r in results:
        r.installed = local.is_installed(r.manifest.name)

    if not results:
        click.echo("No agents found. Install some first or refine your search.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box

        console = Console()
        table = Table(title=f'Search: "{query or tag or framework}"', box=box.ROUNDED)
        table.add_column("Agent", style="bold cyan", min_width=24)
        table.add_column("Version", width=8)
        table.add_column("Cost", justify="right", width=12)
        table.add_column("Author", width=16)
        table.add_column("Description")

        for r in results:
            m = r.manifest
            table.add_row(
                m.name, m.version, m.cost_display,
                f"@{m.author}", m.description[:50],
            )
        console.print(table)
    except ImportError:
        for r in results:
            m = r.manifest
            click.echo(f"  {m.name} v{m.version} | {m.cost_display} | {m.description[:60]}")


@cli.command()
@click.argument("name")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def info(name, as_json):
    """Show detailed info about an installed agent."""
    registry = LocalRegistry()
    manifest = registry.get_manifest(name)
    if not manifest:
        click.echo(f"Agent '{name}' not found. Is it installed?")
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(manifest.to_dict(), indent=2))
    else:
        click.echo(f"\n{manifest.name} v{manifest.version}")
        click.echo(f"  {manifest.description}")
        click.echo(f"  Author: @{manifest.author}")
        click.echo(f"  Cost: {manifest.cost_display}")
        click.echo(f"  Frameworks: {', '.join(manifest.frameworks) or 'any'}")
        click.echo(f"  Capabilities: {', '.join(manifest.capabilities)}")
        click.echo(f"  Models: {', '.join(manifest.models)}")
        click.echo(f"  Tools: {', '.join(manifest.tools) or 'none'}")
        click.echo()


@cli.command()
@click.argument("manifest_path", default="agent.yaml")
@click.option("--source-dir", default=None, help="Directory containing agent source")
def install(manifest_path, source_dir):
    """Install an agent (from remote mesh or local manifest)."""
    registry = LocalRegistry()
    remote = RemoteRegistry()
    
    target_manifest_path = manifest_path

    # If it's not a local YAML file, we assume it's a Remote Identifier
    if not manifest_path.endswith((".yaml", ".yml")):
        click.echo(f"🔄 Contacting global mesh for '{manifest_path}'...")
        manifest = remote.fetch_manifest(manifest_path)
        if not manifest:
            click.echo(f"❌ Failed to find '{manifest_path}' in the global registry.", err=True)
            sys.exit(1)
            
        # In a complete FAANG architecture, here we'd trigger the Artifact Downloader
        # using manifest.source_path (e.g. S3 bucket, signed URL, or GitHub tree fetch)
        click.echo(f"📥 Found {manifest.name} v{manifest.version}. Simulating artifact download...")
        
        # For MVP purposes: Fail explicitly that remote source code fetching is pending
        click.echo("❌ Remote artifact downloading is disabled in this Phase 1 MVP.")
        click.echo("   Please provide a local agent.yaml path for now.")
        sys.exit(1)

    try:
        import asyncio
        manifest = asyncio.run(registry.install(target_manifest_path, source_dir))
        click.echo(f"✅ Installed {manifest.name} v{manifest.version}")
        click.echo("   Usage: from agent_mesh import load_agent")
        click.echo(f'   agent = load_agent("{manifest.name}")')
    except Exception as e:
        click.echo(f"❌ Install failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("name")
def uninstall(name):
    """Uninstall an agent."""
    registry = LocalRegistry()
    if registry.uninstall(name):
        click.echo(f"✅ Uninstalled {name}")
    else:
        click.echo(f"Agent '{name}' was not installed")


@cli.command("list")
def list_cmd():
    """List installed agents."""
    registry = LocalRegistry()
    agents = registry.list_installed()

    if not agents:
        click.echo("No agents installed. Use 'agent-mesh install' to add some.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box

        console = Console()
        table = Table(title="Installed Agents", box=box.SIMPLE)
        table.add_column("Name", style="bold")
        table.add_column("Version")
        table.add_column("Cost")
        table.add_column("Author")

        for m in agents:
            table.add_row(m.name, m.version, m.cost_display, f"@{m.author}")
        console.print(table)
    except ImportError:
        for m in agents:
            click.echo(f"  {m.name} v{m.version} by @{m.author}")


@cli.command()
@click.option("-o", "--output", default="agent.yaml")
def init(output):
    """Generate a template agent.yaml manifest."""
    path = generate_template(output)
    click.echo(f"✅ Created {path}")
    click.echo("   Edit the manifest, then run 'agent-mesh validate'")


@cli.command()
@click.argument("path", default="agent.yaml")
def validate(path):
    """Validate an agent.yaml manifest."""
    try:
        manifest = parse_manifest(path)
        errors = validate_manifest(manifest)
        if errors:
            click.echo("❌ Validation errors:")
            for e in errors:
                click.echo(f"   • {e}")
            sys.exit(1)
        else:
            click.echo(f"✅ Valid: {manifest.name} v{manifest.version}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("agents", nargs=-1, required=True)
@click.option("-o", "--output", default="agent-compose.yaml")
def compose(agents, output):
    """Generate an agent-compose.yaml from installed agents."""
    try:
        path = compose_pipeline(list(agents), output)
        click.echo(f"✅ Generated pipeline: {path}")
        click.echo(f"   Run with: agent-compose up -f {output}")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("agent_name")
@click.argument("input_text")
def run(agent_name, input_text):
    """Run an installed agent directly."""
    from .registry import load_agent
    import asyncio

    try:
        agent = load_agent(agent_name)
        click.echo(f"🚀 Running agent: {agent_name}...")
        
        async def _run():
            return await agent.execute(input_text)
            
        result = asyncio.run(_run())
        click.echo(f"\nResult:\n{result}")
    except Exception as e:
        click.echo(f"❌ Execution failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("manifest_path", default="agent.yaml")
def publish(manifest_path):
    """Publish an agent to the global mesh registry."""
    remote = RemoteRegistry()
    try:
        manifest = parse_manifest(manifest_path)
        errors = validate_manifest(manifest)
        if errors:
            click.echo("❌ Cannot publish invalid manifest:")
            for e in errors:
                click.echo(f"   • {e}")
            sys.exit(1)

        click.echo(f"🚀 Publishing {manifest.name} v{manifest.version} to global mesh...")
        if remote.publish(manifest):
            click.echo(f"✅ Successfully published {manifest.name}")
            click.echo(f"   Discovery URL: https://agent-mesh.com/agents/{manifest.name}")
        else:
            click.echo("❌ Remote registry rejected the publication.")
            sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Publish failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--port", default=8000, help="Port to run the dashboard on.")
@click.option("--host", default="127.0.0.1", help="Host to bind the dashboard to.")
def dashboard(port, host):
    """Launch the AgentMesh organizational discovery dashboard."""
    import uvicorn
    from .api import app
    click.echo(f"🚀 Launching AgentMesh Dashboard at http://{host}:{port}/dashboard")
    uvicorn.run(app, host=host, port=port)


@cli.command()
@click.argument("compose_file")
@click.argument("input_text")
def compose_run(compose_file, input_text):
    """Execute a composed agent pipeline."""
    from .orchestrator import Orchestrator
    import asyncio

    try:
        click.echo(f"🌀 Loading pipeline from: {compose_file}")
        orchestrator = Orchestrator(compose_file)
        
        async def _run():
            return await orchestrator.execute(input_text)
            
        final_output = asyncio.run(_run())
        click.echo(f"\nFinal Result:\n{final_output}")
    except Exception as e:
        click.echo(f"❌ Pipeline execution failed: {e}", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
