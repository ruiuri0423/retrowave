# -*- coding: utf-8 -*-
"""AI / MCP interface layer (design spec §15) — command-injection over Document.

Two halves, deliberately split so the substance is testable without the `mcp`
package installed:

- `WaveSession` — holds ONE `Document` and exposes the command catalog as plain
  methods returning JSON-able dicts. Fully headless (no `mcp`, no tkinter),
  unit-tested directly. **This is the only way to author a waveform here**: the
  model builds/edits via commands, exactly like a user clicking. It never
  hand-writes the document JSON.
- `serve()` / `main()` — the thin stdio MCP wiring. Imports `mcp` lazily (FastMCP)
  and registers each WaveSession method as a tool. Run as a plugin via
  `python -m retrowave.mcp_server` (see docs for the .mcp.json snippet).

`open_document` / `import_wavedrom` only *load an existing saved file* — the
native document JSON is a persistence format, not an authoring surface.
"""
import json
import os
import tempfile
from typing import List, Optional

from . import __version__
from .document import Document
from .export import export_png, export_svg, wavedrom_dict, wavedrom_to_dict
from .geometry import Geometry
from .templates import TemplateLibrary

WAVE_TYPES = ("CLK", "H", "L", "BUS", "HiZ", "Unknown")


def _ok(**kw):
    d = {"ok": True}; d.update(kw); return d


def _err(msg):
    return {"ok": False, "error": msg}


