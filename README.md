# RetroWave

A lightweight **digital timing / waveform editor** with a Windows 95/XP retro look,
built entirely on Python's standard-library `tkinter`. Draw clocks, buses, and
logic-level signals, organize them into collapsible groups, reuse them as
templates, and export to PNG, SVG or EPS.

> Status: prototype **v1.27**. A small Python package (`src/retrowave/`) with strict
> three-tier layering — logic (`model`), transfer (`document`: commands, change events,
> undo), and application (headless drawing + a tkinter shell); only `app.py` touches
> tkinter. No third-party dependencies required to run (Pillow is optional, PNG export only).

---

## Features

**Signal drawing**
- Six waveform element types: `CLK` (clock), `H` (logic high), `L` (logic low),
  `BUS` (data bus with an editable label), `HiZ` (high-impedance / mid level),
  and `Unknown` (red hatched "don't care").
- Neighbor-aware transitions: rising/falling edges, bus open/close triangles, and
  `X` data crossings are computed from adjacent cells with a single unified slope,
  so `BUS↔HiZ`, `H↔L`, and data crossings all share consistent geometry.
- Click to paint a single cell, drag to brush a row (the starting row is locked so
  vertical drift does not affect other rows).
- BUS cells preserve existing data when brushed over; click an existing BUS cell
  again to edit its value.

**Onboarding tutorial**
- First launch opens a step-by-step interactive tour: the window dims, each step
  **spotlights** the region it explains (on Windows the highlighted area is fully
  clear *and clickable*, so you can try the gesture immediately). Skip ends it
  permanently; the last step has a "don't show again" checkbox. Reopen anytime via
  *Help → 使用教學*.

**Undo / Redo**
- `Ctrl+Z` / `Ctrl+Y`, last **5 steps**. One gesture = one step: a whole brush stroke,
  block fill, or paste reverts atomically; no-op gestures aren't recorded. Destructive
  operations (delete signals/group, New, Open) are undoable too.

**Editing & selection**
- **Pan mode** (`Esc`): deselects the tool so plain left-drag pans the canvas —
  no more accidental painting while navigating. Panning is clamped to the drawing
  area (no vertical drift when everything already fits the window) and the name
  column always stays in sync. Shift/Ctrl + left-drag still
  box-selects; click an element button or press 1–6 to return to drawing.
  `Esc` works from any state (also clears an active box selection); there is
  deliberately no toolbar button for it.
- Box-select a rectangular region (Shift **or** Ctrl + drag — both are pure
  selection); then press an element key to fill, or `Ctrl+C` to copy.
- Per-signal **color (highlight)** and **offset / phase shift**, applied to one or
  many selected signals at once.
- Multi-select signals in the name column (Ctrl / Shift click); per-signal actions
  live in a right-click menu (color, offset, rename, delete, grouping).

**Groups** (arbitrary nesting depth)
- Create a new group from selected signals; **merge** signals into a group, or
  **nest** one group inside another (a group merged into another becomes a
  subgroup), to any depth.
- **Dissolve** a group (promote its children up one level, keeping any subgroups) or
  **delete** a group together with its whole subtree; apply a single **group-wide
  offset** to all members (including nested) at once.
- Collapse / expand a group from its header row (collapsed groups hide their whole
  subtree); headers and members indent by nesting depth.
- Group color cascades to descendant waveforms (nearest ancestor group wins; a
  per-signal color still overrides it).
- Structure lives in a separate **group tree** (metadata + nesting); signals stay a
  flat pool referenced by stable id, kept in sync with the tree's leaf order — so
  index-based editing, anchors, and hit-testing all keep working.

**Reordering & drag merge/split**
- Drag a signal name to move it: drop onto a group header's lower half or inside a
  group to **merge** it in at the exact cursor position (merge + reorder in one
  move); drop on a header's upper half to place it just before that group; drop
  among top-level signals to move it **out** to the top level.
