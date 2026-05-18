"""FastAPI backend for the AgentMesh Dashboard."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from typing import List

from .registry import LocalRegistry
from .models import AgentManifest

app = FastAPI(title="AgentMesh Dashboard API")
registry = LocalRegistry()

# This would normally serve a built React/Vue app
# For MVP: index.html with Tailwind/Alpine.js

@app.get("/api/agents", response_model=List[AgentManifest])
async def list_agents():
    """List all installed agents in the local mesh."""
    return registry.list_installed()

@app.get("/api/agents/{name}", response_model=AgentManifest)
async def get_agent(name: str):
    """Fetch details for a specific agent."""
    manifest = registry.get_manifest(name)
    if not manifest:
        raise HTTPException(status_code=404, detail="Agent not found")
    return manifest

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the static AgentMesh Mesh discovery dashboard."""
    # We'll embed the HTML for simplicity in this turn
    return """
<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentMesh | Discovery Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Outfit', sans-serif; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); }
        .agent-card:hover { border-color: #3b82f6; transform: translateY(-2px); transition: all 0.2s; }
    </style>
</head>
<body class="h-full text-slate-200 antialiased" x-data="{ agents: [], search: '', loading: true }" x-init="agents = await (await fetch('/api/agents')).json(); loading = false">
    
    <!-- Navbar -->
    <nav class="border-b border-slate-800 bg-slate-900/50 px-6 py-4 backdrop-blur-md sticky top-0 z-50">
        <div class="flex items-center justify-between mx-auto max-w-7xl">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 bg-blue-600 rounded flex items-center justify-center font-bold text-white shadow-lg shadow-blue-900/20">M</div>
                <h1 class="text-xl font-bold tracking-tight">AgentMesh <span class="text-blue-500 font-normal">Registry</span></h1>
            </div>
            <div class="flex items-center gap-4">
                <div class="text-xs font-mono px-3 py-1 bg-green-500/10 text-green-400 border border-green-500/20 rounded-full">v0.1.0 Operational</div>
                <div class="w-8 h-8 rounded-full bg-slate-800 border border-slate-700"></div>
            </div>
        </div>
    </nav>

    <main class="mx-auto max-w-7xl p-8">
        <div class="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
            <div>
                <h2 class="text-3xl font-bold mb-2">Discovery Mesh</h2>
                <p class="text-slate-400">Discover, audit, and orchestrate verified AI agents across the organizational fabric.</p>
            </div>
            <div class="w-full md:w-96 relative">
                <input x-model="search" type="text" placeholder="Search by name, author or capability..." 
                       class="w-full bg-slate-900 border border-slate-800 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-600 transition-all">
                <div class="absolute right-3 top-3.5 text-slate-500">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                </div>
            </div>
        </div>

        <div x-show="loading" class="flex items-center justify-center h-64">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>

        <div x-show="!loading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <template x-for="agent in agents.filter(a => (a.name + a.author + a.description).toLowerCase().includes(search.toLowerCase()))">
                <div class="glass p-6 rounded-xl agent-card relative overflow-hidden group">
                    <div class="flex items-start justify-between mb-4">
                        <div>
                            <div class="text-xs font-mono text-blue-400 mb-1" x-text="'v' + agent.version"></div>
                            <h3 class="text-xl font-bold" x-text="agent.name"></h3>
                        </div>
                        <template x-if="agent.signature">
                            <span class="px-2 py-0.5 text-[10px] bg-blue-600/20 text-blue-400 border border-blue-600/30 rounded uppercase tracking-widest font-bold">Verified</span>
                        </template>
                    </div>
                    
                    <p class="text-slate-400 text-sm mb-6 line-clamp-3" x-text="agent.description"></p>
                    
                    <div class="flex items-center gap-2 mb-6 flex-wrap">
                        <template x-for="tag in agent.capabilities">
                            <span class="text-[10px] bg-slate-800 text-slate-300 px-2.5 py-1 rounded-md" x-text="tag"></span>
                        </template>
                    </div>

                    <div class="border-t border-slate-800 pt-4 flex items-center justify-between text-xs text-slate-500">
                        <div class="flex items-center gap-2">
                            <div class="w-5 h-5 rounded-full bg-slate-700 flex items-center justify-center text-[8px] font-bold text-white uppercase" x-text="agent.author[0]"></div>
                            <span x-text="'@' + agent.author"></span>
                        </div>
                        <div x-text="'~$' + agent.avg_cost_per_run.toFixed(2) + '/run'"></div>
                    </div>

                    <!-- Action Hover Reveal -->
                    <div class="absolute inset-0 bg-blue-600/95 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                         <button class="bg-white text-blue-600 px-6 py-2 rounded-full font-bold shadow-xl">Inspect Manifest</button>
                    </div>
                </div>
            </template>
        </div>

        <template x-if="!loading && agents.length == 0">
             <div class="h-96 flex flex-col items-center justify-center gap-4 text-center border-2 border-dashed border-slate-800 rounded-3xl">
                <div class="text-slate-600 text-6xl">∅</div>
                <div class="text-slate-500">No agents installed in the local registry. <br> Run <code class="bg-slate-900 px-2 py-1 rounded">agent-mesh install</code> to get started.</div>
            </div>
        </template>
    </main>

</body>
</html>
    """