class WaveSession:
    """One editing session over a single Document. Every method is a tool the
    LLM calls; all references are by signal index / gid / nid (read them from
    get_document). Returns plain dicts so the MCP layer can pass them straight
    through."""

    def __init__(self):
        self.doc = Document()
        self.geom = Geometry()
        self._outdir = tempfile.mkdtemp(prefix="retrowave_mcp_")

    @property
    def model(self):
        return self.doc.model

    # ---- read / lifecycle ----
    def help(self):
        """Read this FIRST if unsure how to use RetroWave. Returns the full guide
        (element vocabulary, the command list, and a worked example). You author
        waveforms ONLY through commands — never by writing document JSON. Same
        content as the waveform:// resources, surfaced as a tool so you can pull
        it into context on demand."""
        return _ok(guide="\n\n".join(f"[{uri}]\n{text}"
                                     for uri, text in _RESOURCES.items()))

    def get_document(self, full: bool = False):
        """Current state. `compact` is a WaveDrom-style readable view; `signals`
        maps each command index to a name/group; `full=True` adds the raw doc."""
        m = self.model
        sigs = [{"index": i, "name": s["name"], "offset": s.get("offset", 0.0),
                 "color": s.get("color"), "group": s.get("group")}
                for i, s in enumerate(m.signals)]
        groups = {g: {"name": v.get("name", g), "collapsed": v.get("collapsed", False),
                      "color": v.get("color")} for g, v in m.groups.items()}
        by = {s["sid"]: s["name"] for s in m.signals}
        anchors = {nid: {"signal": by.get(nd["sid"]), "period": nd["period"],
                         "edge": nd["edge"]} for nid, nd in m.nodes.items()}
        out = _ok(n_periods=m.n_periods, signals=sigs, groups=groups,
                  anchors=anchors, edges=list(m.edges), compact=wavedrom_dict(m),
                  undo_depth=self.doc.history()[0])
        if full:
            out["document"] = m.to_dict()
        return out

    def new_document(self):
        self.doc.new_document()
        return self.get_document()

    def open_document(self, path: str):
        """Load an EXISTING saved RetroWave .json file (not AI-authored JSON)."""
        try:
            with open(path, encoding="utf-8") as f:
                self.doc.load_document(json.load(f))
        except Exception as ex:
            return _err(f"open failed: {ex}")
        return self.get_document()

    def import_wavedrom(self, path: str):
        """Load an EXISTING WaveDrom JSON file."""
        try:
            with open(path, encoding="utf-8") as f:
                self.doc.load_document(wavedrom_to_dict(json.load(f)))
        except Exception as ex:
            return _err(f"import failed: {ex}")
        return self.get_document()

    def undo(self):
        return _ok(undone=self.doc.undo(), **{"history": self.doc.history()})

    def redo(self):
        return _ok(redone=self.doc.redo(), **{"history": self.doc.history()})

    # ---- render ----
    def render(self, format: str = "png", scale: int = 2, path: Optional[str] = None,
               inline: bool = False):
        """Render the current diagram to a file and return its PATH (read the file
        to view it). PNG needs Pillow; SVG is zero-dependency.

        `inline` defaults to **False** — RetroWave's users are mostly engineers who
        want the saved file, and an inline image is a large payload. Pass
        `inline=True` to instead return the PNG as an MCP image block so it
        displays directly in the session (PNG only; SVG always returns a path)."""
        fmt = format.lower()
        if path is None:
            path = os.path.join(self._outdir, f"waveform.{fmt}")
        try:
            if fmt == "png":
                export_png(self.model, self.geom, path, scale=scale)
                size = os.path.getsize(path)
                if inline:
                    return self._inline_png(path, size)
                return _ok(format="png", path=path, bytes=size)
            if fmt == "svg":
                export_svg(self.model, self.geom, path)
                return _ok(format="svg", path=path, bytes=os.path.getsize(path))
            return _err(f"unknown format: {format}")
        except ImportError:
            return _err("PNG export needs Pillow (pip install pillow); try format='svg'")
        except Exception as ex:
            return _err(f"render failed: {ex}")

    @staticmethod
    def _inline_png(path, size):
        """Wrap a rendered PNG in a FastMCP image block. Falls back to the path
        result if `mcp` isn't installed (so headless callers/tests still work)."""
        try:
            from mcp.server.fastmcp import Image
        except ImportError:
            return _ok(format="png", path=path, bytes=size,
                       inline_unavailable="mcp not installed; returning path")
        return Image(path=path)

    # ---- signals ----
    def add_signal(self, name: Optional[str] = None, fill: str = "L"):
        # Not an MCP tool (the plural add_signals covers it); kept for internal use/tests.
        if fill not in WAVE_TYPES:
            return _err(f"fill must be one of {WAVE_TYPES}")
        idx = self.doc.add_signal(name, fill)
        return _ok(index=idx, name=self.model.signals[idx]["name"])

    def add_signals(self, signals: List[dict]):
        """Add one or many signals in ONE undo step (for a single signal pass a
        one-element list). Each entry is {name?, fill?}: omit `name` for an
        auto-generated one; `fill` paints every cell (CLK/H/L/BUS/HiZ/Unknown,
        default "L"). Returns the new {index, name} pairs in order. Validated
        atomically: any bad entry rejects the whole batch (nothing added, no
        undo step)."""
        norm = []
        for i, s in enumerate(signals):
            if not isinstance(s, dict):
                return _err(f"signal {i}: must be an object with optional name/fill")
            fill = s.get("fill", "L")
            if fill not in WAVE_TYPES:
                return _err(f"signal {i}: fill must be one of {WAVE_TYPES}")
            name = s.get("name")
            if name is not None and not isinstance(name, str):
                return _err(f"signal {i}: name must be a string")
            norm.append((name, fill))
        self.doc.begin()
        added = []
        for name, fill in norm:
            idx = self.doc.add_signal(name, fill)
            added.append({"index": idx, "name": self.model.signals[idx]["name"]})
        self.doc.commit()
        return _ok(added=added)

    def remove_signals(self, indices: List[int]):
        return _ok(removed=self.doc.remove_signals(list(indices)))

    def rename_signal(self, index: int, name: str):
        return _ok(renamed=self.doc.rename_signal(index, name))

    def set_offset(self, indices: List[int], value: float):
        return _ok(count=self.doc.set_offset(list(indices), float(value)))

    def set_color(self, indices: List[int], color: Optional[str] = None):
        """color = hex like '#2266CC', or null to clear."""
        return _ok(count=self.doc.set_color(list(indices), color))

    def set_periods(self, n: int):
        return _ok(changed=self.doc.set_n_periods(int(n)), n_periods=self.model.n_periods)

    # ---- cells (drawing) ----
    def set_cell(self, signal: int, period: int, type: str, text: str = ""):
        # Not an MCP tool (the plural set_cells covers it); kept for internal use/tests.
        if type not in WAVE_TYPES:
            return _err(f"type must be one of {WAVE_TYPES}")
        return _ok(set=self.doc.set_cell(signal, period, type, text))

    def fill(self, signal: int, start: int, end: int, type: str, text: str = ""):
        """Fill periods [start, end] (inclusive) of one signal with `type` — one
        undo step. The 'brush' equivalent."""
        if type not in WAVE_TYPES:
            return _err(f"type must be one of {WAVE_TYPES}")
        if not (0 <= signal < len(self.model.signals)):
            return _err("signal index out of range")
        a, b = sorted((int(start), int(end)))
        self.doc.begin()
        n = 0
        for p in range(a, b + 1):
            if self.doc.set_cell(signal, p, type, text):
                n += 1
        self.doc.commit()
        return _ok(filled=n)

    def set_cells(self, cells: List[dict]):
        """Set one or many cells in ONE undo step (for a single cell pass a
        one-element list). `cells` is a list of {signal, period, type, text?}
        objects (`type` ∈ CLK/H/L/BUS/HiZ/Unknown; `text` is the BUS label,
        default ""). Use `fill` instead for a run of the SAME value. Validated
        atomically: if ANY entry is malformed or out of range nothing is
        changed and ok=False is returned (no partial writes, no undo step)."""
        n_sig, n_per = len(self.model.signals), self.model.n_periods
        norm = []
        for i, c in enumerate(cells):
            if not isinstance(c, dict):
                return _err(f"cell {i}: must be an object with signal/period/type")
            try:
                sig, per, typ = int(c["signal"]), int(c["period"]), c["type"]
            except (KeyError, TypeError, ValueError):
                return _err(f"cell {i}: needs signal, period, type")
            if typ not in WAVE_TYPES:
                return _err(f"cell {i}: type must be one of {WAVE_TYPES}")
            if not (0 <= sig < n_sig):
                return _err(f"cell {i}: signal index out of range")
            if not (0 <= per < n_per):
                return _err(f"cell {i}: period out of range")
            norm.append((sig, per, typ, c.get("text", "")))
        self.doc.begin()
        n = sum(1 for sig, per, typ, txt in norm if self.doc.set_cell(sig, per, typ, txt))
        self.doc.commit()
        return _ok(set=n)

    # ---- groups ----
    def create_group(self, indices: List[int], name: Optional[str] = None):
        gid = self.doc.group_signals(list(indices), name)
        return _ok(gid=gid) if gid else _err("could not create group (empty selection?)")

    def merge_into_group(self, indices: List[int], gid: str):
        return (_ok(gid=gid) if self.doc.merge_into_group(list(indices), gid)
                else _err("merge failed (bad gid?)"))

    def dissolve_group(self, gid: str):
        return _ok(dissolved=self.doc.ungroup([gid]))

    def delete_group(self, gid: str):
        return _ok(deleted_signals=self.doc.delete_group(gid))

    def toggle_collapse(self, gid: str):
        r = self.doc.toggle_group(gid)
        return _ok(collapsed=r) if r is not None else _err("bad gid")

    def set_group_color(self, gid: str, color: Optional[str] = None):
        return _ok(set=self.doc.set_group_color(gid, color))

    def rename_group(self, gid: str, name: str):
        return _ok(set=self.doc.rename_group(gid, name))

    # ---- annotations ----
    def add_anchor(self, signal: int, period: int, edge: str = "start"):
        if edge not in ("start", "mid", "end"):
            return _err("edge must be start|mid|end")
        if not (0 <= signal < len(self.model.signals)):
            return _err("signal index out of range")
        nid = self.doc.add_anchor(self.model.signals[signal]["sid"], int(period), edge)
        return _ok(nid=nid) if nid else _err("could not add anchor")

    def add_edge(self, frm: str, to: str, label: str = "", style: str = "double"):
        if style not in ("double", "single", "measure"):
            return _err("style must be double|single|measure")
        e = self.doc.add_edge(frm, to, label, style)
        return _ok(edge=e) if e else _err("could not add edge (bad anchor ids?)")

    # ---- templates ----
    def list_templates(self):
        lib = TemplateLibrary()
        avail, _missing = lib.load()
        return _ok(templates=[e["name"] for e in avail])

    def insert_template(self, name: str):
        lib = TemplateLibrary()
        avail, _ = lib.load()
        entry = next((e for e in avail if e["name"] == name), None)
        if entry is None:
            return _err(f"no template named {name!r}")
        try:
            tsignals = TemplateLibrary.read(entry["path"]).get("signals", [])
        except Exception as ex:
            return _err(f"read failed: {ex}")
        res = self.doc.insert_template(name, tsignals)
        return _ok(group=res[0], indices=res[1]) if res else _err("template empty")