- Drag a group header to move the whole group; dropping it onto another group
  **nests** it as a subgroup (it can't be dropped into its own descendant).
- Drag starts only after moving past half a row height. While dragging, the view
  dims, the container the item would drop into is highlighted, and an insertion line
  shows the exact landing spot.

**Copy & paste**
- Cell-range copy/paste (auto-adds rows when needed).
- Signal-level copy/paste (full signal incl. name, offset, color, waveform).
- Group-level copy/paste (whole group is duplicated under a fresh group id).

**Template library**
- Templates are stored **independently of project files**; an index file under
  `~/.retrowave/templates_index.json` records the name and path of each template
  JSON.
- Imported templates are auto-loaded on startup. If a referenced file is missing,
  the app reports it and prunes the index.
- Importing a JSON registers it as a template (it does *not* draw to the canvas,
  unlike **Open**). Inserting a template from the **Template** menu adds its
  signals to the canvas and promotes them into a group named after the template.

**Save / export**
- Project save & load as JSON (includes view geometry, colors, and groups).
- **PNG export with no Ghostscript dependency** — rendering is done directly with
  Pillow, reusing the exact same drawing code as the on-screen canvas. A resolution
  multiplier (1×–4×) re-renders at higher pixel density for crisp output (not an
  upscale). Only `pip install pillow` is needed.
- **SVG export (vector)** — a dedicated SVG backend reuses the same drawing engine,
  producing infinitely scalable, editable output (and the dashed period grid is
  preserved). No third-party dependency.
- EPS / PostScript export uses tkinter's built-in PostScript writer (zero
  dependencies).

---

## Requirements

- **Python 3.8+** with `tkinter`.
  - `tkinter` ships with most CPython installs. On some Linux distros you may need
    the system package, e.g. `sudo apt install python3-tk`.
