# -*- coding: utf-8 -*-
"""Launch the RetroWave MCP server (stdio) for plugging into AI sessions.

The run-layer counterpart of run.py: run.py starts the GUI, run_mcp.py starts
the MCP server. It resolves src/ onto sys.path itself, so an MCP client can point
straight at this file with no PYTHONPATH wiring:

    {"mcpServers": {"retrowave": {"command": "python",
                                  "args": ["/abs/path/to/run_mcp.py"]}}}

Requires `pip install mcp` (and `pillow` for PNG rendering). All diagnostics go to
stderr — stdout is reserved for the MCP protocol.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def launch():
    """Start the server; turn a missing `mcp` package into a friendly message."""
    try:
        from retrowave.mcp_server import main
        main()
    except ModuleNotFoundError as e:
        if (e.name or "").split(".")[0] == "mcp":
            sys.stderr.write(
                "RetroWave MCP server needs the 'mcp' package:\n"
                "  pip install mcp        (and: pip install pillow  for PNG rendering)\n")
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    launch()