# ---------------------------------------------------------------------------
# Thin stdio MCP wiring. `mcp` is imported here (lazily) so the module above
# stays import-safe and unit-testable without the package. Verify on-machine
# with `pip install mcp` and a real MCP client (Claude Desktop / Claude Code).
# ---------------------------------------------------------------------------
_RESOURCES = {
    "waveform://schema":
        "RetroWave document schema. Element types: " + ", ".join(WAVE_TYPES) + ".\n"
        "A signal has name, offset (phase, 0..0.95), color (hex or null), and cells\n"
        "(one per period). BUS cells carry a text value. Build via commands only.",
    "waveform://commands":
        "Author waveforms ONLY through commands (never by writing JSON):\n"
        "  add_signals([{name, fill}]) / remove_signals / rename_signal / set_offset / set_color\n"
        "  set_cells([{signal, period, type, text}]) — one undo step; single cell = one-element list\n"
        "  fill(signal, start, end, type, text) — a run of the SAME value on one signal\n"
        "  set_periods(n)\n"
        "  create_group(indices, name) / merge_into_group / dissolve_group / delete_group\n"
        "  add_anchor(signal, period, edge) / add_edge(frm, to, label, style)\n"
        "  insert_template(name)\n"
        "Read state with get_document; see the result image with render.\n"
        "open_document(path)/import_wavedrom(path) only OPEN an existing saved file.",
    "waveform://guide":
        "Example — an SPI burst:\n"
        "1. new_document(); set_periods(12)\n"
        "2. add_signals([{'name':'CLK','fill':'CLK'}, {'name':'CS_N','fill':'H'},\n"
        "                {'name':'MOSI','fill':'HiZ'}])\n"
        "3. fill(1,2,8,'L')  # CS_N active-low window\n"
        "4. set_cells([{'signal':2,'period':2,'type':'BUS','text':'CMD'},\n"
        "              {'signal':2,'period':3,'type':'BUS','text':'ADDR'}])\n"
        "5. create_group([1,2],'SPI'); render()",
}

