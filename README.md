# blender-mcp-bridge

A CLI + Python bridge from [Hermes](https://hermes-agent.nousresearch.com) to the
**official Blender Lab MCP server** add-on (`lab_blender_org/mcp`, shipped for
Blender 5.1+).

## Why this exists

The official add-on exposes exactly one operation over a raw TCP socket:
*execute arbitrary `bpy` Python inside a running Blender*. There are no
structured "create_object" / "set_material" commands — the client sends code,
Blender runs it, and returns whatever the code leaves in a pre-seeded `result`
dict. This bridge wraps that raw protocol in a small ergonomic client, a library
of convenience helpers, and an agent-friendly CLI.

## Protocol

- Transport: plain TCP, default `localhost:9876`.
- Framing: one JSON object terminated by a null byte (`\0`), both directions.
- Request: `{"type": "execute", "code": "<bpy python>", "strict_json": true}`
  (`strict_json` is **required** by the add-on).
- Response: `{"status": "ok", "result": {...}}` or
  `{"status": "error", "message": "..."}`, each optionally carrying `stdout` /
  `stderr` captured from the executed code.

## Install

```bash
cd C:\Users\Name\Projects\blender-mcp-bridge
uv pip install -e .        # or: pip install -e .
```

This puts the `blender-mcp` command on your PATH.

## Prerequisites

1. Blender 5.1+ with the **MCP** add-on enabled (Preferences → Add-ons → MCP).
2. The MCP server **running** (Add-on preferences → "Start MCP Server"; the
   status line should read "Server is running"). Default `localhost:9876`.

## CLI usage

Every command prints one JSON object to stdout on success, or a JSON error to
stderr (exit code 1) on failure — designed for agent consumption.

```bash
blender-mcp ping
blender-mcp info
blender-mcp objects
blender-mcp exec "import bpy; result['n'] = len(bpy.data.objects)"
blender-mcp exec --file scene_setup.py
blender-mcp add-cube --location 0 0 1 --name HeroCube --size 2
blender-mcp add-sphere --radius 0.7 --name Ball
blender-mcp material HeroCube BrandRed --hex e63946 --roughness 0.3
blender-mcp render /tmp/frame.png --engine CYCLES
blender-mcp clear            # remove mesh objects
blender-mcp clear --all      # remove everything
```

Global options: `--host`, `--port`, `--timeout`.

## Python usage

```python
from blender_mcp_bridge import connect, add_cube, add_material, render_to_file

bpy = connect()                       # localhost:9876
add_cube(bpy, size=2, location=(0, 0, 1), name="HeroCube")
add_material(bpy, "HeroCube", "BrandRed", rgba=(0.9, 0.2, 0.3, 1.0))
render_to_file(bpy, "/tmp/frame.png", engine="CYCLES")

# Escape hatch — run anything:
info = bpy.run("import bpy; result['objs'] = [o.name for o in bpy.data.objects]")
```

## Notes & pitfalls

- The server must be started inside Blender each session (auto-start is on by
  default in the add-on preferences).
- Render output paths must be **absolute**.
- `render_to_file` blocks until the frame is done; for very long renders use the
  add-on's deferred path (`check_is_finished`) via `run_bpy`.
- The add-on runs your code in a weak sandbox: `sys.exit()` and a few operators
  (e.g. `wm.quit_blender`) are blocked.
