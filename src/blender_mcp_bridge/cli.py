"""Command-line interface for the Blender MCP bridge.

Designed to be driven by an agent (Hermes) over the terminal: every command
prints a single JSON object to stdout on success, or a JSON error object to
stderr with exit code 1 on failure. This makes output trivially parseable.

Examples
--------
    blender-mcp ping
    blender-mcp info
    blender-mcp objects
    blender-mcp exec "import bpy; result['n'] = len(bpy.data.objects)"
    blender-mcp exec --file scene_setup.py
    blender-mcp add-cube --location 0 0 1 --name HeroCube
    blender-mcp material HeroCube BrandRed --hex e63946
    blender-mcp render /tmp/frame.png --engine CYCLES
    blender-mcp clear --all
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import helpers
from .client import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    BlenderMCPClient,
    BlenderMCPError,
)


def _print_json(value: Any) -> None:
    """Print ``value`` as compact JSON (the machine-readable contract)."""
    print(json.dumps(value, default=repr))


def _error_json(message: str, **extra: Any) -> None:
    """Print a JSON error object to stderr."""
    payload: dict[str, Any] = {"status": "error", "message": message}
    payload.update(extra)
    print(json.dumps(payload, default=repr), file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blender-mcp",
        description="Drive a running Blender instance via the official Blender Lab MCP server.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="MCP server host (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MCP server port (default: %(default)s)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Socket timeout in seconds (default: %(default)s)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping", help="Check the server is reachable")
    sub.add_parser("info", help="Scene summary (object count, frame range)")
    sub.add_parser("objects", help="Detailed list of every object")

    p_exec = sub.add_parser("exec", help="Execute raw bpy Python code")
    p_exec.add_argument("code", nargs="?", help="Python code to run (omit to read from stdin)")
    p_exec.add_argument("--file", help="Read code from a file instead")
    p_exec.add_argument(
        "--lax-json",
        action="store_true",
        help="Allow non-JSON-serializable result values (repr fallback)",
    )

    p_clear = sub.add_parser("clear", help="Delete objects from the scene")
    p_clear.add_argument("--all", action="store_true", help="Delete ALL objects, not just meshes")

    p_del = sub.add_parser("delete", help="Delete one object by name")
    p_del.add_argument("name")

    for cmd, help_text in (
        ("add-cube", "Add a cube"),
        ("add-sphere", "Add a UV sphere"),
        ("add-cylinder", "Add a cylinder"),
    ):
        p = sub.add_parser(cmd, help=help_text)
        p.add_argument("--location", type=float, nargs=3, default=[0.0, 0.0, 0.0], metavar=("X", "Y", "Z"))
        p.add_argument("--name", help="Object name")
        if cmd == "add-cube":
            p.add_argument("--size", type=float, default=2.0)
        elif cmd == "add-sphere":
            p.add_argument("--radius", type=float, default=1.0)
        else:  # add-cylinder
            p.add_argument("--radius", type=float, default=0.5)
            p.add_argument("--depth", type=float, default=2.0)

    p_mat = sub.add_parser("material", help="Create a material and assign it to an object")
    p_mat.add_argument("object")
    p_mat.add_argument("material")
    p_mat.add_argument("--hex", dest="hex_color", help="Base color as #rrggbb")
    p_mat.add_argument("--rgba", type=float, nargs=4, metavar=("R", "G", "B", "A"), help="Base color 0-1")
    p_mat.add_argument("--roughness", type=float, default=0.4)
    p_mat.add_argument("--metallic", type=float, default=0.0)

    p_render = sub.add_parser("render", help="Render the current frame to a file")
    p_render.add_argument("filepath", help="Absolute output path")
    p_render.add_argument("--engine", default="CYCLES", help="CYCLES, BLENDER_EEVEE_NEXT, or BLENDER_WORKBENCH")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    client = BlenderMCPClient(host=args.host, port=args.port, timeout=args.timeout)

    try:
        result = _dispatch(client, args)
    except BlenderMCPError as ex:
        _error_json(str(ex), stdout=ex.stdout, stderr=ex.stderr)
        return 1
    except (KeyError, ValueError) as ex:
        _error_json(str(ex))
        return 1

    _print_json({"status": "ok", "result": result})
    return 0


def _dispatch(client: BlenderMCPClient, args: argparse.Namespace) -> Any:
    cmd = args.command

    if cmd == "ping":
        return {"pong": client.ping()}

    if cmd == "info":
        return helpers.get_scene_info(client)

    if cmd == "objects":
        return {"objects": helpers.list_objects(client)}

    if cmd == "exec":
        code = _read_code(args)
        return helpers.run_bpy(client, code, strict_json=not args.lax_json)

    if cmd == "clear":
        if args.all:
            return helpers.run_bpy(
                client,
                "import bpy\n"
                "removed = [o.name for o in list(bpy.data.objects)]\n"
                "bpy.ops.object.select_all(action='SELECT')\n"
                "bpy.ops.object.delete()\n"
                "result['removed'] = removed\n"
                "result['count'] = len(removed)\n",
            )
        return helpers.clear_scene(client)

    if cmd == "delete":
        return helpers.delete_object(client, args.name)

    if cmd == "add-cube":
        return helpers.add_cube(client, size=args.size, location=tuple(args.location), name=args.name)

    if cmd == "add-sphere":
        return helpers.add_sphere(client, radius=args.radius, location=tuple(args.location), name=args.name)

    if cmd == "add-cylinder":
        return helpers.add_cylinder(
            client, radius=args.radius, depth=args.depth, location=tuple(args.location), name=args.name
        )

    if cmd == "material":
        rgba = _resolve_rgba(args)
        return helpers.add_material(
            client,
            args.object,
            args.material,
            rgba=rgba,
            roughness=args.roughness,
            metallic=args.metallic,
        )

    if cmd == "render":
        return helpers.render_to_file(client, args.filepath, engine=args.engine)

    raise ValueError("Unknown command: {!r}".format(cmd))


def _read_code(args: argparse.Namespace) -> str:
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read()
    if args.code:
        return args.code
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise ValueError("No code supplied: pass code, --file, or pipe via stdin")


def _resolve_rgba(args: argparse.Namespace) -> tuple[float, float, float, float]:
    if args.hex_color:
        return helpers.hex_to_rgba(args.hex_color)
    if args.rgba:
        return tuple(args.rgba)  # type: ignore[return-value]
    return (0.8, 0.2, 0.2, 1.0)


if __name__ == "__main__":
    raise SystemExit(main())