# Method name -> docstring shown to the model (kept short; full guide is a resource).
_TOOLS = [
    "help",
    "get_document", "new_document", "open_document", "import_wavedrom", "render",
    "undo", "redo", "add_signals", "remove_signals", "rename_signal", "set_offset",
    "set_color", "set_periods", "set_cells", "fill", "create_group",
    "merge_into_group", "dissolve_group", "delete_group", "toggle_collapse",
    "set_group_color", "rename_group", "add_anchor", "add_edge",
    "list_templates", "insert_template",
]


def build_server(session=None):
    """Construct and return the FastMCP server (registers all tools + resources)
    without running it — separated from serve() so the wiring is smoke-testable.
    Requires `pip install mcp`."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("retrowave")
    session = session or WaveSession()

    for name in _TOOLS:
        method = getattr(session, name)
        # FastMCP infers the input schema from the bound method's signature.
        server.add_tool(method, name=name, description=(method.__doc__ or name).strip())

    def _const(value):                               # zero-arg reader (FastMCP checks
        def _read():                                 # that params match URI placeholders;
            return value                             # a static URI needs a no-arg function)
        return _read

    for uri, text in _RESOURCES.items():
        server.resource(uri)(_const(text))           # FastMCP resource decorator

    return server


def serve():
    """Run the stdio MCP server. Requires `pip install mcp`."""
    build_server().run()                             # stdio transport by default


def main():
    serve()


if __name__ == "__main__":
    main()
