# -*- coding: utf-8 -*-
"""UI shell: the only module in the whole package allowed to import tkinter.
Design doc §8/§11; the UI<->Core protocol (R1-R5) in §14 is this module's migration target contract."""
import json
import math
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog

from . import __version__
from .backends import PILCanvas, SVGCanvas, _load_pil_fonts
from .document import Document
from .engine import Engine
from .elements import WAVE_TYPES
from .export import export_png, export_svg, export_wavedrom
from .geometry import Geometry
from .templates import TemplateLibrary
from .theme import Style
from .tutorial import TutorialOverlay, tutorial_enabled

SHIFT_MASK = 0x0001
CTRL_MASK = 0x0004


def make_key_button(parent, text, command, width=None):
    b = tk.Button(parent, text=text, command=command, font=Style.KEY_FONT,
                  bg=Style.FACE, activebackground="#F5F3E7",
                  relief=tk.RAISED, bd=3, padx=8, pady=3, highlightthickness=0)
    if width:
        b.configure(width=width)
    return b


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"RetroWave - Digital Waveform Editor  v{__version__}")
        self.geometry("1160x660"); self.minsize(900, 470)
        self.configure(bg=Style.FACE)
        self.doc = Document(scheduler=self.after_idle)
        self.doc.subscribe(self._on_doc_changed)
        self.geom = Geometry(); self.engine = Engine()
        self.active_tool = "H"; self.tool_btns = {}
        self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
        self.cell_sel = None; self.clip = None; self.clip_signals = None
        self.clip_group = None
        self._clip_kind = None; self._copy_ctx = "cells"
        self._press = None; self._press_xy = (0, 0); self._moved = False
        self._marquee = None; self._selecting = False; self._panning = False
        self._pan_anchor = None
        self._render_job = None                 # pending coalesced redraw (after_idle id)
        self._drag_value = None; self._hover = None
        self._hover_node = None; self._hover_edge = None
        self._connecting = False; self._connect_from = None; self._connect_xy = None
        self._name_press = None; self._name_moved = False; self._dragging = False
        self._drag_kind = None; self._drag_ref = None; self._drop = None; self._drop_target = None
        self.lib = TemplateLibrary()
        self._build_menubar(); self._build_toolbar(); self._build_main()
        self._build_statusbar(); self._bind_keys()
        self._set_tool("H"); self.render()          # first draw must be synchronous so the window is complete on appearance
        self.after(150, self._startup_templates)    # load templates / warn about missing files after the window shows
        self.after(450, self._maybe_show_tutorial)  # show the tutorial on first launch

    def _maybe_show_tutorial(self, force=False):
        """First-launch tutorial: can be disabled by an env var (testing/automation) and user preference; the Help menu can force it open again."""
        if not force:
            if os.environ.get("RETROWAVE_NO_TUTORIAL"):
                return
            if not tutorial_enabled():
                return
        if getattr(self, "_tutorial", None) is not None and self._tutorial.winfo_exists():
            return
        self._tutorial = TutorialOverlay(self, self._tutorial_steps())

    def _tutorial_steps(self):
        toolbar = self.tool_btns["CLK"].master       # the whole element toolbar
        cfg = self.sp_p.master                       # the geometry/period spinbox area
        return [
            (None, "Welcome to RetroWave",
             "This is a retro-style digital timing / waveform editor.\n"
             "The next few steps walk you through the main operations - the highlighted area "
             "is what you can act on right now, so feel free to try it directly.\n\n"
             "(Press Esc or \"Skip\" any time to end the tutorial.)"),
            (toolbar, "Element Toolbar",
             "Pick an element (or press number keys 1-6): CLK clock, H high level, L low level, "
             "BUS data bus, HiZ high impedance, Unknown.\n"
             "\"+ Signal\" adds a new signal row. Once an element is selected you can draw "
             "waveforms on the canvas to the right."),
            (self.wave_cv, "Waveform Canvas",
             "Click a cell to draw it; press and drag to brush along the same row (row-locked, no slips).\n"
             "Click a BUS cell again to enter its data value.\n"
             "Shift/Ctrl + drag = box-select (press an element key to fill the block, Ctrl+C/V to copy and paste).\n"
             "Right-click to create an anchor; drag from one anchor to another to draw a measurement / relationship line."),
            (self.name_cv, "Signal Name Column",
             "Select signals (Ctrl/Shift for multi-select); right-click menu: color, offset, create group, rename, delete.\n"
             "Press and drag a name up/down to reorder; drag into a group = merge in, drag to the empty space at the bottom = move out of the group.\n"
             "Click a group header to collapse/expand the whole group."),
            (cfg, "Geometry and Periods",
             "Adjust cell width, row height, transition slope ratio and period count - the view updates instantly.\n"
             "These are view settings and are saved together with the project JSON."),
            (None, "A Few Last Tricks",
             "Esc = pan mode (left-drag pans the canvas, no accidental drawing).\n"
             "Ctrl+Z / Ctrl+Y = undo / redo (last 5 steps, one gesture counts as one step).\n"
             "The File menu lets you save (JSON) and export PNG/SVG/EPS and WaveDrom.\n"
             "To see the tutorial again later: Help -> Interactive tutorial."),
        ]

    @property
    def model(self):
        """CQRS read path: read-only pass-through for rendering/layout/hit-testing; any write goes through self.doc commands."""
        return self.doc.model

    def _on_doc_changed(self, scopes):
        """Document change event -> redraw (coalesced scheduling)."""
        self.request_render()

    def _build_menubar(self):
        bar = tk.Frame(self, bg=Style.FACE, bd=1, relief=tk.RAISED); bar.pack(side=tk.TOP, fill=tk.X)
        fmb = tk.Menubutton(bar, text="File", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        fm = tk.Menu(fmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        fm.add_command(label="New\tCtrl+N", command=self.do_new)
        fm.add_command(label="Load...\tCtrl+O", command=self.do_open)
        fm.add_command(label="Save...\tCtrl+S", command=self.do_save)
        fm.add_separator()
        fm.add_command(label="Import Template...", command=self._import_template)
        fm.add_separator()
        fm.add_command(label="Export Image...\tCtrl+E", command=self.do_export)
        fm.add_command(label="Export WaveDrom JSON...", command=self.do_export_wavedrom)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.destroy)
        fmb.configure(menu=fm); fmb.pack(side=tk.LEFT)

        tmb = tk.Menubutton(bar, text="Template", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        self.tmpl_menu = tk.Menu(tmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        tmb.configure(menu=self.tmpl_menu); tmb.pack(side=tk.LEFT)
        self._rebuild_template_menu()
        hmb = tk.Menubutton(bar, text="Help", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        hm = tk.Menu(hmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        hm.add_command(label="Interactive tutorial", command=lambda: self._maybe_show_tutorial(force=True))
        hm.add_command(label="Usage", command=self.help_usage)
        hm.add_command(label="Shortcuts", command=self.help_keys)
        hm.add_separator()
        hm.add_command(label="About RetroWave", command=self.help_about)
        hmb.configure(menu=hm); hmb.pack(side=tk.LEFT)

    # ---- Template library ----
    def _rebuild_template_menu(self):
        m = self.tmpl_menu
        m.delete(0, "end")
        if self.lib.entries:
            for e in self.lib.entries:
                m.add_command(label=e["name"], command=lambda en=e: self._insert_template(en))
            m.add_separator()
            rem = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            for e in self.lib.entries:
                rem.add_command(label=e["name"], command=lambda en=e: self._remove_template(en["name"]))
            self._tmpl_rem = rem               # keep a reference so it isn't garbage-collected
            m.add_cascade(label="Remove Template", menu=rem)
        else:
            m.add_command(label="(No templates yet)", state="disabled")
        m.add_separator()
        m.add_command(label="Import Template...", command=self._import_template)
        m.add_command(label="Save Current Canvas as Template...", command=self._save_as_template)

    def _startup_templates(self):
        avail, missing = self.lib.load()
        self._rebuild_template_menu()
        if missing:
            lines = "\n".join(f"- {m['name']}    ({m.get('path') or 'unknown path'})" for m in missing)
            messagebox.showwarning(
                "Template Loading", f"The following template files could not be found and were removed from the list:\n\n{lines}")

    def _import_template(self):
        path = filedialog.askopenfilename(
            title="Import Template (JSON)", filetypes=[("Waveform JSON", "*.json"), ("All Files", "*.*")])
        if not path:
            return
        try:
            d = TemplateLibrary.read(path)
            if not isinstance(d, dict) or "signals" not in d:
                raise ValueError("Not a valid waveform JSON (missing signals field)")
        except Exception as ex:
            messagebox.showerror("Import Template Failed", str(ex)); return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("Import Template", "Template name:", initialvalue=default, parent=self)
        if not name:
            return
        self.lib.add(name, path); self._rebuild_template_menu()
        messagebox.showinfo("Import Template",
                            f"Template \"{name}\" added.\n(This template loads automatically every time "
                            f"the tool opens; pick it from the Template menu to insert it as a group.)")

    def _save_as_template(self):
        path = filedialog.asksaveasfilename(
            title="Save Current Canvas as Template", defaultextension=".json",
            initialdir=TemplateLibrary.DIR, filetypes=[("Waveform JSON", "*.json")])
        if not path:
            return
        data = self.model.to_dict(); data["view"] = self.geom.to_dict()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            messagebox.showerror("Save as Template Failed", str(ex)); return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("Save as Template", "Template name:", initialvalue=default, parent=self)
        if not name:
            return
        self.lib.add(name, path); self._rebuild_template_menu()
        messagebox.showinfo("Template", f"Saved as template \"{name}\".")

    def _remove_template(self, name):
        self.lib.remove(name); self._rebuild_template_menu()
        self.status.configure(text=f" Removed \"{name}\" from the template library (the original file is unaffected)")

    def _insert_template(self, entry):
        try:
            tsignals = TemplateLibrary.read(entry["path"]).get("signals", [])
        except Exception as ex:
            messagebox.showerror("Insert Template Failed",
                                 f"Read failed; the file may have been moved or deleted.\n{entry.get('path')}\n\n{ex}")
            return
        if not tsignals:
            messagebox.showwarning("Insert Template", "This template has no signals."); return
        gname, newidx = self.doc.insert_template(entry["name"], tsignals)
        self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
        self.request_render()
        self.status.configure(text=f" Inserted template \"{gname}\" ({len(newidx)} signals, grouped)")

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=Style.FACE, bd=1, relief=tk.RAISED); tb.pack(side=tk.TOP, fill=tk.X)
        cfg = tk.Frame(tb, bg=Style.FACE); cfg.pack(side=tk.RIGHT, padx=6, pady=4)
        self.sp_w = self._spin(cfg, "Width", 30, 240, 4, self.geom.period_w, self._apply_geom)
        self.sp_h = self._spin(cfg, "Row H", 36, 160, 4, self.geom.row_h, self._apply_geom)
        self.sp_r = self._spin(cfg, "Slope%", 5, 45, 1, int(self.geom.ramp_ratio * 100), self._apply_geom)
        self.sp_p = self._spin(cfg, "Periods", 1, 256, 1, self.model.n_periods, self._apply_periods)

        tk.Label(tb, text="Element:", bg=Style.FACE, font=Style.UI_FONT).pack(side=tk.LEFT, padx=(6, 2), pady=6)
        for t in WAVE_TYPES:
            b = make_key_button(tb, t, lambda x=t: self._set_tool(x))
            b.pack(side=tk.LEFT, padx=2, pady=6); self.tool_btns[t] = b
        tk.Frame(tb, width=2, bg=Style.FACE_DARK).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=8)
        make_key_button(tb, "+ Signal", self.add_signal).pack(side=tk.LEFT, padx=2, pady=6)
        tk.Label(tb, text="(right-click a signal for actions)", bg=Style.FACE,
                 font=Style.UI_FONT, fg="#777").pack(side=tk.LEFT, padx=(8, 2), pady=6)

    def _spin(self, parent, label, lo, hi, step, val, cmd):
        tk.Label(parent, text=label, bg=Style.FACE, font=Style.UI_FONT).pack(side=tk.LEFT, padx=(6, 1))
        sp = tk.Spinbox(parent, from_=lo, to=hi, increment=step, width=5, font=Style.UI_FONT,
                        command=cmd, relief=tk.SUNKEN, bd=2)
        sp.delete(0, tk.END); sp.insert(0, str(val))
        sp.bind("<Return>", lambda e: (cmd(), self.wave_cv.focus_set()))
        sp.bind("<FocusOut>", lambda e: cmd())
        sp.bind("<Escape>", lambda e: self.wave_cv.focus_set())
        sp.pack(side=tk.LEFT)
        return sp

    def _apply_geom(self):
        try:
            self.geom.period_w = max(20, int(float(self.sp_w.get())))
            self.geom.row_h = max(30, int(float(self.sp_h.get())))
            self.geom.ramp_ratio = max(0.02, min(0.45, float(self.sp_r.get()) / 100.0))
        except ValueError:
            return
        self.request_render()

    def _apply_periods(self):
        try:
            n = max(1, int(float(self.sp_p.get())))
        except ValueError:
            return
        if self.doc.set_n_periods(n):
            self.cell_sel = None
        self.request_render()

    def set_offset_dialog(self):
        if not self.model.signals:
            return
        cur = self.model.signals[self.selected].get("offset", 0.0)
        v = simpledialog.askfloat("Set Offset", "Offset (0 ~ 0.95 of a period):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        self.doc.set_offset(sorted(self.sig_sel or {self.selected}), v)
        self.request_render()

    def _refresh_offset_field(self):
        pass            # offset moved to the right-click menu; no persistent field

    def _build_main(self):
        main = tk.Frame(self, bg=Style.FACE_DARK, bd=2, relief=tk.SUNKEN)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=3, pady=3)
        main.columnconfigure(1, weight=1); main.rowconfigure(0, weight=1)
        self.name_cv = tk.Canvas(main, width=self.geom.name_w, bg=Style.CANVAS_BG, highlightthickness=0)
        self.name_cv.grid(row=0, column=0, sticky="ns")
        self.wave_cv = tk.Canvas(main, bg=Style.CANVAS_BG, highlightthickness=0, takefocus=1)
        self.wave_cv.grid(row=0, column=1, sticky="nsew")
        vbar = tk.Scrollbar(main, orient=tk.VERTICAL, command=self._yview); vbar.grid(row=0, column=2, sticky="ns")
        hbar = tk.Scrollbar(main, orient=tk.HORIZONTAL, command=self.wave_cv.xview); hbar.grid(row=1, column=1, sticky="ew")
        self.wave_cv.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.wave_cv.bind("<Button-1>", self.on_press)
        self.wave_cv.bind("<B1-Motion>", self.on_motion)
        self.wave_cv.bind("<ButtonRelease-1>", self.on_release)
        self.wave_cv.bind("<Button-3>", self.on_wave_menu)
        self.wave_cv.bind("<Motion>", self.on_hover)
        self.name_cv.bind("<Button-1>", self.on_name_press)
        self.name_cv.bind("<B1-Motion>", self.on_name_drag)
        self.name_cv.bind("<ButtonRelease-1>", self.on_name_release)
        self.name_cv.bind("<Double-Button-1>", self.on_name_rename)
        self.name_cv.bind("<Button-3>", self.on_name_menu)
        for cv in (self.wave_cv, self.name_cv):
            cv.bind("<MouseWheel>", self._on_wheel)
            cv.bind("<Button-4>", self._on_wheel); cv.bind("<Button-5>", self._on_wheel)

    def _build_statusbar(self):
        self.status = tk.Label(self, text="", bg=Style.FACE, anchor="w",
                               font=Style.UI_FONT, bd=1, relief=tk.SUNKEN)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _is_typing(self):
        return isinstance(self.focus_get(), (tk.Entry, tk.Spinbox))

    def _bind_keys(self):
        self.bind("<Control-n>", lambda e: self.do_new())
        self.bind("<Control-o>", lambda e: self.do_open())
        self.bind("<Control-s>", lambda e: self.do_save())
        self.bind("<Control-e>", lambda e: self.do_export())
        self.bind("<Control-c>", lambda e: self.do_copy())
        self.bind("<Control-v>", lambda e: self.do_paste())
        self.bind("<Escape>", lambda e: self._enter_pan_mode())
        self.bind("<Delete>", lambda e: self._del_hovered_annot())
        self.bind("<Control-z>", lambda e: self.do_undo())
        self.bind("<Control-y>", lambda e: self.do_redo())

        def keyed(fn):
            def handler(e):
                if self._is_typing():
                    return
                fn()
            return handler
        for i, t in enumerate(WAVE_TYPES, start=1):
            self.bind(str(i), keyed(lambda x=t: self._set_tool(x)))

    def _scrollable(self):
        """Return (horizontally scrollable, vertically scrollable): when content size does not exceed the visible window area, panning/scrolling on that axis is disabled."""
        sr = self.wave_cv.cget("scrollregion").split()
        if len(sr) != 4:
            return (False, False)
        cw = float(sr[2]) - float(sr[0]); ch = float(sr[3]) - float(sr[1])
        return (cw > self.wave_cv.winfo_width(), ch > self.wave_cv.winfo_height())

    def _yview(self, *a):
        if not self._scrollable()[1]:
            self.wave_cv.yview_moveto(0.0); self.name_cv.yview_moveto(0.0); return
        self.wave_cv.yview(*a); self.name_cv.yview(*a)

    def _on_wheel(self, e):
        if not self._scrollable()[1]:
            return
        d = -1 if (getattr(e, "delta", 0) > 0 or e.num == 4) else 1
        self.wave_cv.yview_scroll(d, "units"); self.name_cv.yview_scroll(d, "units")

    # ---- Tools ----
    def _set_tool(self, t):
        if self.cell_sel is not None:          # box-select active -> fill that range
            self._fill_selection(t); return
        self.active_tool = t; self._refresh_tools()
        self.wave_cv.configure(cursor="")
        self.request_render()

    def _enter_pan_mode(self):
        """Esc: from any state, fall back to canvas pan mode (clear box-select, deselect element)."""
        self.cell_sel = None
        self.active_tool = None; self._refresh_tools()
        self.wave_cv.configure(cursor="fleur")
        self.request_render()

    def _refresh_tools(self):
        for k, b in self.tool_btns.items():
            on = (k == self.active_tool)
            b.configure(relief=tk.SUNKEN if on else tk.RAISED, bg="#DAD7C2" if on else Style.FACE)

    def _clear_cell_sel(self):
        if self.cell_sel is not None:
            self.cell_sel = None; self.request_render()

    def _fill_rect(self, sel, t):
        s0, s1, p0, p1 = sel
        if t == "BUS":
            txt = simpledialog.askstring("Fill BUS", "Data value for this range:", parent=self)
            if txt is None:
                return None
            payload = ("BUS", txt)
        elif t == "Unknown":
            payload = ("Unknown", "")
        else:
            payload = (t, "")
        self.doc.begin()                        # one fill = one undo unit
        for s in range(s0, s1 + 1):
            for p in range(p0, p1 + 1):
                self.doc.set_cell(s, p, payload[0], payload[1])
        self.doc.commit()
        return f"Filled {payload[0]}" + (f" = '{payload[1]}'" if payload[0] == "BUS" else "")

    def _fill_selection(self, t):
        if self.cell_sel is None:
            return
        msg = self._fill_rect(self.cell_sel, t)
        if msg:
            self.request_render(); self.status.configure(text=" " + msg + " (selection kept, Esc to clear)")

    def _update_status(self):
        if self.active_tool is None:
            self.status.configure(
                text=f" Pan mode | Left-drag = pan canvas | Shift/Ctrl+left-drag = box-select "
                     f"| Click an element button or number key to draw | Periods {self.model.n_periods}")
            return
        if self.active_tool == "BUS":
            hint = "Click/drag = draw BUS (existing BUS kept, non-BUS replaced); click same cell again = edit value"
        else:
            hint = "Click/drag to paint (row-locked)"
        self.status.configure(
            text=f" Brush: {self.active_tool} | {hint} | Shift/Ctrl drag = box-select (press element key to fill / Ctrl+C to copy) "
                 f"| Name Ctrl/Shift multi-select -> right-click: color/offset/delete | Esc = pan mode | Periods {self.model.n_periods}")

    def request_render(self):
        """Coalesced redraw: multiple requests within the same event-loop cycle redraw only once at idle.
        Interactive code always calls this method; only code that "then needs to read canvas content
        synchronously" (e.g. the postscript snapshot for EPS export, the first draw in __init__) calls render() directly."""
        if self._render_job is None:
            self._render_job = self.after_idle(self._render_now)

    def _render_now(self):
        self._render_job = None
        self.render()

    def render(self):
        if self._render_job is not None:        # synchronous redraw -> cancel a pending coalesced request
            self.after_cancel(self._render_job); self._render_job = None
        self.name_cv.configure(width=self.geom.name_w)
        self.engine.draw(self.name_cv, self.wave_cv, self.model, self.sig_sel, self.geom, self.cell_sel)
        # when content shrinks back within the window (deleting rows / collapsing groups, etc.), pull that axis back to origin and keep the name column in sync
        h_ok, v_ok = self._scrollable()
        if not v_ok:
            self.wave_cv.yview_moveto(0.0); self.name_cv.yview_moveto(0.0)
        if not h_ok:
            self.wave_cv.xview_moveto(0.0)
        self._draw_annot_overlay()
        self._draw_drag_overlay()
        self._update_status()

    # ---- Annotations: coordinates / hit-testing / overlay ----
    def _node_screen_positions(self):
        rows = self.model.layout()
        sig_row = {row.ref: r for r, row in enumerate(rows) if row.kind == "sig"}
        sid2idx = {s.get("sid"): i for i, s in enumerate(self.model.signals)}
        return self.engine.node_positions(self.model, self.geom, sig_row, sid2idx)

    def _node_at_xy(self, cx, cy, rad=8):
        best, bd = None, rad
        for nid, (x, y) in self._node_screen_positions().items():
            d = math.hypot(cx - x, cy - y)
            if d <= bd:
                bd = d; best = nid
        return best

    @staticmethod
    def _pt_seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def _edge_at_xy(self, cx, cy, tol=6):
        pos = self._node_screen_positions()
        for i, ed in enumerate(self.model.edges):
            a, b = pos.get(ed["frm"]), pos.get(ed["to"])
            if a and b and self._pt_seg_dist(cx, cy, a[0], a[1], b[0], b[1]) <= tol:
                return i
        return None

    def _draw_annot_overlay(self):
        pos = self._node_screen_positions()
        if self._connecting:
            PW = self.geom.period_w
            max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
            w = self.model.n_periods * PW + max_off * PW + 4
            h = self.geom.header_h + len(self.model.layout()) * self.geom.row_h
            self.wave_cv.create_rectangle(0, 0, w, h, fill="#C2C2C2", stipple="gray50", outline="")
            for nid, xy in pos.items():
                self.engine.draw_node(self.wave_cv, nid, xy, hot=(nid == self._hover_node))
            if self._connect_from in pos and self._connect_xy:
                x0, y0 = pos[self._connect_from]; x1, y1 = self._connect_xy
                self.wave_cv.create_line(x0, y0, x1, y1, fill=Style.MARQUEE, width=2, dash=(5, 3))
                self.engine.draw_node(self.wave_cv, self._connect_from, pos[self._connect_from], hot=True)
        elif self._hover_node and self._hover_node in pos:
            self.engine.draw_node(self.wave_cv, self._hover_node, pos[self._hover_node], hot=True)
        elif self._hover_edge is not None and 0 <= self._hover_edge < len(self.model.edges):
            ed = self.model.edges[self._hover_edge]
            a, b = pos.get(ed["frm"]), pos.get(ed["to"])
            if a and b:
                self.engine.draw_edge(self.wave_cv, a, b, ed.get("label", ""),
                                      hot=True, style=ed.get("style", "double"))

    # ---- Coordinates <-> cells (use layout to map visible rows to signal indices) ----
    def _resolve_row(self, cy):
        if cy < self.geom.header_h:
            return None
        rows = self.model.layout()
        r = int((cy - self.geom.header_h) // self.geom.row_h)
        return rows[r] if 0 <= r < len(rows) else None

    @staticmethod
    def _nearest_sig(rows, r):
        for d in range(len(rows)):
            for rr in (r - d, r + d):
                if 0 <= rr < len(rows) and rows[rr][0] == "sig":
                    return rows[rr][1]
        return None

    def _cell_from_xy(self, cx, cy, clamp=False):
        npd = self.model.n_periods
        rows = self.model.layout()
        if not self.model.signals or npd == 0 or not rows:
            return None
        r = int((cy - self.geom.header_h) // self.geom.row_h)
        if clamp:
            r = max(0, min(len(rows) - 1, r))
        elif cy < self.geom.header_h or not (0 <= r < len(rows)):
            return None
        kind, ref = rows[r].kind, rows[r].ref
        if kind == "sig":
            si = ref
        elif clamp:
            si = self._nearest_sig(rows, r)
            if si is None:
                return None
        else:
            return None
        ox = self.model.signals[si].get("offset", 0.0) * self.geom.period_w
        p = int((cx - ox) // self.geom.period_w)
        if clamp:
            p = max(0, min(npd - 1, p)); return (si, p)
        if 0 <= p < npd:
            return (si, p)
        return None

    def _ev_xy(self, e):
        return self.wave_cv.canvasx(e.x), self.wave_cv.canvasy(e.y)

    # ---- Mouse ----
    def on_hover(self, e):
        cx, cy = self._ev_xy(e)
        self._hover = self._cell_from_xy(cx, cy)
        hv = self._node_at_xy(cx, cy)
        he = self._edge_at_xy(cx, cy) if hv is None else None
        if hv != self._hover_node or he != self._hover_edge:
            self._hover_node = hv; self._hover_edge = he
            self.request_render()

    def on_press(self, e):
        self.wave_cv.focus_set()
        cx, cy = self._ev_xy(e)
        self._press_xy = (cx, cy)
        ctrl = bool(e.state & CTRL_MASK); shift = bool(e.state & SHIFT_MASK)
        nid = self._node_at_xy(cx, cy) if not (ctrl or shift) else None
        if nid:                                   # drag a line from an anchor (enter frozen state); works in both draw and pan mode
            self._connecting = True; self._connect_from = nid
            self._connect_xy = (cx, cy); self._press = None
            self._selecting = False; self._moved = False
            self.request_render(); return
        if self.active_tool is None and not (ctrl or shift):   # pan mode: left button = pan canvas
            self._panning = True
            self._pan_anchor = (e.x, e.y, self.wave_cv.xview()[0], self.wave_cv.yview()[0])
            self._press = None; self._selecting = False; self._moved = False
            return
        self._press = self._cell_from_xy(cx, cy)
        self._moved = False
        self._selecting = ctrl or shift          # Shift/Ctrl drag is always pure box-select
        if self._press:
            self.selected = self._press[0]
        self._drag_value = None
        if self._press and not self._selecting and self.active_tool is not None:
            self.doc.begin()                     # one brush gesture = one undo unit
        if (not self._selecting) and self._press and self.active_tool == "BUS":
            cells = self.model.signals[self._press[0]]["cells"]; p = self._press[1]
            if cells[p]["type"] == "BUS":
                self._drag_value = cells[p]["text"]
            elif p > 0 and cells[p - 1]["type"] == "BUS":
                self._drag_value = cells[p - 1]["text"]
            else:
                self._drag_value = ""
        self._erase_marquee()
        if self.cell_sel is not None:
            self.cell_sel = None; self.request_render()

    def on_motion(self, e):
        if self._panning:
            # pan via xview/yview_moveto, and per _scrollable() explicitly disable axes whose content
            # does not exceed the window (instead of scan_dragto: scan is not bound by scrollregion,
            # which would let content shorter than the window still drag vertically, and after dragging
            # out of range the name column's yview would lose sync).
            ax, ay, fx, fy = self._pan_anchor
            sr = self.wave_cv.cget("scrollregion").split()
            sw = max(float(sr[2]) - float(sr[0]), 1.0)
            sh = max(float(sr[3]) - float(sr[1]), 1.0)
            h_ok, v_ok = self._scrollable()
            self.wave_cv.xview_moveto(fx + (ax - e.x) / sw if h_ok else 0.0)
            self.wave_cv.yview_moveto(fy + (ay - e.y) / sh if v_ok else 0.0)
            self.name_cv.yview_moveto(self.wave_cv.yview()[0])   # sync the name column using the actual clamped value
            return
        cx, cy = self._ev_xy(e)
        if self._connecting:
            self._connect_xy = (cx, cy)
            hv = self._node_at_xy(cx, cy)
            self._hover_node = hv if hv != self._connect_from else None
            self.request_render(); return
        if self._selecting:
            self._moved = True
            self._draw_marquee(self._press_xy, (cx, cy))
        elif self._press:
            self._moved = True
            s = self._press[0]
            ox = self.model.signals[s].get("offset", 0.0) * self.geom.period_w
            p_cur = max(0, min(self.model.n_periods - 1, int((cx - ox) // self.geom.period_w)))
            p0, p1 = sorted((self._press[1], p_cur))
            for p in range(p0, p1 + 1):
                self._paint_cell(s, p, self.active_tool, self._drag_value)
            self.request_render()

    def on_release(self, e):
        if self._panning:
            self._panning = False; self._pan_anchor = None
            return
        cx, cy = self._ev_xy(e)
        if self._connecting:
            target = self._node_at_xy(cx, cy)
            frm = self._connect_from
            self._connecting = False; self._connect_from = None; self._connect_xy = None
            self._hover_node = None
            if target and target != frm:
                label = simpledialog.askstring("Relationship Line", "Label (optional, e.g. t_su):", parent=self) or ""
                self.doc.add_edge(frm, target, label)
                self.status.configure(text=f" Created relationship line {frm} -> {target}")
            self.request_render(); return
        if self._selecting:
            a = self._cell_from_xy(*self._press_xy, clamp=True)
            b = self._cell_from_xy(cx, cy, clamp=True)
            if a and b:
                s0, s1 = sorted((a[0], b[0])); p0, p1 = sorted((a[1], b[1]))
                self.cell_sel = (s0, s1, p0, p1)
                self._copy_ctx = "cells"
            self._erase_marquee(); self.request_render()
            if self.cell_sel:
                self.status.configure(text=" Box-selected; press an element key to fill, or Ctrl+C to copy")
        else:
            if not self._moved and self._press:
                self._click_cell(*self._press)
            self.doc.commit()                    # finalize the brush gesture (no change means nothing is pushed to the undo stack)
            self.request_render()

    def on_wave_menu(self, e):
        cx, cy = self._ev_xy(e)
        m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        nid = self._node_at_xy(cx, cy)
        if nid:
            m.add_command(label=f"Delete anchor {nid}", command=lambda: self._del_node(nid))
        else:
            ei = self._edge_at_xy(cx, cy)
            if ei is not None:
                m.add_command(label="Edit label...", command=lambda: self._edit_edge(ei))
                sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
                cur = self.model.edges[ei].get("style", "double")
                for sty, lab in (("double", "Double arrow (measurement)"),
                                 ("single", "Single arrow (causal)"),
                                 ("measure", "No arrow (measurement line)")):
                    mark = "* " if sty == cur else "o "
                    sub.add_command(label=mark + lab, command=lambda s=sty: self._set_edge_style(ei, s))
                m.add_cascade(label="Arrow style", menu=sub)
                m.add_command(label="Delete relationship line", command=lambda: self._del_edge(ei))
            else:
                c = self._cell_from_xy(cx, cy)
                if not c:
                    return
                m.add_command(label="Create anchor here", command=lambda: self._add_node_at(cx, cy))
                m.add_separator()
                m.add_command(label="Clear to L",
                              command=lambda cc=c: (self.doc.set_cell(cc[0], cc[1], "L"), self.request_render()))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _cell_edge_from_xy(self, cx, cy):
        c = self._cell_from_xy(cx, cy)
        if not c:
            return None
        si, p = c
        ox = self.model.signals[si].get("offset", 0.0) * self.geom.period_w
        frac = ((cx - ox) / self.geom.period_w) - p
        edge = "start" if frac < 0.34 else ("end" if frac > 0.66 else "mid")
        return (si, p, edge)

    def _add_node_at(self, cx, cy):
        ce = self._cell_edge_from_xy(cx, cy)
        if not ce:
            return
        si, p, edge = ce
        nid = self.doc.add_anchor(self.model.signals[si].get("sid"), p, edge)
        self.request_render(); self.status.configure(text=f" Created anchor {nid} (drag an anchor to draw a relationship line; Del to delete)")

    def _del_node(self, nid):
        self.doc.remove_anchor(nid)
        if self._hover_node == nid:
            self._hover_node = None
        self.request_render(); self.status.configure(text=f" Deleted anchor {nid}")

    def _edit_edge(self, i):
        if 0 <= i < len(self.model.edges):
            cur = self.model.edges[i].get("label", "")
            new = simpledialog.askstring("Relationship Line Label", "Label:", initialvalue=cur, parent=self)
            if new is not None:
                self.doc.set_edge_label(i, new); self.request_render()

    def _del_edge(self, i):
        if self.doc.remove_edge(i):
            self._hover_edge = None
            self.request_render(); self.status.configure(text=" Deleted relationship line")

    def _set_edge_style(self, i, style):
        if self.doc.set_edge_style(i, style):
            self.request_render()
            self.status.configure(text=f" Relationship line style: { {'double':'double arrow','single':'single arrow (causal)','measure':'no-arrow measurement'}[style] }")

    def _del_hovered_annot(self):
        if self._is_typing():
            return
        if self._hover_node:
            self._del_node(self._hover_node)
        elif self._hover_edge is not None:
            self._del_edge(self._hover_edge)

    def _paint_cell(self, s, p, t, drag_value=None):
        cells = self.model.signals[s]["cells"]
        if t == "BUS":
            if cells[p]["type"] == "BUS":           # already BUS -> keep it continuing, don't overwrite
                return
            if drag_value is not None:
                text = drag_value
            else:
                text = cells[p - 1]["text"] if (p > 0 and cells[p - 1]["type"] == "BUS") else ""
            self.doc.set_cell(s, p, "BUS", text)
        elif t == "Unknown":
            self.doc.set_cell(s, p, "Unknown", "")
        else:
            self.doc.set_cell(s, p, t)

    def _click_cell(self, s, p):
        t = self.active_tool
        if t is None:                                    # pan mode does not draw
            return
        cells = self.model.signals[s]["cells"]
        if t == "BUS" and cells[p]["type"] == "BUS":     # already BUS -> edit value
            cur = cells[p].get("text", "")
            new = simpledialog.askstring("BUS Data", "Enter data value:", initialvalue=cur, parent=self)
            if new is not None:
                self.doc.set_cell(s, p, "BUS", new)
        else:
            self._paint_cell(s, p, t, self._drag_value)

    # ---- Copy / paste (waveform-level + signal-level) ----
    @staticmethod
    def _copy_signal(sig):
        return {"name": sig["name"], "offset": sig.get("offset", 0.0),
                "color": sig.get("color"),
                "cells": [{"type": c["type"], "text": c.get("text", "")} for c in sig["cells"]]}

    def do_copy(self):
        if self._copy_ctx == "signals" and self.sig_sel:
            idxs = sorted(i for i in self.sig_sel if 0 <= i < len(self.model.signals))
            if not idxs:
                return
            self.clip_signals = [self._copy_signal(self.model.signals[i]) for i in idxs]
            self._clip_kind = "signals"
            self.status.configure(text=f" Copied {len(idxs)} signals; Ctrl+V pastes after the selected row")
        elif self.cell_sel is not None:
            s0, s1, p0, p1 = self.cell_sel
            self.clip = [[{"type": self.model.signals[s]["cells"][p]["type"],
                           "text": self.model.signals[s]["cells"][p].get("text", "")}
                          for p in range(p0, p1 + 1)] for s in range(s0, s1 + 1)]
            self._clip_kind = "cells"
            self.status.configure(text=f" Copied {s1-s0+1}x{p1-p0+1} waveform; move to the target cell and Ctrl+V to paste")

    def do_paste(self):
        if self._clip_kind == "group" and self.clip_group:
            self._paste_group(); return
        if self._clip_kind == "signals" and self.clip_signals:
            newidx = self.doc.paste_signals(self.clip_signals, self.selected)
            if not newidx:
                return
            self.selected = newidx[0]
            self.sig_sel = set(newidx); self._sig_anchor = newidx[0]
            self._refresh_offset_field(); self.request_render()
            self.status.configure(text=f" Pasted {len(self.clip_signals)} signals (copies are ungrouped)")
        elif self._clip_kind == "cells" and self.clip:
            s0, p0 = self._hover or (self.selected, 0)
            self.doc.begin()                     # one paste = one undo unit
            while len(self.model.signals) < s0 + len(self.clip):
                self.doc.add_signal()
            for ds, row in enumerate(self.clip):
                for dp, c in enumerate(row):
                    self.doc.set_cell(s0 + ds, p0 + dp, c["type"], c.get("text", ""))
            self.doc.commit()
            self.request_render(); self.status.configure(text=f" Pasted waveform at signal {s0} T{p0}")

    # ---- Color ----
    def pick_color(self):
        if not self.model.signals:
            return
        init = self.model.signals[self.selected].get("color") or Style.WAVE
        try:
            _, hx = colorchooser.askcolor(color=init, parent=self, title="Signal Color")
        except Exception:
            hx = None
        if hx:
            self.doc.set_color(sorted(self.sig_sel or {self.selected}), hx)
            self.request_render()

    def clear_color(self):
        self.doc.set_color(sorted(self.sig_sel or {self.selected}), None)
        self.request_render()

    # ---- marquee ----
    def _draw_marquee(self, xy0, xy1):
        self._erase_marquee()
        x0, y0 = xy0; x1, y1 = xy1
        self._marquee = self.wave_cv.create_rectangle(
            x0, y0, x1, y1, outline=Style.MARQUEE, dash=(3, 2), width=1,
            fill=Style.MARQUEE_FILL, stipple="gray12")

    def _erase_marquee(self):
        if self._marquee:
            self.wave_cv.delete(self._marquee); self._marquee = None

    # ---- Name column (click to select / drag to reorder) ----
    def on_name_press(self, e):
        self.name_cv.focus_set()
        cy = self.name_cv.canvasy(e.y)
        self._name_press = (self._resolve_row(cy), e.x, cy)
        self._name_moved = False; self._dragging = False
        self._drag_kind = None; self._drag_ref = None
        self._drop = None; self._drop_target = None

    def on_name_drag(self, e):
        if self._name_press is None:
            return
        item, _px, py = self._name_press
        cy = self.name_cv.canvasy(e.y)
        if not self._dragging:
            if item is None or abs(cy - py) < self.geom.row_h / 2:   # threshold = half a row height
                return
            self._dragging = True
            self._drag_kind = "group" if item[0] == "group" else "sig"
            self._drag_ref = item[1]
        self._compute_drop(cy)
        self.request_render()

    def on_name_release(self, e):
        if self._dragging:
            tgt = self._drop_target
            if tgt is not None and tgt.get("valid"):
                if self._drag_kind == "sig":
                    sid = self.model.signals[self._drag_ref]["sid"]
                    self.doc.move_leaf_to(sid, tgt["container"], tgt["index"])
                    self.sig_sel = {i for i, s in enumerate(self.model.signals) if s["sid"] == sid}
                    self.selected = next(iter(self.sig_sel), self.selected)
                    self._sig_anchor = self.selected
                    self.status.configure(text=" Moved signal" +
                                          (" (merged into group)" if tgt["container"] else " (moved to top level)"))
                else:
                    self.doc.move_group_to(self._drag_ref, tgt["container"], tgt["index"])
                    self.status.configure(text=" Moved group" +
                                          (" (nested as a subgroup)" if tgt["container"] else " (top level)"))
            self._dragging = False; self._drop = None; self._drop_target = None
            self._name_press = None
            self._refresh_offset_field(); self.request_render()
        else:
            self._name_press = None
            self._name_click(e)

    def _name_click(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":              # clicking a group header = collapse/expand
            self._toggle_group(item[1]); return
        s = item[1]
        ctrl = bool(e.state & CTRL_MASK); shift = bool(e.state & SHIFT_MASK)
        if ctrl:
            if s in self.sig_sel:
                self.sig_sel.discard(s)
            else:
                self.sig_sel.add(s)
            self.selected = s; self._sig_anchor = s
        elif shift and self._sig_anchor is not None:
            a, b = sorted((self._sig_anchor, s))
            self.sig_sel = set(range(a, b + 1)); self.selected = s
        else:
            self.sig_sel = {s}; self.selected = s; self._sig_anchor = s
        if not self.sig_sel:
            self.sig_sel = {s}
        self._copy_ctx = "signals"
        self._refresh_offset_field(); self.request_render()

    # ---- Drop-point resolution (container + insert index), container highlight, insertion line ----
    def _group_visible_span(self, rows, gid):
        r0 = next((r for r, row in enumerate(rows)
                   if row.kind == "group" and row.ref == gid), None)
        if r0 is None:
            return None
        base = rows[r0].depth; r1 = r0
        rr = r0 + 1
        while rr < len(rows) and rows[rr].depth > base:
            r1 = rr; rr += 1
        return r0, r1

    def _child_first_visible_row(self, rows, container_gid, index):
        """First visible row of the index-th child of the container's children (for positioning the insertion line); index==len returns the end."""
        children = self.doc.container_children(container_gid) or []
        sid2idx = {s["sid"]: i for i, s in enumerate(self.model.signals)}
        if index < len(children):
            nd = children[index]
            if nd.get("type") == "group":
                return next((r for r, row in enumerate(rows)
                             if row.kind == "group" and row.ref == nd["gid"]), None)
            si = sid2idx.get(nd.get("sid"))
            return next((r for r, row in enumerate(rows)
                         if row.kind == "sig" and row.ref == si), None)
        # index==len: lands at the end of the container
        if container_gid is None:
            return len(rows)
        span = self._group_visible_span(rows, container_gid)
        return (span[1] + 1) if span else None

    def _compute_drop(self, cy):
        HH, RH = self.geom.header_h, self.geom.row_h
        rows = self.model.layout()
        if not rows:
            self._drop = None; self._drop_target = None; return
        rf = (cy - HH) / RH
        if rf >= len(rows):                     # cursor below all rows: move out to the end of the top level
            top = self.doc.container_children(None)                # members can be dragged out even when the group is collapsed
            self._drop_target = {"container": None, "index": len(top), "valid": True}
            self._drop = {"y": HH + len(rows) * RH, "valid": True, "hl": None}
            return
        r = max(0, min(len(rows) - 1, int(rf)))
        lower = (rf - int(rf)) >= 0.5
        row = rows[r]
        container = None; index = 0; hl = None

        if row.kind == "group":
            gid = row.ref
            if not lower:                       # upper half: insert before this group (same level, the group's parent container)
                pg, _lst, idx = self.doc.locate(
                    lambda nd: nd.get("type") == "group" and nd.get("gid") == gid)
                container, index, hl = pg, idx, pg
            else:                               # lower half: place at the front of this group
                container, index, hl = gid, 0, gid
        else:                                   # signal row: container = its direct parent, index = same-level position +/- half a row
            sid = self.model.signals[row.ref]["sid"]
            loc = self.doc.locate(lambda nd: nd.get("type") == "sig" and nd.get("sid") == sid)
            pg, _lst, idx = loc
            container, index, hl = pg, idx + (1 if lower else 0), pg

        valid = True
        if self._drag_kind == "group":          # safeguard: cannot move into itself or its descendants
            if container is not None and self.doc.is_self_or_descendant(self._drag_ref, container):
                valid = False

        # insertion line y: align to the first visible row of index within the container
        vr = self._child_first_visible_row(rows, container, index)
        if vr is None:
            vr = r + (1 if lower else 0)
        self._drop_target = {"container": container, "index": index, "valid": valid}
        self._drop = {"y": HH + vr * RH, "valid": valid, "hl": hl}

    def _draw_drag_overlay(self):
        if not self._dragging or not self._drop:
            return
        rows = self.model.layout()
        HH, RH = self.geom.header_h, self.geom.row_h
        H = HH + len(rows) * RH
        NW = self.geom.name_w
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        WW = self.model.n_periods * self.geom.period_w + max_off * self.geom.period_w + 4
        self.name_cv.create_rectangle(0, 0, NW, H, fill="#C2C2C2", stipple="gray50", outline="")
        self.wave_cv.create_rectangle(0, 0, WW, H, fill="#C2C2C2", stipple="gray50", outline="")
        # highlight the "container it will drop into": outline the whole group block
        hl = self._drop.get("hl")
        if hl is not None and self._drop.get("valid"):
            span = self._group_visible_span(rows, hl)
            if span:
                y0 = HH + span[0] * RH; y1 = HH + (span[1] + 1) * RH
                for cv, w in ((self.name_cv, NW), (self.wave_cv, WW)):
                    cv.create_rectangle(1, y0 + 1, w - 1, y1 - 1,
                                        outline=Style.MARQUEE, width=2)
        # insertion line
        y = self._drop["y"]; col = Style.MARQUEE if self._drop["valid"] else "#CC2222"
        self.name_cv.create_line(0, y, NW, y, fill=col, width=3)
        self.wave_cv.create_line(0, y, WW, y, fill=col, width=3)

    def on_name_menu(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":              # ---- group header menu ----
            gid = item[1]; meta = self.model.groups.get(gid, {})
            m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            m.add_command(label=("Expand" if meta.get("collapsed") else "Collapse"),
                          command=lambda: self._toggle_group(gid))
            m.add_command(label="Group color...", command=lambda: self._color_group(gid))
            m.add_command(label="Set group offset...", command=lambda: self._offset_group(gid))
            m.add_command(label="Rename group...", command=lambda: self._rename_group(gid))
            others = [g for g in self.model.groups if g != gid]
            if others:
                sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
                for g in others:
                    sub.add_command(label=self.model.groups[g].get("name", g),
                                    command=lambda t=g: self._merge_group_into(gid, t))
                m.add_cascade(label="Merge into group", menu=sub)
            m.add_separator()
            m.add_command(label="Copy group", command=lambda: self._copy_group(gid))
            if self.clip_group:
                m.add_command(label="Paste group", command=self._paste_group)
            m.add_separator()
            m.add_command(label="Dissolve group (keep members)", command=lambda: self._dissolve_group(gid))
            m.add_command(label="Delete group (with members)", command=lambda: self._delete_group(gid))
            try:
                m.tk_popup(e.x_root, e.y_root)
            finally:
                m.grab_release()
            return
        s = item[1]                          # ---- signal menu ----
        if s not in self.sig_sel:
            self.sig_sel = {s}; self.selected = s; self._sig_anchor = s
            self.request_render()
        self._copy_ctx = "signals"
        n = len(self.sig_sel)
        scope = f" ({n} signals)" if n > 1 else ""
        grouped = any(self.model.signals[i].get("group") for i in self.sig_sel
                      if 0 <= i < len(self.model.signals))
        m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        m.add_command(label=f"Color...{scope}", command=self.pick_color)
        m.add_command(label=f"Clear color{scope}", command=self.clear_color)
        m.add_separator()
        m.add_command(label=f"Set offset...{scope}", command=self.set_offset_dialog)
        m.add_separator()
        m.add_command(label=f"Create new group...{scope}", command=self.group_selected)
        if self.model.groups:
            sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            for g, me in self.model.groups.items():
                sub.add_command(label=me.get("name", g),
                                command=lambda t=g: self._merge_selected_into(t))
            m.add_cascade(label=f"Merge into group{scope}", menu=sub)
        if grouped:
            m.add_command(label=f"Remove from group{scope}", command=self._remove_from_group)
        m.add_separator()
        m.add_command(label="Rename...", command=lambda: self._rename_signal(s))
        m.add_command(label=f"Delete signal{scope}", command=self.del_signal)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _rename_signal(self, s):
        if 0 <= s < len(self.model.signals):
            new = simpledialog.askstring("Rename", "Signal name:",
                                         initialvalue=self.model.signals[s]["name"], parent=self)
            if new:
                self.doc.rename_signal(s, new); self.request_render()

    def on_name_rename(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":
            self._rename_group(item[1])
        else:
            self._rename_signal(item[1])

    # ---- Group operations ----
    def group_selected(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        if not idxs:
            return
        name = simpledialog.askstring("Create New Group", "Group name:", initialvalue="Group", parent=self)
        if name is None:
            return
        sids = {self.model.signals[i]["sid"] for i in idxs}
        gid = self.doc.group_signals(idxs, name)
        if gid:
            newidx = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
            self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
            self.request_render()
            nm = self.model.groups.get(gid, {}).get("name", gid)
            self.status.configure(text=f" Created group \"{nm}\" ({len(newidx)} signals); click the header to collapse")

    def _merge_selected_into(self, target_gid):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        sids = {self.model.signals[i]["sid"] for i in idxs}
        res = self.doc.merge_into_group(idxs, target_gid)
        if not res:
            return
        nm = self.model.groups.get(target_gid, {}).get("name", target_gid)
        newpos = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
        self.sig_sel = set(newpos); self.selected = newpos[0]; self._sig_anchor = newpos[0]
        self.request_render()
        self.status.configure(text=f" Merged into group \"{nm}\" ({len(newpos)} signals)")

    def _merge_group_into(self, src_gid, target_gid):
        res = self.doc.merge_groups(src_gid, target_gid)
        if res:
            self.request_render()
            self.status.configure(
                text=f" Nested the group into \"{self.model.groups.get(target_gid, {}).get('name', target_gid)}\"")
        else:
            self.status.configure(text=" Cannot merge (cannot move into its own subgroup)")

    def _remove_from_group(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        moved = self.doc.remove_from_group(idxs)
        self.request_render()
        self.status.configure(text=(f" Removed {moved} signals (color reset to default)" if moved
                                    else " The selected signals are not in any group"))

    def _dissolve_group(self, gid):
        self.doc.ungroup([gid])             # dissolve: children move up one level (nested subgroups kept)
        self.request_render()
        self.status.configure(text=" Group dissolved (members/subgroups kept, promoted one level)")

    def _delete_group(self, gid):
        nm = self.model.groups.get(gid, {}).get("name", gid)
        n = len(self.doc.group_member_indices(gid))
        if not messagebox.askyesno("Delete Group",
                                   f"Delete group \"{nm}\" and its {n} signals?"):
            return
        self.doc.delete_group(gid)
        if self.model.signals:
            self.selected = min(self.selected, len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._hover_node = None; self._hover_edge = None
        self.request_render()
        self.status.configure(text=f" Deleted group \"{nm}\" and {n} signals")

    def _offset_group(self, gid):
        members = self.doc.group_member_indices(gid)
        if not members:
            return
        cur = self.model.signals[members[0]].get("offset", 0.0)
        v = simpledialog.askfloat("Group Offset", "Offset (0 ~ 0.95, applied to the whole group including subgroups):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        self.doc.set_offset(members, v)
        self.request_render()
        self.status.configure(text=f" Group offset set to {round(v,2)} for the whole group ({len(members)} signals)")

    def _copy_group(self, gid):
        meta = self.model.groups.get(gid, {})
        members = [self._copy_signal(self.model.signals[i])
                   for i in self.doc.group_member_indices(gid)]
        if not members:
            return
        self.clip_group = {"name": meta.get("name", gid), "color": meta.get("color"),
                           "signals": members}
        self._clip_kind = "group"
        self.status.configure(text=f" Copied group \"{self.clip_group['name']}\" ({len(members)} signals); Ctrl+V to paste")

    def _paste_group(self):
        res = self.doc.paste_group(self.clip_group)
        if res is None:
            return
        gname, newidx = res
        self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
        self.request_render()
        self.status.configure(text=f" Pasted group \"{gname}\" ({len(newidx)} signals, new group at the bottom)")

    def _toggle_group(self, gid):
        if self.doc.toggle_group(gid) is not None:
            self.request_render()

    def _rename_group(self, gid):
        meta = self.model.groups.get(gid)
        if meta:
            new = simpledialog.askstring("Rename Group", "Group name:",
                                         initialvalue=meta.get("name", gid), parent=self)
            if new:
                self.doc.rename_group(gid, new); self.request_render()

    def _color_group(self, gid):
        meta = self.model.groups.get(gid)
        if not meta:
            return
        try:
            _, hx = colorchooser.askcolor(color=meta.get("color") or Style.WAVE,
                                          parent=self, title="Group Color")
        except Exception:
            hx = None
        if hx:
            self.doc.set_group_color(gid, hx); self.request_render()

    def add_signal(self):
        self.selected = self.doc.add_signal()
        self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        self._refresh_offset_field(); self.request_render()

    def del_signal(self):
        if not self.model.signals:
            return
        targets = sorted({s for s in (self.sig_sel or {self.selected})
                          if 0 <= s < len(self.model.signals)})
        if not targets:
            return
        if len(targets) > 1 and not messagebox.askyesno(
                "Delete Signals", f"Delete the {len(targets)} selected signals?"):
            return
        self.doc.remove_signals(targets)
        if self.model.signals:
            self.selected = min(targets[0], len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._refresh_offset_field(); self.request_render()

    # ---- Undo / Redo (snapshot-based, depth 5; one gesture = one step) ----
    def do_undo(self):
        if self._is_typing():
            return
        if self.doc.undo():
            self._after_history_jump("Undone")
        else:
            self.status.configure(text=" Nothing to undo")

    def do_redo(self):
        if self._is_typing():
            return
        if self.doc.redo():
            self._after_history_jump("Redone")
        else:
            self.status.configure(text=" Nothing to redo")

    def _after_history_jump(self, verb):
        """After undo/redo the document is fully replaced: clamp the selection and clear transients pointing to old content."""
        n = len(self.model.signals)
        self.selected = min(self.selected, n - 1) if n else 0
        self.sig_sel = {self.selected} if n else set()
        self._sig_anchor = self.selected if n else None
        self.cell_sel = None; self._hover = None
        self._hover_node = None; self._hover_edge = None
        self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
        self.request_render()
        u, r = self.doc.history()
        self.status.configure(
            text=f" {verb} (undo {u}/{self.doc.UNDO_DEPTH}, redo {r})")

    def do_new(self):
        if messagebox.askyesno("New", "Clear the current content and start a new document?"):
            self.doc.new_document()
            self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None; self.clip = None
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self._refresh_offset_field(); self.request_render()

    def do_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                filetypes=[("Waveform JSON", "*.json"), ("All Files", "*.*")])
        if not path:
            return
        data = self.model.to_dict(); data["view"] = self.geom.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Save", f"Saved:\n{path}")

    def do_open(self):
        path = filedialog.askopenfilename(filetypes=[("Waveform JSON", "*.json"), ("All Files", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            cleared = self.doc.load_document(d)
            if "view" in d:
                self.geom.load(d["view"])
                self.sp_w.delete(0, tk.END); self.sp_w.insert(0, str(self.geom.period_w))
                self.sp_h.delete(0, tk.END); self.sp_h.insert(0, str(self.geom.row_h))
                self.sp_r.delete(0, tk.END); self.sp_r.insert(0, str(int(self.geom.ramp_ratio * 100)))
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None
            self._hover_node = None; self._hover_edge = None
            self._refresh_offset_field(); self.request_render()
            cn, ce = cleared or (0, 0)
            if cn or ce:
                self.status.configure(
                    text=f" Opened; detected unmappable annotations, removed {cn} anchors and {ce} relationship lines")
        except Exception as ex:
            messagebox.showerror("Open Failed", str(ex))

    def do_export(self):
        path = filedialog.asksaveasfilename(defaultextension=".png",
                filetypes=[("PNG Image", "*.png"), ("SVG Vector", "*.svg"),
                           ("EPS Vector", "*.eps"), ("PostScript", "*.ps")])
        if not path:
            return
        rows = self.model.layout()
        total_h = self.geom.header_h + len(rows) * self.geom.row_h
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        wave_w = self.model.n_periods * self.geom.period_w + max_off * self.geom.period_w
        lo = path.lower()
        if lo.endswith(".png"):
            scale = simpledialog.askinteger("PNG Resolution", "Scale (1~4, higher = sharper):",
                                            initialvalue=2, minvalue=1, maxvalue=4, parent=self)
            if scale is None:
                return
            try:
                export_png(self.model, self.geom, path, scale)
                messagebox.showinfo("Export", f"Exported PNG ({scale}x resolution):\n{path}")
            except ImportError:
                messagebox.showwarning("Export",
                    "PNG export only needs Pillow (Ghostscript not required).\nPlease install it first:\n  pip install pillow")
            except Exception as ex:
                messagebox.showerror("Export Failed", str(ex))
        elif lo.endswith(".svg"):
            try:
                export_svg(self.model, self.geom, path)
                messagebox.showinfo("Export", f"Exported SVG (vector, infinitely scalable):\n{path}")
            except Exception as ex:
                messagebox.showerror("Export Failed", str(ex))
        else:                                   # EPS / PS: built into tkinter, no extra packages needed
            sel = self.cell_sel; self.cell_sel = None; self.render()   # postscript snapshots the canvas directly, requires a synchronous redraw
            self.wave_cv.postscript(file=path, colormode="color",
                                    x=0, y=0, width=wave_w, height=total_h)
            self.cell_sel = sel; self.render()
            messagebox.showinfo("Export", f"Exported:\n{path}")



    # ---- WaveDrom export (interchange format; color / uniform-slope visuals are not preserved, nodes/edges carry over) ----
    def do_export_wavedrom(self):
        path = filedialog.asksaveasfilename(
            title="Export WaveDrom JSON", defaultextension=".json",
            filetypes=[("WaveDrom JSON", "*.json"), ("All Files", "*.*")])
        if not path:
            return
        try:
            export_wavedrom(self.model, path)
            messagebox.showinfo("Export WaveDrom",
                                f"Exported WaveDrom JSON:\n{path}\n\n"
                                "You can paste it into wavedrom.com or render it with wavedrom-cli.\n"
                                "Note: visuals such as color and uniform slope are redrawn by WaveDrom and not preserved.")
        except Exception as ex:
            messagebox.showerror("Export Failed", str(ex))


    def help_usage(self):
        messagebox.showinfo("Usage",
            "[Drawing waveforms] After picking an element: click a cell to draw it; drag to brush along the starting row (row-locked).\n"
            "  - BUS: cells that are already BUS keep continuing; only non-BUS cells become BUS.\n"
            "         Click the same cell again to enter/edit the data value.\n"
            "[Box-select (canvas)] Shift or Ctrl + drag is always pure box-select:\n"
            "  - After selecting, press an element key = fill the block (BUS asks for text once).\n"
            "  - Ctrl+C to copy; move to the target cell and Ctrl+V to paste (rows are added automatically if you run past the end).\n"
            "[Name column] Click to select signals (Ctrl/Shift for multi-select); press and drag up/down to move:\n"
            "  - Drag to the lower half of a group header / inside the group = merge into that group (the cursor position is the insertion point; merge + reorder in one go).\n"
            "  - Drag to the upper half of a group header = move before that group (same level); drag between top-level signals = move out to the top level.\n"
            "  - Drag a group header = move the whole group; dropping it on another group nests it as a subgroup (cannot drop into its own descendants).\n"
            "  - While dragging, the background dims, the target container lights up, and an insertion line is shown.\n"
            "  - Right-click a group header: collapse/color/group offset/copy/merge (nest)/dissolve/delete (with members).\n"
            "  - Nesting: a signal's right-click \"Merge into group\" adds it in; a group's right-click \"Merge into group\" makes it a subgroup.\n"
            "[Annotations] Right-click a waveform -> \"Create anchor here\" (snaps to the nearest cell edge).\n"
            "  - Hovering over an anchor highlights it; press and drag from an anchor to another anchor to create a relationship line\n"
            "    (while dragging, the waveform dims and freezes to highlight the foreground); enter a label on release (e.g. t_su).\n"
            "  - Anchors/relationship lines: hover to highlight, then press Del to delete; right-click a relationship line to change its label/arrow style.\n"
            "[Pan mode] Press Esc to fall back to pan mode (deselect element, clear box-select):\n"
            "  - Left-drag = pan the canvas (no accidental drawing).\n"
            "  - Shift/Ctrl + left-drag = box-select (same as draw mode).\n"
            "  - Click an element button or press number keys 1~6 to return to draw mode.\n"
            "[Offset] After shifting offset right, the left edge auto-extends the first cell's level and the right end is trimmed flush, giving a sense of continuity.\n"
            "[Export] Images PNG (1-4x)/SVG (vector)/EPS; you can also export the WaveDrom JSON interchange format.\n"
            "[Other] Right-click a waveform also offers \"Clear to L\"; double-click a name to rename; Esc falls back to pan mode and clears box-select.")

    def help_keys(self):
        messagebox.showinfo("Shortcuts",
            "Ctrl+N/O/S/E New/Open/Save/Export   Ctrl+C/V Copy/Paste\n"
            "Ctrl+Z/Y Undo/Redo (last 5 steps; one brush/fill/paste = one step)\n"
            "1~6 Switch element (CLK/H/L/BUS/HiZ/Unknown)\n"
            "Esc Pan mode (deselect element/clear box-select); in pan mode left-drag = pan canvas\n"
            "Shift/Ctrl+drag Box-select (works in both modes)   Press an element key = fill the selection\n"
            "Name column Ctrl/Shift+click for multi-select -> right-click menu (color/offset/group/rename/delete)\n"
            "Right-click a waveform Create anchor/Clear to L; drag an anchor to draw a relationship line; Del deletes annotations\n"
            "Double-click a name to rename")

    def help_about(self):
        messagebox.showinfo("About", f"RetroWave v{__version__}\nDigital circuit waveform editor\nPython + tkinter")


def main():
    App().mainloop()
