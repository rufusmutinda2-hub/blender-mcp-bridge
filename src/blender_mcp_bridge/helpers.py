"""Convenience helpers built on top of :class:`~blender_mcp_bridge.client.BlenderMCPClient`.

Every helper generates a small ``bpy`` script, executes it inside Blender via
the MCP server, and returns the ``result`` dict the script produced. All
geometry helpers return at least ``{"name": <object name>}`` so callers can
chain operations (e.g. create an object, then assign a material by name).
"""

from __future__ import annotations

import json
from typing import Any

from .client import BlenderMCPClient

__all__ = [
    "run_bpy",
    "get_scene_info",
    "list_objects",
    "clear_scene",
    "delete_object",
    "add_cube",
    "add_sphere",
    "add_cylinder",
    "add_material",
    "set_material_color",
    "render_to_file",
]


def run_bpy(client: BlenderMCPClient, code: str, *, strict_json: bool = True) -> Any:
    """Run arbitrary ``bpy`` code and return the ``result`` value.

    This is the escape hatch: anything the helpers don't cover can be expressed
    as raw ``bpy`` Python. Remember to write into the pre-seeded ``result``
    dict to get data back, e.g. ``result['count'] = len(bpy.data.objects)``.
    """
    return client.run(code, strict_json=strict_json)


def get_scene_info(client: BlenderMCPClient) -> dict[str, Any]:
    """Return a summary of the active scene: object count, names, frame range."""
    code = (
        "import bpy\n"
        "scene = bpy.context.scene\n"
        "result['scene'] = scene.name\n"
        "result['object_count'] = len(scene.objects)\n"
        "result['objects'] = [o.name for o in scene.objects]\n"
        "result['frame_start'] = scene.frame_start\n"
        "result['frame_end'] = scene.frame_end\n"
        "result['frame_current'] = scene.frame_current\n"
    )
    return client.run(code)


def list_objects(client: BlenderMCPClient) -> list[dict[str, Any]]:
    """Return a detailed list of every object in the scene."""
    code = (
        "import bpy\n"
        "objs = []\n"
        "for o in bpy.context.scene.objects:\n"
        "    objs.append({\n"
        "        'name': o.name,\n"
        "        'type': o.type,\n"
        "        'location': [round(v, 4) for v in o.location],\n"
        "        'visible': o.visible_get(),\n"
        "    })\n"
        "result['objects'] = objs\n"
    )
    return client.run(code)["objects"]


def clear_scene(client: BlenderMCPClient) -> dict[str, Any]:
    """Delete every mesh object in the scene (leaves cameras/lights/empties)."""
    code = (
        "import bpy\n"
        "bpy.ops.object.select_all(action='DESELECT')\n"
        "removed = []\n"
        "for o in list(bpy.context.scene.objects):\n"
        "    if o.type == 'MESH':\n"
        "        removed.append(o.name)\n"
        "        bpy.data.objects.remove(o, do_unlink=True)\n"
        "result['removed'] = removed\n"
        "result['count'] = len(removed)\n"
    )
    return client.run(code)


def delete_object(client: BlenderMCPClient, name: str) -> dict[str, Any]:
    """Delete a single object by name. Raises if the object does not exist."""
    code = (
        "import bpy\n"
        "name = " + json.dumps(name) + "\n"
        "obj = bpy.data.objects.get(name)\n"
        "if obj is None:\n"
        "    raise KeyError('No object named {!r}'.format(name))\n"
        "bpy.data.objects.remove(obj, do_unlink=True)\n"
        "result['deleted'] = name\n"
    )
    return client.run(code)


def add_cube(
    client: BlenderMCPClient,
    size: float = 2.0,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    name: str | None = None,
) -> dict[str, Any]:
    """Add a cube. Returns ``{"name": <final object name>}``."""
    code = (
        "import bpy\n"
        "bpy.ops.mesh.primitive_cube_add(size={size}, location={loc})\n"
        "obj = bpy.context.active_object\n"
        + (_rename_snippet(name) if name else "")
        + "result['name'] = obj.name\n"
    ).format(size=size, loc=location)
    return client.run(code)


