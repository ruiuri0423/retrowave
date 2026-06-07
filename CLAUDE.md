# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

RetroWave is a digital timing/waveform editor (Win95/XP retro look) implemented as a **single Python file** `src/retrowave.py` (~2,500 lines), using only the standard library `tkinter`. Pillow is optional and only needed for PNG export.

## Commands

```bash
python src/retrowave.py          # run the app (opens with a demo waveform)
python -m pytest                 # full test suite (~50 tests, <1s; GUI tests briefly open a window)
python -m pytest tests/test_model.py -k group   # run a subset
python -c "import ast; ast.parse(open('src/retrowave.py',encoding='utf-8').read())"   # syntax check
```

Both pytest and the syntax check are the required pre-commit gate. Tests live in `tests/`:
`test_model.py` (pure Model unit tests; every mutating test asserts the §2.6 invariants via
`conftest.assert_invariants`) and `test_app_interactions.py` (real `App` driven by synthesized
events; all GUI tests share one session-scoped Tk root — never create/destroy Tk per test, it
trips Tcl's `tcl_findLibrary`).

## Versioning rule (critical)

Version convention is `vMAJOR.MINOR` (currently v1.18). Any feature or behavior change must bump MINOR and keep **three places in sync**:

1. `src/retrowave.py` — module docstring, window title, and About dialog
2. `docs/RetroWave_Design.md` — the `Spec version:` line at the top **and** a new entry at the top of `## 14. Changelog`
3. `README.md` — if the change affects user-facing features/usage

If the code version is ahead of the docs, backfill the missing changelog entries before committing. Commit message format: `vX.Y: <one-line summary>`.

## Documents

- `docs/RetroWave_Design.md` is the **source-of-truth spec** (architecture, algorithms, invariants, reimplementation guidance). Behavior changes must be reflected in the matching section there, not just in code.
- `docs/COWORK_INSTRUCTIONS.md` defines the maintenance/sync workflow (in Chinese), including the "收尾同步" (wrap-up & sync) procedure: syntax check → bump versions → update design doc changelog → update README → show diff + proposed commit message → **wait for explicit user confirmation before commit/push**. Never force-push.

## Architecture (all inside src/retrowave.py)

Layered, top of file to bottom:

- **`Style` / `Geometry`** — visual constants and presentation knobs (`period_w`, `row_h`, `ramp_ratio`). `Geometry.tw` is the transition width; `copy_scaled(k)` produces a scaled copy for high-res export.
- **`Model`** — the document. Signals are a **flat pool** (list of dicts) identified by stable `sid`; nesting lives in a separate **`group_tree`** (nodes are group metadata + children). `signals` order must always equal the tree's DFS leaf order (`_resync_signals` enforces this after every tree change); `signal["group"]` is only a cached pointer to the direct parent group. Annotations (anchors/relationship edges) anchor by `sid`, never by row index. Persistence: `to_dict`/`load_dict` with migration from the older flat-group format.
- **`Element` hierarchy** — `CLK`, `H`, `L`, `BUS`, `HiZ`, `Unknown` cell renderers. Each exposes `entry_y`/`exit_y` so transitions between neighboring cells are computed by the join resolver `Engine.meet`.
- **`Engine`** — the single drawing routine. It renders by calling `create_line`/`create_rectangle`/`create_text`/… on whatever canvas-like object it's given.
- **Backend canvases** — `PILCanvas` (PNG export) and `SVGCanvas` (SVG export) duck-type the tkinter Canvas drawing API, so on-screen rendering and all exports share the exact same drawing code. EPS uses tkinter's built-in PostScript writer.
- **`TemplateLibrary`** — templates are independent of project files; an index at `~/.retrowave/templates_index.json` maps names → JSON paths; missing files are reported and pruned.
- **`App(tk.Tk)`** — all UI: toolbar, name column + wave canvas, drag/drop reorder & group merge, box select, copy/paste (cell/signal/group scopes), pan mode (Esc), menus, export dialogs.

## Invariants (must hold after every edit — see docs/RetroWave_Design.md §2.6)

1. Transition slope is always `swing/tw`; a half-swing (mid↔hi/lo) spans `tw/2` horizontally, not `tw`.
2. Every copy/paste/template-insert must assign fresh unique `sid`s.
3. `group_tree` is the truth for nesting; keep `signals` in DFS leaf order; `signal["group"]` is a synced cache only.
4. Drag-move uses insert-marker-then-detach-then-replace (avoids the downward-drag off-by-one).
5. Annotations are anchored by `sid`, not row index.
6. Total canvas height = `len(layout())` (group headers occupy rows too), never the signal count.
7. The export multiplier attribute is named `export_scale` (don't shadow Canvas's `scale` method); validate it as a number.
