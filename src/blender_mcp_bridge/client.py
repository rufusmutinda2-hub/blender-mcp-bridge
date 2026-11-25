"""Low-level socket client for the official Blender Lab MCP server.

Protocol (reverse-engineered from ``mcp_to_blender_server.py``):

* Transport: plain TCP, default ``localhost:9876``.
* Framing: a single JSON object terminated by a null byte (``\\0``),
  in **both** directions. No length prefix.
* Request schema::

      {"type": "execute", "code": "<bpy python>", "strict_json": true}

  ``strict_json`` is **required** — the add-on rejects any request that
  omits it (see ``_execute_code_from_request``).
* Response schema::

      {"status": "ok",    "result": <value>, "stdout": "...", "stderr": "..."}
      {"status": "error", "message": "<reason>", "stdout": "...", "stderr": "..."}

The executed code runs inside Blender with a ``result`` dict pre-seeded in
its namespace; whatever the code leaves in ``result`` is returned verbatim.
"""

from __future__ import annotations

import json
import socket
from typing import Any

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876

# The add-on evicts a client that has not sent a complete request within
# ``_CLIENT_TIMEOUT = 10.0`` seconds. We use a slightly larger socket timeout
# so a slow render (which can run synchronously) does not trip the client side
# first; long-running work should use the add-on's deferred path instead.
DEFAULT_TIMEOUT = 60.0

# The add-on caps request size (``_MAX_REQUEST_BYTES``). Keep a little under it.
_MAX_REQUEST_BYTES = 1024 * 1024  # conservative; add-on allows more


class BlenderMCPError(RuntimeError):
    """Raised when the server returns ``status: error`` or the socket fails."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class BlenderMCPClient:
    """A minimal, connection-per-call client for the Blender MCP server.

    Each :meth:`execute` opens a fresh TCP connection, sends one request, and
    reads one response. This matches the add-on's per-request connection model
    and avoids any stale-socket issues between calls.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Core request/response
    # ------------------------------------------------------------------
    def execute(self, code: str, *, strict_json: bool = True) -> dict[str, Any]:
        """Run ``code`` inside Blender and return the raw response dict.

        :param code: Arbitrary ``bpy`` Python source.
        :param strict_json: When true (default) the response ``result`` must be
            JSON-serializable. Leave true for code we generate ourselves.
        :raises BlenderMCPError: On a socket failure or a server-side error.
        """
        request = {"type": "execute", "code": code, "strict_json": strict_json}
        payload = (json.dumps(request) + "\0").encode("utf-8")
        if len(payload) > _MAX_REQUEST_BYTES:
            raise BlenderMCPError(
                "Request exceeds {:d} bytes ({:d} bytes)".format(
                    _MAX_REQUEST_BYTES, len(payload)
                )
            )

        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            ) as sock:
                sock.sendall(payload)
                raw = self._recv_until_null(sock)
        except (OSError, socket.timeout) as ex:
            raise BlenderMCPError(
                "Could not talk to Blender MCP server at {:s}:{:d} — {:s}. "
                "Is Blender running with the MCP server started?".format(
                    self.host, self.port, str(ex)
                )
            ) from ex

        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as ex:
            raise BlenderMCPError(
                "Malformed response from server: {:s}".format(str(ex))
            ) from ex

        if response.get("status") == "error":
            raise BlenderMCPError(
                str(response.get("message", "unknown error")),
                stdout=str(response.get("stdout", "")),
                stderr=str(response.get("stderr", "")),
            )
        return response

    def run(self, code: str, *, strict_json: bool = True) -> Any:
        """Execute ``code`` and return just the ``result`` value."""
        return self.execute(code, strict_json=strict_json).get("result")

    def ping(self) -> bool:
        """Return ``True`` if the server responds to a trivial request."""
        try:
            self.execute("result['pong'] = True")
            return True
        except BlenderMCPError:
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _recv_until_null(sock: socket.socket) -> bytes:
        """Read from ``sock`` until a null-byte delimiter is seen."""
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\0" in chunk:
                break
        data = b"".join(chunks)
        # Strip the trailing delimiter (and anything after it, defensively).
        idx = data.find(b"\0")
        return data[:idx] if idx != -1 else data


def connect(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> BlenderMCPClient:
    """Create a :class:`BlenderMCPClient` (does not open a connection yet)."""
    return BlenderMCPClient(host=host, port=port, timeout=timeout)
