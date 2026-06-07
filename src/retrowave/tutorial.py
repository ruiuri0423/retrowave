# -*- coding: utf-8 -*-
"""Onboarding tutorial: semi-transparent dimming overlay + cut-out highlight + step-by-step guide.

A shell-layer module (a UI shell like app.py, allowed to import tkinter).
- Overlay: a Toplevel covering the main window's work area (semi-transparent alpha, dark background).
- Highlight: on Windows, `-transparentcolor` cuts out the target area — that region is fully clear
  **and directly clickable** (guiding users to actually do it); on unsupported platforms it
  degrades automatically to a bright frame marker (no cut-out).
- Exit: on the last step, tick "Don't show on next launch" and click Finish; pressing "Skip" at any
  time exits immediately and won't reopen. The preference is stored in ~/.retrowave/settings.json (show_tutorial).
"""
import tkinter as tk

from .i18n import tr
from .theme import Style
from .usersettings import load_settings, save_settings  # re-exported for tests/back-compat

HOLE = "#FF00FE"            # cut-out color (transparentcolor; a magenta the UI palette never uses)
RING = "#FFD34D"            # highlight frame
CARD_BG = "#FBF8EC"; CARD_BD = "#8A867A"


def tutorial_enabled():
    """Defaults to True (shown on first launch); becomes False after the user ticks don't-show / skips."""
    return bool(load_settings().get("show_tutorial", True))


def set_tutorial_enabled(flag):
    d = load_settings()
    d["show_tutorial"] = bool(flag)
    return save_settings(d)


