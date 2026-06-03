# RetroWave

A lightweight **digital timing / waveform editor** with a Windows 95/XP retro look,
built entirely on Python's standard-library `tkinter`. Draw clocks, buses, and
logic-level signals, organize them into collapsible groups, reuse them as
templates, and export to PNG or EPS.

> Status: prototype **v1.7**. Single-file application (`retrowave.py`), no
> third-party dependencies required to run (Pillow is optional, only for PNG export).

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

**Editing & selection**
- Box-select a rectangular region (Shift **or** Ctrl + drag — both are pure
  selection); then press an element key to fill, or `Ctrl+C` to copy.
- Per-signal **color (highlight)** and **offset / phase shift**, applied to one or
  many selected signals at once.
- Multi-select signals in the name column (Ctrl / Shift click); per-signal actions
  live in a right-click menu (color, offset, rename, delete, grouping).

**Groups** (single level, designed to extend to nesting later)
- Create a new group from selected signals, **merge** signals or whole groups into
  a chosen target group, and **remove** individual signals from a group.
- Collapse / expand a group from its header row (collapsed groups show the header
  only).
- Group color cascades to member waveforms (a per-signal color overrides it).
- Group members are kept contiguous automatically, so the on-screen layout and
  click hit-testing always stay in sync.

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
  Pillow, reusing the exact same drawing code as the on-screen canvas. Only
  `pip install pillow` is needed.
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
python retrowave.py
```

The window opens with a small demo waveform so you can start experimenting
immediately.

---

## Usage

**Draw**
1. Pick an element with the toolbar buttons or number keys `1`–`6`
   (CLK / H / L / BUS / HiZ / Unknown).
2. Click a cell to draw it, or drag along a row to brush.
3. For a BUS, click the cell again to type/edit its data label.

**Select & fill a region**
- Hold **Shift or Ctrl** and drag on the canvas to box-select.
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
- *Export* to PNG (needs Pillow) or EPS / PS.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+E` | New / Open / Save / Export |
| `1`–`6` | Select element (CLK / H / L / BUS / HiZ / Unknown) |
| Shift or Ctrl + drag | Box-select on canvas |
| `Ctrl+C` / `Ctrl+V` | Copy / paste (cells, signals, or group — by last selection) |
| `Esc` | Clear selection |
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

## Roadmap

- **Phase D — Programmable / headless interface.** A CLI that renders a spec to
  PNG/EPS without the GUI (the headless renderer already exists), plus an
  LLM-friendly input format so an AI tool can turn a textual spec or document into
  a waveform automatically. A WaveDrom-style wave-string DSL is the leading
  candidate for the AI-facing input.
- **Nested groups.** The data model and layout layer were designed so the single
  level can grow into a tree without touching the data/event layers.
- **Quality-of-life:** negative offsets (phase-left), incremental redraw for very
  large diagrams, and dashed period grid lines in PNG output (currently solid in
  PNG; EPS keeps dashes).

---

## License

No license has been chosen yet. Until one is added, all rights are reserved by the
author; add a `LICENSE` file (e.g. MIT) before sharing if you intend it to be
reusable.
