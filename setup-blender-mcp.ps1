# One-time setup: makes Blender MCP connect automatically on Windows.
# Run in PowerShell:  powershell -ExecutionPolicy Bypass -File .\setup-blender-mcp.ps1
$ErrorActionPreference = "Stop"

# 1. Install uv (provides uvx, which runs the blender-mcp server)
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# 2. Install the Blender addon plus a startup script into every Blender version found
$blenderRoot = Join-Path $env:APPDATA "Blender Foundation\Blender"
if (-not (Test-Path $blenderRoot)) {
    throw "No Blender config found at $blenderRoot. Open Blender once, close it, then rerun."
}
$addonUrl = "https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py"
$startup = @'
import bpy, addon_utils

def _start():
    try:
        addon_utils.enable("blender_mcp_addon", default_set=True, persistent=True)
        bpy.ops.blendermcp.start_server()
        print("Blender MCP server started")
    except Exception as e:
        print("Blender MCP auto-start failed:", e)
    return None

bpy.app.timers.register(_start, first_interval=1.0)
'@

Get-ChildItem $blenderRoot -Directory | ForEach-Object {
    $addons  = Join-Path $_.FullName "scripts\addons"
    $startDir = Join-Path $_.FullName "scripts\startup"
    New-Item -ItemType Directory -Force -Path $addons, $startDir | Out-Null
    Invoke-WebRequest $addonUrl -OutFile (Join-Path $addons "blender_mcp_addon.py")
    Set-Content -Path (Join-Path $startDir "blender_mcp_autostart.py") -Value $startup
    Write-Host "Installed addon and autostart for Blender $($_.Name)"
}

# 3. Register the MCP server with Claude Code for all projects
if (Get-Command claude -ErrorAction SilentlyContinue) {
    claude mcp add blender --scope user -- uvx blender-mcp
    Write-Host "Registered 'blender' MCP server with Claude Code."
} else {
    Write-Host "Claude Code CLI not found. For Claude Desktop, add this to claude_desktop_config.json:"
    Write-Host '  "mcpServers": { "blender": { "command": "uvx", "args": ["blender-mcp"] } }'
}

Write-Host "`nDone. Start Blender, then start Claude. They connect on their own."