- **Optional:** [Pillow](https://pypi.org/project/Pillow/) for PNG export:
  ```bash
  pip install pillow
  ```
  (EPS / PS export needs nothing extra.)

---

## Getting started

```bash
python run.py            # or: cd src && python -m retrowave
```

No Python? Grab the prebuilt **Windows onefile exe** from the
[Releases](../../releases) page (built automatically from each `v*` tag — tests run
first, PNG export included).

> **SmartScreen / antivirus note**: the exe is currently unsigned, so Windows may show
> a "protected your PC" prompt (More info → Run anyway). Each release ships a
> `SHA256SUMS.txt` to verify integrity, plus an **onedir zip** variant that trips far
> fewer antivirus heuristics than the self-extracting onefile. Code signing hooks are
> already built into the release pipeline (see docs/DEVELOPMENT.md §6.1).

The window opens with a small demo waveform so you can start experimenting
immediately — and a short interactive tutorial on first launch.

---

## Development & tests

New contributor? Start with **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** — it maps every
section of the design spec ([docs/RetroWave_Design.md](docs/RetroWave_Design.md), which is
deliberately language-agnostic) to the actual code symbols, lists the seven iron rules with
their guarding tests, and carries the UI↔core refactoring roadmap.

A pytest suite lives under `tests/`:

```bash
python -m pytest          # run everything (~50 tests, < 1s)
python -m pytest tests/test_model.py -k group   # run a subset
```

- `tests/test_model.py` — pure unit tests for `Model` (signal pool, group tree,
  annotations, save/load + legacy-format migration). Every mutating test ends by
  asserting the design-spec §2.6 invariants (`tests/conftest.py::assert_invariants`).
- `tests/test_app_interactions.py` — smoke tests that drive the real `App` with
  synthesized mouse events (paint, brush row-lock, BUS preservation, box-select
  fill, pan mode, copy/paste, template insertion). A window briefly opens; the
  whole suite shares one Tk root.
- `tests/test_render_coalescing.py` — verifies that bursts of UI mutations inside
  one event-loop cycle repaint the canvas exactly once (`request_render()`
  scheduling) and that the final picture matches the synchronous behavior.
- `tests/test_module_boundaries.py` — enforces the layering: every module except
  `app.py` must be importable without `tkinter` entering `sys.modules`.
- `tests/test_export.py` — headless export tests: SVG structure, exact WaveDrom
  wave strings, PNG pixel dimensions (skipped without Pillow).

Both `python -m pytest` and the `ast.parse` syntax check must pass before a commit.

---

## Usage

**Draw**
1. Pick an element with the toolbar buttons or number keys `1`–`6`
   (CLK / H / L / BUS / HiZ / Unknown).
2. Click a cell to draw it, or drag along a row to brush.
3. For a BUS, click the cell again to type/edit its data label.

**Pan / navigate**
- Press `Esc` to enter **pan mode** (no element selected): left-drag pans the
  canvas, and clicks never paint. The cursor changes to a move shape.
- Shift/Ctrl + left-drag still box-selects while panning.
- Anchors stay fully usable in pan mode: create them from the right-click menu and
  **drag anchor→anchor to draw relationship lines** (anchors take priority over panning).
- Click an element button or press `1`–`6` to go back to drawing.

**Select & fill a region**
- Hold **Shift or Ctrl** and drag on the canvas to box-select (works in both
  draw and pan mode).
- With a region selected, press an element key to fill it, or `Ctrl+C` to copy.

**Per-signal tweaks (name column)**
- Click a name to select; `Ctrl`/`Shift`+click to multi-select.
- **Right-click** a signal for: color, clear color, set offset, create new group,
  merge into a group, remove from group, rename, delete. Actions apply to all
  selected signals.

**Groups**
- Select signals, right-click → *Create new group*.
- **Click a group header** to collapse / expand.
- Right-click a group header for: collapse/expand, group color, rename, merge into
  another group, copy/paste group, dissolve group.

**Templates** (`Template` menu, next to *File* / *Help*)
- *File → Import Template…* registers a JSON file as a reusable template.
- The **Template** menu lists imported templates; click a name to insert it into
  the canvas as a group.
- *Save current canvas as template…* writes the current diagram out and registers
  it.

**Save / export** (`File` menu)
- *Save* / *Open* for project JSON.
- *Export* to PNG (needs Pillow; choose a 1×–4× resolution), SVG (vector), or EPS / PS.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+E` | New / Open / Save / Export |
| `1`–`6` | Select element (CLK / H / L / BUS / HiZ / Unknown) |
| Shift or Ctrl + drag | Box-select on canvas (draw or pan mode) |
| `Ctrl+C` / `Ctrl+V` | Copy / paste (cells, signals, or group — by last selection) |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo (last 5 steps; one gesture = one step) |
| `Esc` | Pan mode: clear selection + deselect tool; left-drag then pans the canvas |
| Right-click on a cell | Clear to Low |
| Double-click a name | Rename |

---

## File format

Projects are plain JSON:

```jsonc
{
  "version": "1.4",
  "n_periods": 12,
  "signals": [
    { "name": "CLK", "offset": 0.0, "color": null, "group": "g1",
      "cells": [ { "type": "CLK", "text": "" }, ... ] }
  ],
  "groups": { "g1": { "name": "SPI", "collapsed": false, "color": "#2266CC" } },
  "view": { "period_w": 78, "row_h": 64, "ramp_ratio": 0.28 }
}
```

A signal is a single source-of-truth object; a *group* is just a label
(`signal.group`) plus group-level metadata in `groups`. The visible row order
(group headers + signals) is computed on the fly at render time, so signals are
never duplicated.

---

## Interoperability

- **WaveDrom JSON export** (*File → Export WaveDrom JSON*) maps signals, groups
  (nested arrays), per-signal phase, and anchors/relationship lines (node/edge) to
  the WaveDrom schema, so diagrams can be shared on GitHub/wikis or rendered by
  WaveDrom tooling. Colors and the custom slope styling are not carried over —
  WaveDrom redraws with its own skin — so the native RetroWave format remains the
  source of truth.

## Roadmap

- **VCD import.** Render deterministic simulation output (the source of truth in a
  Verilog flow) into clean, publication-ready diagrams.
- **Quality-of-life:** multi-select drag, negative offsets (phase-left), incremental
  redraw for very large diagrams, and dashed period grid lines in PNG output
  (currently solid in PNG; SVG/EPS keep dashes).

---

## License

[MIT](LICENSE) © 2026 Ricky (ruiuri0423).
