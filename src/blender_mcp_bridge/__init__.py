"""Bridge from Hermes to the official Blender Lab MCP server.

The official add-on (lab_blender_org/mcp) exposes a single operation:
execute arbitrary ``bpy`` Python code inside a running Blender instance.
Requests and responses are JSON objects delimited by a null byte (``\\0``)
over a plain TCP socket (default ``localhost:9876``).

This package wraps that raw protocol in a small, ergonomic client plus a
library of convenience helpers (create objects, assign materials, render,
inspect the scene) and a CLI so Hermes can drive Blender from the terminal.
"""

from .client import BlenderMCPClient, BlenderMCPError, connect
from .helpers import (
    add_cube,
    add_cylinder,
    add_material,
    add_sphere,
    clear_scene,
    delete_object,
    get_scene_info,
    list_objects,
    render_to_file,
    run_bpy,
    set_material_color,
)

__all__ = [
    "BlenderMCPClient",
    "BlenderMCPError",
    "connect",
    "add_cube",
    "add_cylinder",
    "add_material",
    "add_sphere",
    "clear_scene",
    "delete_object",
    "get_scene_info",
    "list_objects",
    "render_to_file",
    "run_bpy",
    "set_material_color",
]

__version__ = "1.0.0"