def add_sphere(
    client: BlenderMCPClient,
    radius: float = 1.0,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    name: str | None = None,
) -> dict[str, Any]:
    """Add a UV sphere. Returns ``{"name": <final object name>}``."""
    code = (
        "import bpy\n"
        "bpy.ops.mesh.primitive_uv_sphere_add(radius={radius}, location={loc})\n"
        "obj = bpy.context.active_object\n"
        + (_rename_snippet(name) if name else "")
        + "result['name'] = obj.name\n"
    ).format(radius=radius, loc=location)
    return client.run(code)


def add_cylinder(
    client: BlenderMCPClient,
    radius: float = 0.5,
    depth: float = 2.0,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    name: str | None = None,
) -> dict[str, Any]:
    """Add a cylinder. Returns ``{"name": <final object name>}``."""
    code = (
        "import bpy\n"
        "bpy.ops.mesh.primitive_cylinder_add(radius={radius}, depth={depth}, location={loc})\n"
        "obj = bpy.context.active_object\n"
        + (_rename_snippet(name) if name else "")
        + "result['name'] = obj.name\n"
    ).format(radius=radius, depth=depth, loc=location)
    return client.run(code)


def add_material(
    client: BlenderMCPClient,
    object_name: str,
    material_name: str,
    rgba: tuple[float, float, float, float] = (0.8, 0.2, 0.2, 1.0),
    roughness: float = 0.4,
    metallic: float = 0.0,
) -> dict[str, Any]:
    """Create a Principled BSDF material and assign it to ``object_name``."""
    code = (
        "import bpy\n"
        "obj = bpy.data.objects.get(" + json.dumps(object_name) + ")\n"
        "if obj is None:\n"
        "    raise KeyError('No object named {!r}'.format(" + json.dumps(object_name) + "))\n"
        "mat = bpy.data.materials.new(name=" + json.dumps(material_name) + ")\n"
        "mat.use_nodes = True\n"
        "bsdf = mat.node_tree.nodes.get('Principled BSDF')\n"
        "if bsdf is not None:\n"
        "    bsdf.inputs['Base Color'].default_value = " + json.dumps(list(rgba)) + "\n"
        "    bsdf.inputs['Roughness'].default_value = " + json.dumps(roughness) + "\n"
        "    bsdf.inputs['Metallic'].default_value = " + json.dumps(metallic) + "\n"
        "if obj.data.materials:\n"
        "    obj.data.materials[0] = mat\n"
        "else:\n"
        "    obj.data.materials.append(mat)\n"
        "result['material'] = mat.name\n"
        "result['object'] = obj.name\n"
    )
    return client.run(code)


def set_material_color(
    client: BlenderMCPClient,
    material_name: str,
    rgba: tuple[float, float, float, float],
) -> dict[str, Any]:
    """Update the Base Color of an existing material."""
    code = (
        "import bpy\n"
        "mat = bpy.data.materials.get(" + json.dumps(material_name) + ")\n"
        "if mat is None:\n"
        "    raise KeyError('No material named {!r}'.format(" + json.dumps(material_name) + "))\n"
        "bsdf = mat.node_tree.nodes.get('Principled BSDF') if mat.use_nodes else None\n"
        "if bsdf is not None:\n"
        "    bsdf.inputs['Base Color'].default_value = " + json.dumps(list(rgba)) + "\n"
        "result['material'] = mat.name\n"
    )
    return client.run(code)


def render_to_file(
    client: BlenderMCPClient,
    filepath: str,
    engine: str = "CYCLES",
) -> dict[str, Any]:
    """Render the current frame to ``filepath`` (absolute path required).

    Uses the add-on's synchronous execution path, so the call blocks until the
    render finishes. For very long renders prefer the deferred path via
    :func:`run_bpy` with a ``check_is_finished`` callable.
    """
    code = (
        "import bpy\n"
        "bpy.context.scene.render.filepath = " + json.dumps(filepath) + "\n"
        "bpy.context.scene.render.engine = " + json.dumps(engine) + "\n"
        "bpy.ops.render.render(write_still=True)\n"
        "result['filepath'] = " + json.dumps(filepath) + "\n"
        "result['engine'] = " + json.dumps(engine) + "\n"
    )
    return client.run(code)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _rename_snippet(name: str) -> str:
    """Return a bpy snippet that renames the active object to ``name``."""
    return "obj.name = " + json.dumps(name) + "\n"


def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Convert ``#rrggbb`` (or ``rrggbb``) to a normalized RGBA tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError("Expected a 6-digit hex color, got {!r}".format(hex_color))
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b, alpha)