class TutorialOverlay(tk.Toplevel):
    """Tutorial overlay covering the main window. steps = [(target_widget|None, title, body)]."""

    ALPHA = 0.88
    PAD = 8                  # cut-out region outward padding
    CARD_W = 460

    def __init__(self, master, steps):
        super().__init__(master)
        self.app = master
        self.steps = steps
        self.idx = 0
        self.dont_show = tk.BooleanVar(master=self, value=True)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", self.ALPHA)
        except tk.TclError:
            pass
        self._hole_ok = False
        try:                                     # Windows: cut-out and clickable
            self.attributes("-transparentcolor", HOLE)
            self._hole_ok = True
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self, bg="#23211B", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.bind("<Escape>", lambda e: self.skip())
        self._cfg_id = master.bind("<Configure>", self._on_master_configure, add="+")
        self._sync_geometry()
        self._show_step()

    # ---- geometry ----
    def _sync_geometry(self):
        m = self.app
        self.geometry(f"{max(m.winfo_width(), 1)}x{max(m.winfo_height(), 1)}"
                      f"+{m.winfo_rootx()}+{m.winfo_rooty()}")

    def _on_master_configure(self, _e=None):
        if self.winfo_exists():
            self._sync_geometry()
            self._show_step()

    def _target_bbox(self, widget):
        """The target widget's (x0,y0,x1,y1) in the overlay's coordinate system; None=no highlight."""
        if widget is None or not widget.winfo_exists():
            return None
        x0 = widget.winfo_rootx() - self.app.winfo_rootx() - self.PAD
        y0 = widget.winfo_rooty() - self.app.winfo_rooty() - self.PAD
        x1 = x0 + widget.winfo_width() + 2 * self.PAD
        y1 = y0 + widget.winfo_height() + 2 * self.PAD
        return x0, y0, x1, y1

    # ---- drawing ----
    def _show_step(self):
        cv = self.cv
        cv.delete("all")
        target, title, body = self.steps[self.idx]
        bbox = self._target_bbox(target)
        W = max(self.winfo_width(), 600); H = max(self.winfo_height(), 400)

        if bbox:
            x0, y0, x1, y1 = bbox
            if self._hole_ok:                    # cut-out: that region is clearly visible and directly usable
                cv.create_rectangle(x0, y0, x1, y1, fill=HOLE, outline="")
            cv.create_rectangle(x0, y0, x1, y1, outline=RING, width=3)
            cv.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline="#7A6320", width=1)

        # ---- info card: avoid the highlight region (highlight in upper half -> card below, and vice versa) ----
        cw = min(self.CARD_W, W - 40)
        last = self.idx == len(self.steps) - 1
        # Measure the wrapped body height first, then size the card to fit —
        # fixed heights overlap the button row when translations run long.
        tmp = cv.create_text(0, -10000, anchor="nw", text=body, width=cw - 36,
                             font=("Tahoma", 10))
        tb = cv.bbox(tmp)
        body_h = (tb[3] - tb[1]) if tb else 60
        cv.delete(tmp)
        ch = 48 + body_h + 18 + (34 if last else 0) + 52   # title + body + gap (+checkbox) + buttons
        cx = (W - cw) // 2
        if bbox is None:
            cy = (H - ch) // 2
        elif (bbox[1] + bbox[3]) / 2 < H / 2:
            cy = min(bbox[3] + 24, H - ch - 16)
        else:
            cy = max(bbox[1] - ch - 24, 16)
        cv.create_rectangle(cx + 4, cy + 5, cx + cw + 4, cy + ch + 5,
                            fill="#15130E", outline="")          # shadow
        cv.create_rectangle(cx, cy, cx + cw, cy + ch, fill=CARD_BG, outline=CARD_BD, width=2)
        cv.create_text(cx + 18, cy + 24, anchor="w", text=title,
                       font=("Tahoma", 12, "bold"), fill="#1A1A1A")
        cv.create_text(cx + cw - 18, cy + 24, anchor="e",
                       text=f"{self.idx + 1}/{len(self.steps)}",
                       font=Style.UI_FONT, fill="#777")
        cv.create_text(cx + 18, cy + 48, anchor="nw", text=body, width=cw - 36,
                       font=("Tahoma", 10), fill="#262626")

        # ---- button row ----
        by = cy + ch - 38
        btn_skip = tk.Button(cv, text=tr("Skip (don't show again)"), font=Style.UI_FONT,
                             bg=CARD_BG, relief=tk.GROOVE, command=self.skip)
        cv.create_window(cx + 18, by, anchor="w", window=btn_skip)
        if self.idx > 0:
            btn_prev = tk.Button(cv, text=tr("◀ Back"), font=Style.UI_FONT,
                                 bg=CARD_BG, relief=tk.GROOVE, command=self.prev)
            cv.create_window(cx + cw - 118, by, anchor="e", window=btn_prev)
        btn_next = tk.Button(cv, text=(tr("Finish") if last else tr("Next ▶")),
                             font=("Tahoma", 9, "bold"), bg="#EDE7CF",
                             relief=tk.RAISED, command=(self.finish if last else self.next))
        cv.create_window(cx + cw - 18, by, anchor="e", window=btn_next)
        if last:                                  # last step: don't-show-next-time checkbox
            chk = tk.Checkbutton(cv, text=tr("Don't show this tutorial again"),
                                 variable=self.dont_show, font=Style.UI_FONT,
                                 bg=CARD_BG, activebackground=CARD_BG)
            cv.create_window(cx + 18, by - 32, anchor="w", window=chk)

    # ---- flow ----
    def next(self):
        if self.idx < len(self.steps) - 1:
            self.idx += 1
            self._show_step()

    def prev(self):
        if self.idx > 0:
            self.idx -= 1
            self._show_step()

    def skip(self):
        """Skip: exit immediately and never show again."""
        set_tutorial_enabled(False)
        self.close()

    def finish(self):
        """Finish: whether to show next time depends on the checkbox."""
        set_tutorial_enabled(not self.dont_show.get())
        self.close()

    def close(self):
        try:
            self.app.unbind("<Configure>", self._cfg_id)
        except tk.TclError:
            pass
        self.destroy()
