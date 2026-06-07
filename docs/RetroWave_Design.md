# RetroWave — Design Specification

**Spec version: v1.22** &nbsp;·&nbsp; tracks the implementation version (`retrowave.__version__`). Keep this
header, the program version string, and `README.md` in lock-step on every change. See the
[Changelog](#15-changelog) at the end.

> A complete, implementation-ready design document for the **RetroWave** digital-waveform
> editor. It is written so that an engineer (or model) who has never seen the original code can
> rebuild the product faithfully in any stack (e.g. **React + SVG/CSS**).
>
> All algorithms are given as **language-neutral pseudocode**. No production language syntax is
> used. Where the original used an immediate-mode 2-D canvas, this document abstracts drawing
> behind a small **drawing-surface interface** so the same logic can target a screen canvas, a
> bitmap exporter, or an SVG document.

---

## 0. Product summary

RetroWave is a single-screen editor for drawing **digital timing diagrams** (the kind used in
hardware / Verilog documentation). The user paints waveforms cell-by-cell on a period grid,
organises signals into **arbitrarily nested groups**, adds **timing annotations** (anchors and
relationship lines), and exports to **PNG (1–4×), SVG (vector), EPS/PostScript, and WaveDrom
JSON**. The visual theme is a retro Win95/XP look.

Core design pillars:

1. **One source of truth for waveform data** — a flat list of signals; everything else
   (grouping, ordering, annotations) is a *view* or *overlay* referencing signals by a stable id.
2. **A single drawing routine** used for both screen and every export backend (a thin
   surface-adapter switches the target). This guarantees screen and exports always match.
3. **A unified transition slope** for all waveform edges, derived from one geometry constant.
4. **Stable identity** — signals carry an immutable `sid`; annotations and grouping reference
   `sid`, so reordering/regrouping never corrupts them.

---

## 1. Glossary / domain concepts

- **Period**: one time column (`T0, T1, …`). The diagram has `n_periods` columns of equal width.
- **Cell**: one signal's value during one period. A cell has a **type** and optional **text**.
- **Signal**: one horizontal track (e.g. `CLK`), containing `n_periods` cells, plus presentation
  metadata (name, color, horizontal offset) and a stable id `sid`.
- **Element type**: the kind of waveform a cell draws. One of:
  `CLK, H (high), L (low), BUS, HiZ, Unknown`.
- **Group**: a named container of signals and/or sub-groups; may nest to any depth.
- **Group tree**: the authoritative structure describing nesting + order + group metadata.
- **Row**: one visible line on screen — either a group header or a signal track. Produced by the
  layout algorithm from the group tree.
- **Anchor (node)**: a labelled point pinned to (signal, period, edge) used for annotations.
- **Relationship line (edge)**: a labelled connector between two anchors (timing arrow / measure).
- **Offset**: a per-signal fractional rightward shift (phase), in units of one period.
- **tw**: transition width — the horizontal distance a full vertical swing takes (slope control).

---

## 2. Data model

All persistent state lives in a **Document** with these top-level fields:

```
Document:
    version        : string                  // schema version tag
    n_periods      : integer                 // number of time columns
    signals        : list of Signal          // the flat signal pool (display order)
    group_tree     : list of TreeNode         // nesting + order + group metadata
    nodes          : map  nid -> Anchor       // annotation anchors
    edges          : list of Edge             // annotation relationship lines
    view (optional): Geometry settings        // zoom/size knobs (may be saved separately)
```

### 2.1 Signal

```
Signal:
    sid    : integer        // STABLE unique id, assigned once, never reused for another signal
    name   : string
    color  : color or NULL  // per-signal override; NULL means "inherit / default"
    offset : number in [0, 0.95]   // rightward shift as a fraction of one period
    group  : gid or NULL    // CACHE of the immediate parent group's id (derived from tree)
    cells  : list of Cell, length == n_periods
```

`group` is a **denormalised cache** of "which group directly contains me", recomputed from the
tree after every structural edit. It is convenient for code paths that only care about the
immediate level; the **group tree is the real truth**.

### 2.2 Cell

```
Cell:
    type : one of {CLK, H, L, BUS, HiZ, Unknown}
    text : string   // only meaningful for BUS (the bus value, e.g. "A5"); ignored otherwise
```

### 2.3 Group tree node

```
TreeNode = GroupNode | SigLeaf

GroupNode:
    type      : "group"
    gid       : string            // unique group id, e.g. "g1"
    name      : string
    collapsed : boolean
    color     : color or NULL
    children  : list of TreeNode  // ordered; may contain GroupNodes (nesting) and SigLeafs

SigLeaf:
    type : "sig"
    sid  : integer                // references a Signal by stable id
```

### 2.4 Annotations

```
Anchor (node):
    // key is the nid: a single letter "a".."z", then "aa","ab",… (first free one is reused)
    sid    : integer                 // which signal it is pinned to (stable across reorders)
    period : integer                 // which period column
    edge   : one of {start, mid, end}// where inside the cell: left edge / center / right edge

Edge:
    frm   : nid
    to    : nid
    label : string                   // e.g. "t_su"
    style : one of {double, single, measure}
```

### 2.5 Geometry (presentation knobs, not persisted as document content)

```
Geometry:
    period_w   : pixels per period            (default 84)
    row_h      : pixels per row               (default 64)
    header_h   : pixels of the column-header strip (default 26)
    name_w     : pixels width of the name column   (default 150)
    ramp_ratio : fraction controlling slope   (default 0.20)
    level_hi   : fraction of row height for the HIGH rail  (default 0.20)
    level_lo   : fraction of row height for the LOW rail   (default 0.80)
```

### 2.6 Invariants (MUST hold after every edit)

1. **Identity**: every Signal has a unique `sid`; every SigLeaf in the tree references an existing
   Signal; every Signal appears exactly once as a SigLeaf in the tree.
2. **Order coupling**: the order of `signals` equals the **depth-first leaf order** of
   `group_tree`. (So a contiguous index range in `signals` always corresponds to a contiguous
   vertical span on screen — important for range operations.)
3. **Group cache**: each Signal's `group` equals the id of its immediate parent GroupNode, or
   NULL if it sits at the top level.
4. **No empty groups**: GroupNodes with no children are pruned.
5. **No dangling annotations**: anchors whose `sid` no longer exists are removed; edges whose
   endpoints are missing are removed.

A single routine `RECONCILE()` re-establishes 2–4 after any tree mutation:

```
FUNCTION RECONCILE():
    prune empty groups recursively from group_tree
    // re-order the signal pool to match the tree's DFS leaf order
    order  <- [leaf.sid for leaf in DFS_LEAVES(group_tree)]
    append any signal sids missing from the tree as top-level SigLeafs (safety)
    signals <- signals reordered to match `order`
    // rebuild groups index + each signal's immediate-parent cache
    groups_index <- empty map
    WALK(group_tree, parent_gid = NULL):
        FOR EACH node in this level:
            IF node is GroupNode:
                groups_index[node.gid] <- node
                WALK(node.children, parent_gid = node.gid)
            ELSE:
                signal_with(node.sid).group <- parent_gid
```

`groups_index` (gid → GroupNode) is a runtime convenience so any code can fetch a group's
name/color/collapsed in O(1). Because it stores the **actual node objects**, mutating
`groups_index[gid].collapsed` mutates the tree directly.

---

## 3. Coordinate system & geometry

The wave area is an infinite 2-D plane with `x` increasing rightward, `y` downward. Two scrollable
surfaces share the same vertical scroll: the **name column** (width `name_w`) and the **wave area**.

### 3.1 Vertical levels of a row

For a row whose top is at `row_top`:

```
hi  = row_top + level_hi * row_h          // HIGH rail   (default 20% down)
lo  = row_top + level_lo * row_h          // LOW rail    (default 80% down)
mid = (hi + lo) / 2                        // center line
swing = lo - hi                            // full vertical travel
```

### 3.2 Horizontal period mapping

```
grid_w   = n_periods * period_w                 // right boundary of the period grid
x_of(period p, signal s) = p * period_w + s.offset * period_w
```

The header strip occupies `y in [0, header_h)`; row `r` (0-based, in *visible* order) occupies
`y in [header_h + r*row_h, header_h + (r+1)*row_h)`.

### 3.3 The unified slope (the single most important visual rule)

Every transition (rising/falling edge, bus open/close, X-crossing) uses **one** slope so the whole
diagram looks consistent:

```
A transition with vertical change |dy| occupies horizontal width:
        w = |dy| / swing * tw
equivalently slope = swing / tw  (vertical per horizontal)

where  tw = min(period_w * ramp_ratio, period_w * 0.45)
```

Consequences used throughout:
- A **full swing** (lo↔hi) takes horizontal `tw`.
- A **half swing** (mid↔hi or mid↔lo) takes horizontal `tw/2`.
- A right-angle (vertical) transition has zero width (used for CLK edges and CLK↔level joins).

`ramp_ratio` is user-adjustable (a "slope %" control); clamping at `0.45 * period_w` prevents the
ramp from exceeding a cell.

---

## 4. Drawing-surface abstraction (key to "one routine, many outputs")

Define a minimal surface interface. The waveform engine only ever calls these; the concrete
implementation decides whether pixels go to the screen, a bitmap, or SVG text.

```
INTERFACE Surface:
    line(points, color, width, dash?)          // polyline
    rect(x0,y0,x1,y1, fill?, outline?, width?, dash?)
    polygon(points, fill?, outline?)
    oval(x0,y0,x1,y1, fill?, outline?, width?)
    text(x,y, string, font, fill, anchor)       // anchor in {center, west, east}
    clear()
    // optional: an export_scale property (number); default 1
```

Backends:
- **Screen surface**: forwards to the platform's vector canvas / SVG-in-DOM.
- **Raster surface**: draws onto a bitmap; multiplies stroke widths and glyph sizes by
  `export_scale` (see §9.1).
- **Vector (SVG) surface**: appends SVG primitives to a shared list; supports an `x_offset` so the
  name column and wave area can be merged into one file (§9.2).

> Reimplementation note: in a React/SVG build the *screen* and the *vector export* can be the same
> code path — you literally render SVG elements. The raster exporter then becomes "render the SVG
> at k× and rasterise", or a dedicated canvas pass.

---

## 5. Layout algorithm (group tree → visible rows)

The renderer never walks the tree directly; it first flattens it into an ordered list of `Row`s.

```
Row:
    kind  : "group" | "sig"
    ref   : gid (if group)  |  signal index (if sig)
    depth : integer   // nesting depth, 0 at top level
    gcol  : color or NULL
            //  group row: the group's OWN color
            //  sig   row: the INHERITED color (nearest ancestor group color)

FUNCTION LAYOUT() -> list of Row:
    rows <- []
    index_of_sid <- map each signal's sid -> its position in `signals`
    WALK(nodes = group_tree, depth = 0, inherited = NULL):
        FOR EACH node in nodes:
            IF node is GroupNode:
                emit Row(group, node.gid, depth, node.color)
                IF not node.collapsed:
                    WALK(node.children, depth+1, node.color OR inherited)
            ELSE:                                  // SigLeaf
                si <- index_of_sid[node.sid]
                emit Row(sig, si, depth, inherited)
    RETURN rows
```

Notes:
- **Color cascade**: a signal inherits the *nearest ancestor group's* color; `node.color OR
  inherited` propagates the closest non-null color down. A per-signal `color` overrides this at
  render time (§6.1).
- **Collapse**: a collapsed group emits its header but none of its subtree.
- Total content height = `header_h + length(rows) * row_h`.

---

## 6. Waveform rendering

**Render scheduling (coalescing).** Interaction code never calls `render()` directly; it calls
`request_render()`, which schedules a single redraw via `after_idle` and de-duplicates: any number
of requests inside one event-loop cycle produce exactly one repaint at idle time. A synchronous
`render()` cancels a pending request (so no double paint follows). Only two cases bypass the
queue and render synchronously: the very first paint in `__init__` (so the window appears fully
drawn) and the EPS export, which snapshots the live canvas with tk's `postscript` writer
immediately after redrawing without the selection highlight.

The engine renders the whole scene to two surfaces (name + wave). High-level flow:

```
FUNCTION RENDER(name_surface, wave_surface, document, geometry, selection, cell_selection):
    name_surface.clear(); wave_surface.clear()
    rows = LAYOUT()
    total_h = header_h + length(rows)*row_h
    grid_w  = n_periods * period_w

    // (a) header strip + period grid
    draw "SIGNAL" header box on name_surface
    FOR p in 0..n_periods-1:
        wave_surface.text(p*period_w + period_w/2, header_h/2, "T"+p, LABEL_FONT, TEXT, center)
        wave_surface.line([(p*period_w, header_h), (p*period_w, total_h)], DASH, dash=(2,3))
    draw right boundary dashed line at x=grid_w
    draw top grid line at y=header_h

    // (b) each row
    sig_row <- empty map   // signal index -> visible row number (used by selection + annotations)
    FOR r, row in enumerate(rows):
        row_top = header_h + r*row_h ; row_bot = row_top + row_h
        IF row.kind == group:  DRAW_GROUP_HEADER(row, ...)         // §6.2
        ELSE:                  DRAW_SIGNAL_ROW(row, ...) ; sig_row[row.ref] = r   // §6.1, §6.3

    // (c) overlays drawn last so they sit on top
    DRAW_ANNOTATIONS(wave_surface, sig_row, ...)                   // §7
```

### 6.1 Signal row chrome and color resolution

```
FUNCTION DRAW_SIGNAL_ROW(row, ...):
    si  = row.ref ; signal = signals[si]
    (hi, mid, lo) = levels(row_top)
    ox  = signal.offset * period_w
    inherited = row.gcol
    wave_color = signal.color OR inherited OR DEFAULT_WAVE     // priority: own > group > default
    name_color = signal.color OR inherited OR DEFAULT_TEXT
    indent = 8 + row.depth * 16                                // name label indent by depth

    draw selection highlight behind the name if si in selection
    draw the name label at x=indent: signal.name + (offset shown as "  Δ0.40" if offset>0)
    draw the bottom grid line of the row
    set engine.current_wave_color = wave_color                 // elements read this
    FOR p in 0..n_periods-1:
        element = element_for(cells[p].type)
        element.draw(surface, geometry, cell=cells[p],
                     prev=cells[p-1] or NULL, next=cells[p+1] or NULL,
                     x0 = p*period_w + ox, hi, mid, lo)
    DRAW_OFFSET_EXTENSION(...)                                  // §6.5 (only if ox>0)
```

### 6.2 Group header row

```
FUNCTION DRAW_GROUP_HEADER(row, ...):
    meta = groups_index[row.ref]
    triangle = collapsed ? "▸" : "▾"
    gx = 8 + row.depth * 16                          // indent header text by depth
    draw a "face"-colored bar across the name column; text = triangle + " " + meta.name
       in (row.gcol OR default text color)
    draw a "face"-colored bar across the wave area; if row.gcol: a 3px color ribbon on top edge
    draw the bottom grid line
```

### 6.3 Element rendering algorithms

Each element type implements `draw(surface, geometry, cell, prev, next, x0, hi, mid, lo)` using the
unified slope. They also expose `exit_y` and `entry_y` (the y-level at the cell's right/left
boundary) used by the **join resolver** (`MEET`, §6.4).

Shared locals: `x1 = x0 + period_w`, `tw`, `swing = lo - hi`, `width(dy) = |dy|/swing*tw`,
`col = engine.current_wave_color`, stroke `W = 2`.

**Level elements** — `H` sits at `hi`, `L` at `lo`, `HiZ` at `mid`. `entry_y = exit_y = own level`.

```
FUNCTION LEVEL.draw(...):
    y = own level (hi / lo / mid)
    pe = element_for(prev.type) if prev else NULL
    IF pe is NULL:
        surface.line([(x0,y),(x1,y)])                          // flat
    ELSE IF pe.kind == DATA (BUS/Unknown):                      // bus closes INTO this level
        whi = width(hi - y) ; wlo = width(lo - y)
        surface.line([(x0+min(whi,wlo), y), (x1, y)])           // flat part
        if whi>0.5: surface.line([(x0,hi),(x0+whi,y)])          // converge upper rail
        if wlo>0.5: surface.line([(x0,lo),(x0+wlo,y)])          // converge lower rail
    ELSE IF pe.kind == CLK:                                      // right angle
        if |lo - y|>0.5: surface.line([(x0,lo),(x0,y)])          // vertical riser
        surface.line([(x0,y),(x1,y)])
    ELSE:                                                        // level <-> level ramp
        py = pe.exit_y ; dy = y - py
        IF |dy| < 0.5: surface.line([(x0,y),(x1,y)])
        ELSE:
            w = width(dy)
            surface.line([(x0,py),(x0+w,y)])                     // sloped edge
            surface.line([(x0+w,y),(x1,y)])                      // flat remainder
```

**Clock** — square wave; rising at the period start, high for the first half, low for the second.
`exit_y = lo` (rests low at the boundary), `entry_y` undefined.

```
FUNCTION CLK.draw(...):
    xm = x0 + period_w/2
    rise = MEET(prev.type, CLK) if prev else lo     // level just before the rising edge
    if rise is NULL: rise = lo
    if |rise - hi|>0.5: surface.line([(x0,rise),(x0,hi)])   // vertical rise (height depends on prev)
    surface.line([(x0,hi),(xm,hi)])                          // high half
    surface.line([(xm,hi),(xm,lo)])                          // falling edge
    surface.line([(xm,lo),(x1,lo)])                          // low half
```

**Bus** — a value lane drawn as two parallel rails (at `hi` and `lo`) that open from a point on the
left and close to a point on the right; the value text is centered. `width-of-value` helper
`wl(dv) = |dv| * tw / swing` (same slope).

```
FUNCTION BUS.draw(...):
    sameL = SAME_DATA(prev, cell)     // identical BUS/Unknown value -> continuous, no seam
    sameR = SAME_DATA(cell, next)
    trailing = (not sameR) AND (next is NULL OR element_for(next.type).kind == CLK)
    prevDATA = prev is DATA-kind AND not sameL

    // ----- left boundary -----
    IF sameL:                          xLhi = xLlo = x0          // continue seamlessly
    ELSE IF prevDATA:                                            // value change -> X crossing
        xm = x0 + tw/2
        draw 4 segments: (x0,hi)->(xm,mid), (x0,lo)->(xm,mid),
                          (xm,mid)->(x0+tw,hi), (xm,mid)->(x0+tw,lo)
        xLhi = xLlo = x0 + tw
    ELSE:                                                        // open from a level/clk/none
        vyL = MEET(prev.type, BUS) or mid
        whi = wl(hi - vyL) ; wlo = wl(lo - vyL)
        if whi>0.5: draw (x0,vyL)->(x0+whi,hi)
        if wlo>0.5: draw (x0,vyL)->(x0+wlo,lo)
        xLhi = x0+whi ; xLlo = x0+wlo

    // ----- right boundary -----
    IF trailing:                                                 // close to a point
        vyR = MEET(BUS, next.type) or mid
        whi = wl(hi - vyR) ; wlo = wl(lo - vyR)
        xRhi = x1 - whi ; xRlo = x1 - wlo
        if whi>0.5: draw (x1-whi,hi)->(x1,vyR)
        if wlo>0.5: draw (x1-wlo,lo)->(x1,vyR)
    ELSE:
        xRhi = xRlo = x1

    // ----- optional fill (Unknown subtype) -----
    IF this element has a fill color:
        build the lane polygon from the boundary points and fill it
        draw diagonal hatch lines across the lane (negative slope, spaced ~7px, stepping by `swing`)

    // ----- the two horizontal rails + the boundary segments -----
    surface.line([(xLhi,hi),(xRhi,hi)])
    surface.line([(xLlo,lo),(xRlo,lo)])
    draw all collected left/right boundary segments
    IF cell.text and not sameL:
        surface.text((x0+x1)/2, mid, cell.text, BUS_FONT, text_color, center)
```

**Unknown** — identical to Bus but with a red fill and diagonal hatch (a "don't-care / X" lane).
It does **not** show value text. It inherits the same open/close/cross geometry.

`SAME_DATA(a,b)` is true iff both cells exist, both are BUS or both Unknown of the same type, and
their `text` is equal. This is what makes consecutive equal bus values merge into one continuous
lane (no internal seam), while a changed value produces the X crossing.

### 6.4 Join resolver `MEET`

When two adjacent cells of different element types touch, the boundary y-level must be agreed. Each
element offers `entry_y` (level at its left) and `exit_y` (level at its right). `MEET` picks the
shared level, or `mid` if undecidable.

```
FUNCTION MEET(left_type, right_type) -> y or NULL:
    eL = element_for(left_type).exit_y   if left_type known  else NULL
    eR = element_for(right_type).entry_y if right_type known else NULL
    IF eL and eR present: RETURN (eL == eR) ? eL : NULL    // disagreement -> NULL (caller falls back)
    IF eL present: RETURN eL
    IF eR present: RETURN eR
    RETURN mid
```

`entry_y/exit_y` table: Level elements return their own level for both. CLK returns `lo` for
`exit_y` and nothing for `entry_y` (so its rise height is decided by the previous element).
BUS/Unknown return nothing (they meet at `mid` by default).

### 6.5 Offset (phase) and the virtual edge extension

A signal with `offset = ox_frac` is drawn shifted right by `ox = ox_frac * period_w`. This leaves a
gap on the left `[0, ox]` and pushes the tail past `grid_w`. To make the waveform read as
"continuing from off-screen", draw a **left extension** and **clamp the right**:

```
FUNCTION DRAW_OFFSET_EXTENSION(...):    // only when ox > 0
    f = element_for(cells[0].type)
    IF f.kind == DATA (BUS/Unknown):
        // closing chevron arriving from off-screen, MATCHING the bus slope:
        half_w = |mid - hi| * tw / swing          // == tw/2 ; the half-swing width
        base_x = ox - half_w
        IF base_x > 0:                            // room for a flat lane before the chevron
            draw rails (0,hi)->(base_x,hi) and (0,lo)->(base_x,lo)
            (xh,yh) = (base_x,hi) ; (xl,yl) = (base_x,lo)
        ELSE:                                     // chevron starts off-screen: clip at x=0 on the slope
            t = (-base_x)/half_w
            (xh,yh) = (0, hi + (mid-hi)*t) ; (xl,yl) = (0, lo + (mid-lo)*t)
        draw (xh,yh)->(ox,mid) and (xl,yl)->(ox,mid)   // converge to the cell's opening point
    ELSE IF f.kind == CLK:
        draw (0,lo)->(ox,lo)                      // resting low before first rising edge
    ELSE (LEVEL):
        draw (0, f.entry_y)->(ox, f.entry_y)      // flat at the entry level

    // right clamp: hide the tail pushed past the grid by painting background over it
    rect( grid_w+1, row_top, grid_w+ox+2, row_bot, fill = CANVAS_BG, outline = none )
```

The chevron apex at `(ox, mid)` meets the first cell's own opening (which also converges to `mid`),
forming a clean value-change boundary. **Critical correctness point**: a half-swing transition is
`tw/2` wide, not `tw`. Using `tw` halves the slope and visibly mismatches every other bus edge.

---

## 7. Annotations (anchors + relationship lines)

Annotations live in a separate overlay layer, drawn after all rows. They are pinned by **stable
sid**, so reordering/regrouping never moves them incorrectly; if a signal's row is hidden (inside a
collapsed group) its anchors are simply not drawn.

### 7.1 Anchor screen position

```
FUNCTION ANCHOR_POS(anchor, sig_row) -> (x,y) or NULL:
    si = index_of_sid[anchor.sid]
    IF si is NULL OR si not in sig_row: RETURN NULL        // signal hidden/collapsed -> skip
    ox = signals[si].offset * period_w
    frac = { start:0.0, mid:0.5, end:1.0 }[anchor.edge]
    x = (anchor.period + frac) * period_w + ox
    y = header_h + sig_row[si]*row_h + row_h/2             // vertical center of the row
    RETURN (x,y)
```

### 7.2 Drawing anchors and edges

```
DRAW_ANNOTATIONS:
    pos = { nid: ANCHOR_POS(node) for each node, skipping NULLs }
    FOR each edge whose both endpoints are in pos:  DRAW_EDGE(pos[frm], pos[to], edge.label, edge.style)
    FOR each nid in pos:                            DRAW_NODE(nid, pos[nid])

DRAW_NODE(nid, (x,y), hot=false):
    s = export_scale (1 on screen)
    draw a small circle radius 4*s, white fill (or highlight fill if hot), colored outline
    draw the nid label just above it

DRAW_EDGE(a, b, label, style):
    draw line a->b
    style == double : arrowhead at both ends
    style == single : arrowhead at b only            (causal frm -> to)
    style == measure: a short perpendicular tick at each end (no arrowheads)
    if label: draw it at the midpoint, slightly above the line

ARROWHEAD(tip, from): filled triangle, length 11*s, half-width 5*s, pointing along (tip-from)
TICK(end, other):     perpendicular bar of half-length 6*s at `end`
```

> Note on `export_scale`: glyph sizes scale for high-res export. Read it **defensively** — the
> screen canvas object may expose an unrelated `scale` method, so name the property distinctly
> (e.g. `export_scale`) and coerce non-numbers to 1.

### 7.3 Annotation interaction (no separate mode)

- **Create**: right-click a cell → menu "create anchor here". The edge is chosen by where in the
  cell you clicked: `frac = (cx - ox)/period_w - period; edge = frac<0.34? start : frac>0.66? end : mid`.
- **Hover highlight**: on pointer move, the nearest anchor within ~8px (or edge within ~6px) is
  highlighted. Re-render only when the hovered target changes.
- **Connect (drag to relate)**: press on an anchor (with no modifier) starts a *connecting* drag:
  - the whole wave area dims under a light-gray translucent veil ("freeze");
  - a dashed rubber line follows the cursor from the source anchor;
  - any anchor under the cursor highlights;
  - on release over a different anchor, prompt for a label and create an edge.
- **Delete**: `Delete` removes the hovered anchor (and any edges using it) or the hovered edge.
- **Edit edge**: right-click an edge → edit label / choose arrow style / delete.

Point-to-segment distance is used for edge hit-testing.

---

## 8. Interaction model

### 8.1 Tools and the wave canvas

A current **tool** is one of the six element types (chosen by toolbar buttons or number keys 1–6),
**or none** — the *pan mode* described in §8.1a. Tool = none means the left button navigates
instead of painting, eliminating accidental edits while moving around a large diagram.

```
on_press(wave):
    if tool is NONE and no modifier: begin PAN (record scan origin); stop
    if pointer is over an anchor AND no modifier: begin CONNECT drag (see §7.3); stop
    record press cell ; moved=false
    if Ctrl or Shift held: begin BOX-SELECT          # works in both paint and pan mode
    else: PAINT the press cell with the current tool

on_motion(wave):
    if PAN: scroll the wave canvas by the cursor delta (gain 1);
            sync the name column's vertical view to the wave canvas; stop
    if CONNECT: update rubber line + freeze + target highlight
    else if BOX-SELECT: update the marquee rectangle
    else if a press cell exists: PAINT along the SAME ROW as the press (row-locked brush)

on_release(wave):
    if PAN: end panning; stop
    if CONNECT: finalize edge (see §7.3)
    else if BOX-SELECT: store the rectangular cell selection
```

### 8.1a Pan mode (tool = none)

`Escape` is the single entry point — there is **no toolbar button** for pan mode. From *any*
state (tool selected, box selection active, both) `Escape` clears the box selection, deselects
the tool, and enters pan mode in one press. The cursor switches to a move/fleur shape and the
status bar announces the mode.

While in pan mode:
- **Left-drag** pans the canvas in both axes (the name column follows vertically). Panning is
  implemented with fraction-based `xview_moveto`/`yview_moveto` anchored at the press point —
  **not** tk's `scan_mark`/`scan_dragto`, which ignore the scrollregion. An explicit
  per-axis gate `_scrollable()` compares the scrollregion size against the visible window
  size: when the content does not exceed the window on an axis, that axis is **forced to
  origin (fraction 0)** instead of panned — `moveto`'s own clamping is *not* relied upon.
  The same gate is applied to the mouse wheel and the vertical scrollbar callback, and
  `render()` snaps the view back to origin when content shrinks below the window size
  (row deletion, group collapse). The name column is always synced from the wave canvas's
  *post-clamp* y-fraction so the two panes can never drift apart.
- **Shift/Ctrl + left-drag** still performs BOX-SELECT, exactly as in paint mode; with a
  selection active, element keys fill the block as usual (filling does not leave pan mode).
- A plain left click never paints, never starts a CONNECT drag, and keeps the current
  box selection intact (panning is pure navigation).
- Right-click context menus (anchors, edges, "clear to L") remain available.

Exiting pan mode: click any element button or press a number key 1–6 (when no box selection is
active — otherwise the key fills the selection first, per §8.1).

**Painting rules**:
- Setting a cell to the current tool replaces its type.
- **BUS specifics**: a cell that is already BUS keeps its value (continuity); a non-BUS cell
  becomes BUS; re-clicking a BUS cell opens a prompt to edit its value.
- **Cell hit-test** must subtract the signal's offset: `period = floor((cx - offset*period_w)/period_w)`.

**Box selection** produces a rectangle `(row0,row1, period0,period1)`. With a selection active:
- pressing an element key fills the whole block with that type (BUS asks once for a value),
- `Ctrl+C` copies the block of cells.
`Escape` clears the selection.

### 8.2 Name column: select vs. drag

The name column uses a press/drag/release model so a click can mean "select" while a drag means
"reorder/merge". The drag threshold is **half a row height**.

```
on_name_press: record the row under the cursor; dragging=false
on_name_drag:
    if not dragging and moved vertically more than row_h/2: dragging=true; choose subject
        subject = the pressed row's group (if header) or signal (if track)
    if dragging: COMPUTE_DROP(cursor_y); re-render with the drag overlay
on_name_release:
    if dragging: perform the move from COMPUTE_DROP result (§8.3); else treat as a CLICK
CLICK on a signal: select (Ctrl toggles, Shift extends a range, plain replaces)
CLICK on a group header: toggle collapse
double-click: rename the row (signal or group)
right-click: open the signal menu or the group menu
```

### 8.3 Drag drop resolution (reorder + merge + split, one gesture)

The cursor's vertical position picks a **target container** and an **insertion index** within it.
The container is "the innermost thing the cursor is over" and lights up; an insertion line shows the
exact landing slot. The same routine handles plain reordering, merging into a group, moving out to
the top level, and nesting one group inside another.

```
FUNCTION COMPUTE_DROP(cursor_y):
    rows = LAYOUT()
    r    = clamp(floor((cursor_y - header_h)/row_h), 0, len(rows)-1)
    lower = fractional_part((cursor_y - header_h)/row_h) >= 0.5
    row = rows[r]

    IF row.kind == group:
        gid = row.ref
        IF not lower:                         // upper half of a header -> sibling, BEFORE this group
            (parent_gid, _, idx) = LOCATE_GROUP(gid)
            container = parent_gid ; index = idx ; highlight = parent_gid
        ELSE:                                 // lower half -> INTO this group at the front
            container = gid ; index = 0 ; highlight = gid
    ELSE:                                     // a signal row
        sid = signals[row.ref].sid
        (parent_gid, _, idx) = LOCATE_LEAF(sid)
        container = parent_gid
        index     = idx + (lower ? 1 : 0)
        highlight = parent_gid                // NULL means top level

    valid = true
    IF dragging a group AND container is the dragged group itself or a descendant: valid = false

    insertion_line_y = top of the visible row of the (container, index) child, or end-of-container
    RETURN { container, index, valid, highlight, y: insertion_line_y }
```

`LOCATE_LEAF(sid)` / `LOCATE_GROUP(gid)` return `(parent_gid, children_list, index_in_parent)` by a
recursive search of the tree (parent_gid NULL means top level).

On release, if `valid`, call the appropriate **container move** (§5.x below). Because the move uses
the *marker technique* it is immune to the classic off-by-one when the dragged item starts in the
same container above the target slot.

```
FUNCTION MOVE_LEAF_TO(sid, container_gid, index):
    cont = children_list_of(container_gid)          // group_tree itself if container_gid is NULL
    clamp index into [0, len(cont)]
    insert a MARKER into cont at index
    detach the SigLeaf(sid) from wherever it currently is   // marker shifts naturally if needed
    replace the MARKER (find it in cont) with the detached leaf
    RECONCILE()

FUNCTION MOVE_GROUP_TO(gid, container_gid, index):
    reject if container_gid is gid or a descendant of gid (cycle guard)
    same marker-insert / detach-group / replace pattern
    RECONCILE()
```

> Why the marker works: you reserve the destination slot *first*; detaching the source afterward
> auto-corrects indices regardless of whether the source was above or below the slot. This is the
> robust fix for "the visual insertion point is one row off when dragging downward".

### 8.4 Drag overlay (focus feedback)

```
DRAW_DRAG_OVERLAY:
    dim the entire name column and wave area under a translucent light-gray veil ("background")
    if highlight (container) is a group and the drop is valid:
        draw a bright outline rectangle around that group's full visible span ("lit container")
    draw the insertion line across both columns at drop.y
       (use the normal accent color if valid, a warning color if invalid)
```

This realises the agreed language: **the dimmed area is background; the lit thing is the container
the item will drop into**, switching as the cursor moves between a group and the surrounding level.

### 8.5 Copy / paste (three scopes)

A single `Ctrl+C` / `Ctrl+V` dispatches by the last context the user acted in:

- **Cells**: copy the selected rectangle; paste at the hovered cell, auto-adding rows if needed.
- **Signals**: copy whole signals (name/offset/color/cells); paste as new top-level signals with
  **fresh sids** and de-duplicated names, inserted after the selected row's top-level position.
- **Group**: copy a group's (flattened) members; paste as a new top-level group with a fresh gid,
  fresh sids, de-duplicated names.

> Fresh sids on paste/template-insert are **mandatory**: duplicate or missing sids collapse the
> sid→signal map and make annotations attach to the wrong signal.

### 8.6 Offset editing

A numeric control sets the selected signal's `offset` (0..0.95). The name label shows `Δ0.40`.
Group-level offset applies one absolute value to **all descendants** of a group at once.

---

## 9. Export

All exports reuse `RENDER` (§6) through a surface backend, so they always match the screen.

### 9.1 PNG (raster, 1–4×)

```
FUNCTION EXPORT_PNG(path, scale in {1,2,3,4}):
    g2 = geometry scaled by `scale`              // period_w, row_h, header_h, name_w *= scale
                                                 // ratios (ramp/level) unchanged
    fonts = load fonts at size ~ 12*scale
    rows = LAYOUT() ; height = header_h_scaled + len(rows)*row_h_scaled   // USE len(rows)!
    name_img = bitmap(name_w_scaled, height) ; wave_img = bitmap(wave_w_scaled, height)
    RENDER( raster_surface(name_img, export_scale=scale),
            raster_surface(wave_img, export_scale=scale),
            document, g2, selection=empty, cell_selection=none )
    compose name_img | wave_img side by side ; save
```

This is a **true higher-density re-render** (sharp), not an upscale. Stroke widths and annotation
glyphs scale via `export_scale`. (Raster backends may lack native dashes → period grid renders
solid in PNG; vector backends keep dashes.)

### 9.2 SVG (vector, infinite resolution)

```
FUNCTION EXPORT_SVG(path):
    rows = LAYOUT() ; W = name_w + wave_w ; H = header_h + len(rows)*row_h
    elems = []                                   // shared element list
    RENDER( svg_surface(elems, x_offset=0),       // name column at x 0
            svg_surface(elems, x_offset=name_w),  // wave area shifted right by name_w
            document, geometry, empty, none )
    wrap elems in <svg width=W height=H> with a background rect ; write file
```

Text uses a CJK-capable font-family fallback; `anchor` maps to `text-anchor` (center→middle,
west→start, east→end) with a middle baseline. Dashes are preserved.

### 9.3 EPS / PostScript

Use the platform canvas's native PostScript writer for the wave area (zero dependencies). This path
is vector but only covers the wave area in the original (names are a separate surface).

### 9.4 WaveDrom JSON (interchange)

Maps the document to WaveDrom's schema. **Lossy on purpose**: colors and the custom slope are not
represented (WaveDrom redraws with its own skin); grouping, phase, and anchors/edges *are* carried.

```
WAVE-CHAR per cell type:  CLK->'p'  H->'1'  L->'0'  HiZ->'z'  Unknown->'x'  BUS->'='
CONTINUATION '.' :  for BUS, when the next cell has the SAME value;
                    for others, when the next cell has the SAME type.

FUNCTION SIG_OBJECT(signal):
    walk cells left to right:
        if continues previous: emit '.'
        else: emit the type's wave-char; if it is '=', push the cell.text onto data[]
    result = { name, wave }
    if data nonempty: result.data = data
    if offset != 0:   result.phase = -offset        // WaveDrom phase is leftward; we shift right
    if this signal has anchors: result.node = a string with the nid placed at each anchor's period
    RETURN result

FUNCTION SIG_LIST(nodes):                            // recurse the group tree -> nested arrays
    out = []
    FOR node in nodes:
        if GroupNode: out.append( [ node.name ] + SIG_LIST(node.children) )
        else:         out.append( SIG_OBJECT(signal_of(node.sid)) )
    RETURN out

document.signal = SIG_LIST(group_tree)
document.edge   = for each edge: "<frm><op><to> <label>"
                  op: double->"<->", single->"->", measure->"-"
```

---

## 10. Persistence & migration

- **Save**: write the Document JSON (`version`, `n_periods`, `signals`, `group_tree`, `nodes`,
  `edges`; optionally the geometry under `view`).
- **Load (new format)**: adopt `group_tree` directly; backfill any missing signal fields; assign a
  `sid` to any signal lacking one; restore the gid sequence counter from existing gids; then
  `RECONCILE()` and prune dangling annotations (reporting how many were removed).
- **Load (legacy flat format)**: older files had `signal.group = gid` plus a flat `groups` map and
  no tree. Migrate by scanning signals in order: a run of equal `group` becomes one GroupNode whose
  children are those signals; ungrouped signals become top-level SigLeafs. (Single level only,
  which is exactly what the old format could express.)
- **Orphan annotations**: after load, anchors referencing absent sids are pruned and the user is
  told in the status bar (so anchors never vanish silently).

---

## 11. UI structure (chrome)

```
Window
├── Menu bar
│   ├── File: New, Open, Save, Import Template, Export Image, Export WaveDrom JSON, Exit
│   └── Help: Usage, Shortcuts
├── Toolbar
│   ├── Element buttons: CLK H L BUS HiZ Unknown  (also keys 1..6)
│   ├── Group/offset actions (create group, set offset, …)
│   └── Geometry spinners: width(period_w), row height, slope%(ramp_ratio*100), periods(n_periods)
├── Main split
│   ├── Name column surface  (fixed width = name_w; shows headers + names; drag to reorder/merge)
│   └── Wave area surface     (scrollable; the diagram; shared vertical scroll with name column)
└── Status bar (transient messages: actions performed, warnings, hints)
```

Context menus:
- **Signal name** (right-click): recolor / clear color / set offset / create group / merge into
  group / move out of group / rename / delete (applies to the whole multi-selection).
- **Group header** (right-click): collapse/expand / recolor / group offset / rename / merge into
  another group (becomes a subgroup) / copy / paste / dissolve (promote children up one level) /
  delete (with whole subtree).
- **Wave cell** (right-click): create anchor here / clear to L.
- **Edge** (right-click): edit label / arrow style / delete.

Dialogs are simple prompts: text entry (names, bus values, edge labels), number entry (offset,
export scale), and a color picker.

Default theme tokens (retro look):

```
FACE        #ECE9D8   (toolbars/headers)        FACE_DARK  #ACA899
CANVAS_BG   #FBFBF6   (drawing background)       GRID       #C8C8C8
DASH        #B9B9A8   (period gridlines)         WAVE       #101010  (default waveform)
TEXT        #202020   SEL #BFD9FF (row select)   UNK_FILL   #E79B9B  UNK_HATCH #A83232
ACCENT/MARQUEE #1F5FBF (selection, drag, anchors/edges accent: a violet ~#6A3FB5 in the original)
Fonts: UI/name ~9px (bold for names/keys); monospace ~9px for period labels and bus values
```

Keyboard: `Ctrl+N/O/S/E` (new/open/save/export), `Ctrl+C/V` (copy/paste), `1..6` (tools),
`Delete` (annotation under cursor), `Escape` (clear cell selection), `Shift/Ctrl+drag` (box select).

---

## 12. Reimplementation guidance for React + SVG/CSS

This product maps cleanly onto a modern declarative stack. Suggested approach:

**State** — keep the Document in a single store (signals, group_tree, nodes, edges, n_periods) plus
ephemeral UI state (current tool, selection set, cell selection rect, hovered anchor/edge, drag
state). `LAYOUT()` is a **pure selector** deriving the row list from the tree; memoise it.

**Rendering** — render the wave area as **one SVG** (it doubles as your vector export). Map each
`Row` to an SVG group; element drawing routines emit `<polyline>/<polygon>/<text>` exactly as the
pseudocode describes. Because SVG is resolution-independent, "PNG export at k×" becomes "serialize
the SVG and rasterize at k×". CSS handles all chrome (toolbar, name column, menus, status bar).

**Component tree (suggested)**:

```
<App>
  <MenuBar/> <Toolbar/>
  <Editor>                     // CSS grid: [name column | wave area], shared vertical scroll
    <NameColumn rows=…         // headers + names; pointer handlers for select/drag
        onReorder=…/>
    <WaveCanvas rows=…>        // an <svg>; renders grid + elements + annotations + overlays
        <Grid/> <Rows/> <AnnotationLayer/> <DragOverlay/> <ConnectOverlay/>
    </WaveCanvas>
  </Editor>
  <StatusBar/>
  <Dialogs/>                   // prompts + color picker
```

**Events** — use pointer events. The wave area needs: click/drag painting (row-locked), Shift/Ctrl
marquee, anchor hover + connect-drag with a freeze overlay (an absolutely-positioned dim layer with
the live anchors/edges drawn above it). The name column needs the press/drag/release select-vs-move
logic with the half-row threshold and the `COMPUTE_DROP` container/index resolution.

**Pitfalls to carry over** (all learned the hard way):
1. Keep `signals` ordered to match the tree's DFS leaves after every edit (`RECONCILE`).
2. Assign **fresh, unique sids** on every paste / template insert; never let two signals share one.
3. The half-swing transition width is **`tw/2`**, not `tw` — using `tw` halves the slope and breaks
   the consistent look (notably the offset bus chevron).
4. Use the **marker insert-before-detach** technique for moves to avoid the downward-drag
   off-by-one.
5. Anchor by **sid**, never by row index — rows change with grouping/collapse.
6. Use `len(LAYOUT())`, not the signal count, for total height (group headers add rows).
7. Name your export-scale property distinctly so it can't collide with a host canvas method.

**Testing methodology** (recommended, tooling-agnostic): exercise the pure core (tree ops, layout,
serialization/migration, element geometry, exports) headlessly with a standard coverage tool; drive
the UI in a headless browser/display with synthesized pointer events for the interactive paths
(paint, box-select, the three pastes, create/connect/delete annotations, drag reorder/merge/split,
collapse, undo of structure via dissolve, old-file migration). Aim high on core logic; treat the
interaction layer separately since its branches are event-driven.

---

## 13. Feature checklist (what "done" means)

- [x] Six element types with a single unified slope; correct joins via `MEET`.
- [x] BUS continuity, value text, X-crossing on value change; Unknown red/hatched lane.
- [x] Per-signal color, name, and fractional **offset** with virtual edge extension
      (BUS left **closing chevron** matching the bus slope; right clamp).
- [x] **Arbitrarily nested groups** via a group tree; recursive layout; depth indent;
      color cascade; collapse/expand of whole subtrees.
- [x] Group ops: create, merge-signals-in, **nest** (merge group into group), move-out, dissolve
      (promote), delete (with subtree), group recolor, **absolute group offset**.
- [x] Name-column **drag** that reorders / merges-in / moves-out / nests in one gesture, with a
      focus overlay (dim background, lit target container, insertion line) and cycle guard.
- [x] Cell painting (row-locked brush), box selection + block fill, three-scope copy/paste.
- [x] **Annotations**: anchors (sid-pinned) + relationship lines with double/single/measure styles;
      hover highlight; drag-to-connect with a freeze overlay; delete; edit.
- [x] Exports: **PNG 1–4×** (sharp re-render), **SVG** (vector, dashes preserved), **EPS/PS**,
      **WaveDrom JSON** (nested groups, phase, node/edge; colors/slope intentionally not preserved).
- [x] JSON persistence with **legacy-flat→tree migration** and orphan-annotation pruning + report.

---

## 14. UI ↔ Core protocol

> **Status: design adopted (2026-06-07); implementation phased in.** Today's code still couples
> the UI shell directly to the document (the violation inventory and migration roadmap live in
> `docs/DEVELOPMENT.md`). New code MUST follow this protocol; existing call sites migrate per
> the roadmap. This section is the contract — it stays language-agnostic on purpose, so the
> same core can serve a tkinter shell today and an SVG/web shell (§12) tomorrow.

### 14.1 The two sides

**Document core** owns everything that is *the document*:
- persisted content — signals (flat pool, sid identity), group tree, annotations, `n_periods`;
- derived queries — `LAYOUT()` (§5), hit-test math (screen point → row/period given a geometry),
  anchor positions (§7.1);
- **commands** — the only way content changes (§14.3);
- **change events** — the only way the outside world learns content changed (§14.4).

The core is fully headless: it never imports a UI toolkit, never calls into the shell, and is
testable without a window.

**UI shell** owns everything that is *the session*:
- input mapping (mouse/keyboard gestures → command invocations);
- render scheduling (§6 coalescing) and all drawing surfaces;
- dialogs, menus, status bar, clipboard UX;
- **transient state**: active tool, selection (signals and cell range), hover, marquee,
  drag ghost, pan anchor, connect-in-progress.

Transient state is deliberately *not* document content: it is never persisted, never undoable,
and never crosses into the core except as plain command arguments.

### 14.2 Rules

- **R1 — Commands only.** The shell mutates the document exclusively through named commands
  with plain-data arguments. It never touches internal structures (signal list, group tree,
  annotation maps) and never calls private helpers.
- **R2 — One-way calls.** The core never calls the shell. Information flows out only as command
  return values, query results, and change events.
- **R3 — Plain data across the boundary.** Every argument and result crossing the boundary is
  JSON-serializable (numbers, strings, lists, dicts, sid/gid/nid handles). No toolkit objects,
  no live references into core internals.
- **R4 — Invariants after every command.** A command either leaves the document satisfying all
  §2.6 invariants or fails as a whole (no partial mutations escape).
- **R5 — One command = one undo unit = at most one change event.** A continuous gesture
  (e.g. a brush stroke from press to release) is *one* command; the shell accumulates it and
  submits once, or the core offers an explicit begin/commit transaction for it.

### 14.3 Command catalog (initial)

Identity is always by stable handle (`sid`/`gid`/`nid`), never by row index (§2.6).

| Command | Arguments | Notes |
|---|---|---|
| `set_cell` | sid, period, type, text | single cell |
| `paint_stroke` | sid, periods[], type, bus_seed_text | one brush gesture; BUS continuity rules §6.3 |
| `fill_region` | sids[], period range, type, text | box-select fill |
| `add_signal` | name?, fill? | appends top-level |
| `remove_signals` | sids[] | prunes annotations |
| `rename_signal` / `set_offset` / `set_color` | sid(s), value | value=None clears color |
| `set_periods` | n | pads/truncates cells |
| `create_group` | sids[], name? | →gid |
| `merge_into_group` / `merge_groups` | sids[]/gid, target gid | nest guard §2.6 |
| `move_leaf` / `move_group` | sid/gid, container gid?, index | marker method (§8.3) |
| `remove_from_group` / `dissolve_group` / `delete_group` | sids[] / gid / gid | |
| `set_group_color` / `rename_group` / `toggle_collapsed` | gid, value? | |
| `paste_cells` | at (sid, period), block | auto-adds signals |
| `paste_signals` / `paste_group` / `insert_template` | payload, at | **fresh sids/gids** (§2.6) |
| `add_anchor` / `remove_anchor` | sid, period, edge / nid | |
| `add_edge` / `edit_edge` / `remove_edge` | nid pair, label, style / index | |
| `new_document` / `load_document` | — / dict | load reports pruned annotations |

### 14.4 Change events

The core emits `changed(scope)` after a successful command, with
`scope ∈ {cells, structure, annotations, document}` (`structure` = anything affecting layout:
add/remove/move/group/collapse/periods; `document` = wholesale replacement). The tkinter shell
maps every event to `request_render()`; scopes exist so a future incremental renderer can
repaint only dirty rows, and so non-UI observers (autosave, dirty-flag) can subscribe too.

### 14.5 Undo / redo semantics

Snapshot-based at the command boundary: capture `to_dict()` before applying, push on success.
R5 guarantees gesture-level granularity (one brush stroke / one drag = one undo step).
Transient shell state is never part of a snapshot.

### 14.6 Why this protocol

- **Headless testability** — commands + events are testable without a window (today only
  `Model` is; gestures require a real Tk shell).
- **Undo seam** — R4+R5 make snapshot undo trivial and correct.
- **Second shell** — the §12 web/SVG reimplementation consumes the same catalog unchanged.
- **VCD import & scripting** — an importer is just another command producer.

## 15. Changelog

Versioned to match the `retrowave.py` implementation. Newest first. When adding a feature or
changing behaviour, bump the version in three places — the program string, this spec's header, and
`README.md` — and add a line here.

- **v1.22** — **Package split (internal; no behaviour change).** The single file became the
  `retrowave` package with strict layering: shared base (`theme`, `geometry`), logic unit
  (`model`, `templates`), drawing unit (`elements`, `engine`, `backends`), and the UI shell
  (`app`) — the only module allowed to import tkinter. `__init__` re-exports the public API and
  lazy-loads UI names via PEP 562 so importing the core never pulls in tkinter. The program
  version became single-source (`retrowave.__version__`; window title and About read it).
  Launchers: `python run.py` or `python -m retrowave`. Guarded by
  `tests/test_module_boundaries.py`: a subprocess proves core+drawing imports leave
  `tkinter` out of `sys.modules`; an AST scan forbids tkinter imports outside `app.py`;
  re-export completeness; no hard-coded version strings.
- **v1.21** — **Render coalescing.** All 46 interaction call sites now go through
  `request_render()` (dirty scheduling via `after_idle`): bursts of mutations inside one
  event-loop cycle repaint once instead of once per call, with no change to the drawing code.
  A synchronous `render()` cancels any pending request. Two call sites intentionally stay
  synchronous: the first paint in `__init__` and the EPS export (tk `postscript` snapshots the
  live canvas). See the new "Render scheduling" note at the top of §6. Covered by
  `tests/test_render_coalescing.py` (burst→1 draw, cancel-on-sync, paint-drag equivalence).
- **v1.20** — **Test safety net (internal; no behaviour change).** Added a pytest suite under
  `tests/`: `test_model.py` (48 tests total) covers the signal pool / group tree / annotations /
  persistence-and-migration paths of `Model`, and `test_app_interactions.py` drives the real
  `App` with synthesized mouse events (paint, brush row-lock, BUS preservation, marquee fill,
  pan mode, copy/paste, template insertion). Every mutating test ends by asserting the §2.6
  invariants via a shared `assert_invariants()` helper (sid uniqueness, DFS-leaf-order sync,
  group cache, no empty groups/markers, annotation validity, layout row count). The GUI tests
  share one session-scoped Tk root (repeated create/destroy of Tk in one process trips Tcl's
  `tcl_findLibrary`). Gate: `python -m pytest` must pass before every commit, in addition to the
  `ast.parse` syntax check.
- **v1.19** — **Pan clamping & name-column sync fix.** Pan-mode dragging now moves the view with
  `xview_moveto`/`yview_moveto` (fraction-based, anchored at the press point) instead of
  `scan_mark`/`scan_dragto`. tk's *scan* API ignores the scrollregion, so the canvas could be
  dragged vertically even when the content fit the window, and once the origin left the
  scrollregion the name column's clamped `yview_moveto` no longer matched the wave canvas
  (vertical desync). A new explicit per-axis gate `_scrollable()` (content size vs. visible
  window size) forces an axis to fraction 0 when the content fits — applied to pan drag, the
  mouse wheel, and the scrollbar callback alike — and `render()` snaps the view back to origin
  when content shrinks below the window. The name column is synced from the post-clamp
  y-fraction, keeping the two canvases identical.
- **v1.18** — **Pan mode (tool = none)** to stop accidental painting while navigating: `Escape`
  from any state (tool active and/or box selection) clears the selection, deselects the tool, and
  enters pan mode — no toolbar button, `Escape` is the only entry. In pan mode plain left-drag
  pans the canvas (name column vertically synced, fleur cursor), Shift/Ctrl + left-drag still
  box-selects, plain clicks never paint or start connect-drags; element buttons / number keys
  return to paint mode. (§8.1, §8.1a)
- **v1.17** — Fixed the offset BUS left-edge **closing chevron slope**: a half-swing transition is
  `tw/2` wide (slope `swing/tw`), not `tw`; now matches every other bus edge for both small and
  large offsets (clips at the left border when the chevron starts off-screen).
- **v1.16** — Nested groups **step 2**: name-column drag upgraded from reorder-only to
  reorder / merge-into-group / move-out / nest, resolved by *container + insertion index* (combine
  and reorder in one gesture); focus overlay (dim background, lit target container, insertion line);
  cycle guard; **off-by-one on downward drag fixed** via the marker insert-before-detach technique.
- **v1.15** — Nested groups **step 1**: introduced the **group tree** (arbitrary depth) as the
  structural source of truth with `signals` kept in DFS-leaf order and `signal["group"]` as an
  immediate-parent cache; recursive `layout()` with depth indent and ancestor color cascade; nested
  collapse; create-nesting via right-click; legacy-flat→tree load migration; nested WaveDrom export.
- **v1.14** — Offset BUS left edge changed from parallel rails to a **closing chevron** that meets
  the first cell's opening at a value boundary (slope corrected later in v1.17).
- **v1.13** — Drag reorder (single-level): signal reorder within its group/no-group range and
  group-block reorder, with dim + insertion-line feedback.
- **v1.13** — Delete group (with all members); absolute **group-wide offset**; **WaveDrom JSON**
  export (groups→nested arrays, offset→phase, anchors/edges→node/edge).
- **v1.12** — Fixed export-scale property name clash with the canvas `scale` method (renamed to
  `export_scale`, defensive numeric read); annotations again render on screen.
- **v1.11** — **PNG 1–4× resolution** (true high-density re-render) and **SVG vector export** via a
  dedicated SVG drawing surface (dashed grid preserved); PNG height fixed to use `len(layout())`.
- **v1.10** — Orphan-annotation pruning reported in the status bar on load; relationship-line
  **arrow styles** (double / single / measure) switchable from the edge right-click menu.
- **v1.9**  — Fixed missing `sid` on template-insert / paste (which made anchors attach to the wrong
  signal); clearer arrowheads; connect-drag freeze veil changed to light gray.
- **v1.8**  — **Annotations**: sid-pinned anchors + relationship lines; create via right-click;
  hover highlight; drag-to-connect with freeze overlay; `Delete` to remove.
- **v1.7**  — Phase C: group-level copy/paste and a template library (import templates, insert as a
  group).
- **v1.6**  — Explicit create / merge / move-out / dissolve group actions; group color cascades to
  members.
- **v1.4–1.5** — Single-level groups via a view-layer `layout()`; group merge semantics.
- **v1.3**  — Recolor / offset moved into the right-click menu.
- **v1.2**  — Per-signal color; signal-level copy/paste.
- **v1.1**  — PNG export switched to a bitmap surface (no Ghostscript dependency).
- **v0.1–1.0** — Foundation: element hierarchy, unified slope, joins (`MEET`), box-select,
  copy/paste, per-signal offset with edge extension.

---

*End of specification.*
