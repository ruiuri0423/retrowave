# -*- coding: utf-8 -*-
"""UI 殼層：整個套件唯一允許 import tkinter 的模組。
設計文件 §8/§11；§14 的 UI↔Core protocol（R1–R5）是本模組的遷移目標契約。"""
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
        self.title(f"RetroWave - 數位波型繪製工具  v{__version__}")
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
        self._render_job = None                 # 待執行的合併重繪 (after_idle id)
        self._drag_value = None; self._hover = None
        self._hover_node = None; self._hover_edge = None
        self._connecting = False; self._connect_from = None; self._connect_xy = None
        self._name_press = None; self._name_moved = False; self._dragging = False
        self._drag_kind = None; self._drag_ref = None; self._drop = None; self._drop_target = None
        self.lib = TemplateLibrary()
        self._build_menubar(); self._build_toolbar(); self._build_main()
        self._build_statusbar(); self._bind_keys()
        self._set_tool("H"); self.render()          # 首次繪製須同步，視窗一出現即完整
        self.after(150, self._startup_templates)    # 視窗顯示後再載入範本/提示缺檔

    @property
    def model(self):
        """CQRS 讀路徑：渲染/版面/命中測試唯讀直通；任何寫入一律走 self.doc 命令。"""
        return self.doc.model

    def _on_doc_changed(self, scopes):
        """傳遞層 change 事件 → 重繪（合併排程）。"""
        self.request_render()

    def _build_menubar(self):
        bar = tk.Frame(self, bg=Style.FACE, bd=1, relief=tk.RAISED); bar.pack(side=tk.TOP, fill=tk.X)
        fmb = tk.Menubutton(bar, text="File", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        fm = tk.Menu(fmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        fm.add_command(label="新增 (New)\tCtrl+N", command=self.do_new)
        fm.add_command(label="開啟… (Load)\tCtrl+O", command=self.do_open)
        fm.add_command(label="儲存… (Save)\tCtrl+S", command=self.do_save)
        fm.add_separator()
        fm.add_command(label="匯入範本… (Import Template)", command=self._import_template)
        fm.add_separator()
        fm.add_command(label="匯出圖片… (Export)\tCtrl+E", command=self.do_export)
        fm.add_command(label="匯出 WaveDrom JSON…", command=self.do_export_wavedrom)
        fm.add_separator()
        fm.add_command(label="離開 (Exit)", command=self.destroy)
        fmb.configure(menu=fm); fmb.pack(side=tk.LEFT)

        tmb = tk.Menubutton(bar, text="Template", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        self.tmpl_menu = tk.Menu(tmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        tmb.configure(menu=self.tmpl_menu); tmb.pack(side=tk.LEFT)
        self._rebuild_template_menu()
        hmb = tk.Menubutton(bar, text="Help", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        hm = tk.Menu(hmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        hm.add_command(label="使用說明", command=self.help_usage)
        hm.add_command(label="快捷鍵", command=self.help_keys)
        hm.add_separator()
        hm.add_command(label="關於 RetroWave", command=self.help_about)
        hmb.configure(menu=hm); hmb.pack(side=tk.LEFT)

    # ---- 範本庫 ----
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
            self._tmpl_rem = rem               # 保留參考避免被回收
            m.add_cascade(label="移除範本", menu=rem)
        else:
            m.add_command(label="(尚無範本)", state="disabled")
        m.add_separator()
        m.add_command(label="匯入範本… (Import)", command=self._import_template)
        m.add_command(label="將目前畫布存成範本…", command=self._save_as_template)

    def _startup_templates(self):
        avail, missing = self.lib.load()
        self._rebuild_template_menu()
        if missing:
            lines = "\n".join(f"・{m['name']}    ({m.get('path') or '路徑未知'})" for m in missing)
            messagebox.showwarning(
                "範本載入", f"以下範本檔案找不到，已從清單移除：\n\n{lines}")

    def _import_template(self):
        path = filedialog.askopenfilename(
            title="匯入範本 (JSON)", filetypes=[("波型 JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            d = TemplateLibrary.read(path)
            if not isinstance(d, dict) or "signals" not in d:
                raise ValueError("不是有效的波型 JSON（缺 signals 欄位）")
        except Exception as ex:
            messagebox.showerror("匯入範本失敗", str(ex)); return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("匯入範本", "範本名稱:", initialvalue=default, parent=self)
        if not name:
            return
        self.lib.add(name, path); self._rebuild_template_menu()
        messagebox.showinfo("匯入範本",
                            f"已加入範本「{name}」。\n（此範本會在每次開啟工具時自動載入，"
                            f"從 Template 選單點選即可插入為群組。）")

    def _save_as_template(self):
        path = filedialog.asksaveasfilename(
            title="將目前畫布存成範本", defaultextension=".json",
            initialdir=TemplateLibrary.DIR, filetypes=[("波型 JSON", "*.json")])
        if not path:
            return
        data = self.model.to_dict(); data["view"] = self.geom.to_dict()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            messagebox.showerror("存成範本失敗", str(ex)); return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("存成範本", "範本名稱:", initialvalue=default, parent=self)
        if not name:
            return
        self.lib.add(name, path); self._rebuild_template_menu()
        messagebox.showinfo("範本", f"已存成範本「{name}」。")

    def _remove_template(self, name):
        self.lib.remove(name); self._rebuild_template_menu()
        self.status.configure(text=f" 已從範本庫移除「{name}」（原檔案不受影響）")

    def _insert_template(self, entry):
        try:
            tsignals = TemplateLibrary.read(entry["path"]).get("signals", [])
        except Exception as ex:
            messagebox.showerror("插入範本失敗",
                                 f"讀取失敗，檔案可能已移動或刪除。\n{entry.get('path')}\n\n{ex}")
            return
        if not tsignals:
            messagebox.showwarning("插入範本", "此範本沒有任何訊號。"); return
        gname, newidx = self.doc.insert_template(entry["name"], tsignals)
        self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
        self.request_render()
        self.status.configure(text=f" 已插入範本「{gname}」（{len(newidx)} 條，已成群組）")

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=Style.FACE, bd=1, relief=tk.RAISED); tb.pack(side=tk.TOP, fill=tk.X)
        cfg = tk.Frame(tb, bg=Style.FACE); cfg.pack(side=tk.RIGHT, padx=6, pady=4)
        self.sp_w = self._spin(cfg, "寬度", 30, 240, 4, self.geom.period_w, self._apply_geom)
        self.sp_h = self._spin(cfg, "列高", 36, 160, 4, self.geom.row_h, self._apply_geom)
        self.sp_r = self._spin(cfg, "斜率%", 5, 45, 1, int(self.geom.ramp_ratio * 100), self._apply_geom)
        self.sp_p = self._spin(cfg, "週期", 1, 256, 1, self.model.n_periods, self._apply_periods)

        tk.Label(tb, text="元件:", bg=Style.FACE, font=Style.UI_FONT).pack(side=tk.LEFT, padx=(6, 2), pady=6)
        for t in WAVE_TYPES:
            b = make_key_button(tb, t, lambda x=t: self._set_tool(x))
            b.pack(side=tk.LEFT, padx=2, pady=6); self.tool_btns[t] = b
        tk.Frame(tb, width=2, bg=Style.FACE_DARK).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=8)
        make_key_button(tb, "＋訊號", self.add_signal).pack(side=tk.LEFT, padx=2, pady=6)
        tk.Label(tb, text="(訊號右鍵：調色/位移/群組/改名/刪除；點群組標頭折疊)", bg=Style.FACE,
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
        v = simpledialog.askfloat("設定位移", "位移 (0 ~ 0.95 週期):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        self.doc.set_offset(sorted(self.sig_sel or {self.selected}), v)
        self.request_render()

    def _refresh_offset_field(self):
        pass            # 位移已移至右鍵選單，無常駐欄位

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
        """回傳 (水平可捲, 垂直可捲)：內容尺寸未超過視窗可視範圍時，該軸禁止平移/滾動。"""
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

    # ---- 工具 ----
    def _set_tool(self, t):
        if self.cell_sel is not None:          # 有框選 -> 填入該範圍
            self._fill_selection(t); return
        self.active_tool = t; self._refresh_tools()
        self.wave_cv.configure(cursor="")
        self.request_render()

    def _enter_pan_mode(self):
        """Esc：任何狀態皆退回畫布拖曳模式（清除框選、取消元件選擇）。"""
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
            txt = simpledialog.askstring("填入 BUS", "此範圍的資料值:", parent=self)
            if txt is None:
                return None
            payload = ("BUS", txt)
        elif t == "Unknown":
            payload = ("Unknown", "")
        else:
            payload = (t, "")
        self.doc.begin()                        # 一次填入 = 一個 undo 單位
        for s in range(s0, s1 + 1):
            for p in range(p0, p1 + 1):
                self.doc.set_cell(s, p, payload[0], payload[1])
        self.doc.commit()
        return f"已填入 {payload[0]}" + (f" = '{payload[1]}'" if payload[0] == "BUS" else "")

    def _fill_selection(self, t):
        if self.cell_sel is None:
            return
        msg = self._fill_rect(self.cell_sel, t)
        if msg:
            self.request_render(); self.status.configure(text=" " + msg + "（選取保留，Esc 清除）")

    def _update_status(self):
        if self.active_tool is None:
            self.status.configure(
                text=f" 拖曳模式 | 左鍵拖曳=平移畫布 | Shift/Ctrl+左鍵拖曳=框選 "
                     f"| 點元件鈕或數字鍵回繪製 | 週期{self.model.n_periods}")
            return
        if self.active_tool == "BUS":
            hint = "點/拖曳=畫BUS(原為BUS保留, 非BUS取代);再點同格=改值"
        else:
            hint = "點/拖曳上色(鎖列)"
        self.status.configure(
            text=f" 筆刷:{self.active_tool} | {hint} | Shift/Ctrl拖曳=框選(按元件鍵填入/Ctrl+C複製) "
                 f"| 名稱Ctrl/Shift多選 -> 右鍵: 調色/位移/刪除 | Esc=拖曳模式 | 週期{self.model.n_periods}")

    def request_render(self):
        """合併重繪：同一事件迴圈周期內的多次請求，只在 idle 時重繪一次。
        互動程式碼一律呼叫本方法；只有「接著要同步讀取畫布內容」(如 EPS 匯出的
        postscript 快照、__init__ 首繪) 才直接呼叫 render()。"""
        if self._render_job is None:
            self._render_job = self.after_idle(self._render_now)

    def _render_now(self):
        self._render_job = None
        self.render()

    def render(self):
        if self._render_job is not None:        # 同步重繪 -> 取消尚未執行的合併請求
            self.after_cancel(self._render_job); self._render_job = None
        self.name_cv.configure(width=self.geom.name_w)
        self.engine.draw(self.name_cv, self.wave_cv, self.model, self.sig_sel, self.geom, self.cell_sel)
        # 內容縮回視窗範圍內（刪列/收合群組等）時，把該軸拉回原點並保持名稱欄同步
        h_ok, v_ok = self._scrollable()
        if not v_ok:
            self.wave_cv.yview_moveto(0.0); self.name_cv.yview_moveto(0.0)
        if not h_ok:
            self.wave_cv.xview_moveto(0.0)
        self._draw_annot_overlay()
        self._draw_drag_overlay()
        self._update_status()

    # ---- 標注：座標/命中/覆蓋層 ----
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

    # ---- 座標 <-> 格子 (透過 layout 把可見列翻成訊號索引) ----
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

    # ---- 滑鼠 ----
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
        if nid:                                   # 從錨點拉線 (進入冷凍)；繪製/拖曳模式皆可
            self._connecting = True; self._connect_from = nid
            self._connect_xy = (cx, cy); self._press = None
            self._selecting = False; self._moved = False
            self.request_render(); return
        if self.active_tool is None and not (ctrl or shift):   # 拖曳模式：左鍵=平移畫布
            self._panning = True
            self._pan_anchor = (e.x, e.y, self.wave_cv.xview()[0], self.wave_cv.yview()[0])
            self._press = None; self._selecting = False; self._moved = False
            return
        self._press = self._cell_from_xy(cx, cy)
        self._moved = False
        self._selecting = ctrl or shift          # Shift/Ctrl 拖曳皆為純框選
        if self._press:
            self.selected = self._press[0]
        self._drag_value = None
        if self._press and not self._selecting and self.active_tool is not None:
            self.doc.begin()                     # 一次筆刷手勢 = 一個 undo 單位
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
            # 用 xview/yview_moveto 平移，並依 _scrollable() 明確禁止「內容未超出視窗」
            # 的軸（取代 scan_dragto：scan 不受 scrollregion 限制，會造成內容比視窗矮
            # 仍可垂直拖動、且拖出範圍後名稱欄 yview 同步失準）。
            ax, ay, fx, fy = self._pan_anchor
            sr = self.wave_cv.cget("scrollregion").split()
            sw = max(float(sr[2]) - float(sr[0]), 1.0)
            sh = max(float(sr[3]) - float(sr[1]), 1.0)
            h_ok, v_ok = self._scrollable()
            self.wave_cv.xview_moveto(fx + (ax - e.x) / sw if h_ok else 0.0)
            self.wave_cv.yview_moveto(fy + (ay - e.y) / sh if v_ok else 0.0)
            self.name_cv.yview_moveto(self.wave_cv.yview()[0])   # 以夾住後的實際值同步名稱欄
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
                label = simpledialog.askstring("關係線", "標籤 (可留空，例如 t_su):", parent=self) or ""
                self.doc.add_edge(frm, target, label)
                self.status.configure(text=f" 已建立關係線 {frm} → {target}")
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
                self.status.configure(text=" 已框選；按元件鍵填入、或 Ctrl+C 複製")
        else:
            if not self._moved and self._press:
                self._click_cell(*self._press)
            self.doc.commit()                    # 結算筆刷手勢（無變更則不入 undo 棧）
            self.request_render()

    def on_wave_menu(self, e):
        cx, cy = self._ev_xy(e)
        m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        nid = self._node_at_xy(cx, cy)
        if nid:
            m.add_command(label=f"刪除錨點 {nid}", command=lambda: self._del_node(nid))
        else:
            ei = self._edge_at_xy(cx, cy)
            if ei is not None:
                m.add_command(label="編輯標籤…", command=lambda: self._edit_edge(ei))
                sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
                cur = self.model.edges[ei].get("style", "double")
                for sty, lab in (("double", "雙箭頭（量測）"),
                                 ("single", "單箭頭（因果）"),
                                 ("measure", "無箭頭（量測線）")):
                    mark = "● " if sty == cur else "○ "
                    sub.add_command(label=mark + lab, command=lambda s=sty: self._set_edge_style(ei, s))
                m.add_cascade(label="箭頭樣式", menu=sub)
                m.add_command(label="刪除關係線", command=lambda: self._del_edge(ei))
            else:
                c = self._cell_from_xy(cx, cy)
                if not c:
                    return
                m.add_command(label="在此建立錨點", command=lambda: self._add_node_at(cx, cy))
                m.add_separator()
                m.add_command(label="清成 L",
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
        self.request_render(); self.status.configure(text=f" 已建立錨點 {nid}（拖曳錨點可拉關係線；Del 刪除）")

    def _del_node(self, nid):
        self.doc.remove_anchor(nid)
        if self._hover_node == nid:
            self._hover_node = None
        self.request_render(); self.status.configure(text=f" 已刪除錨點 {nid}")

    def _edit_edge(self, i):
        if 0 <= i < len(self.model.edges):
            cur = self.model.edges[i].get("label", "")
            new = simpledialog.askstring("關係線標籤", "標籤:", initialvalue=cur, parent=self)
            if new is not None:
                self.doc.set_edge_label(i, new); self.request_render()

    def _del_edge(self, i):
        if self.doc.remove_edge(i):
            self._hover_edge = None
            self.request_render(); self.status.configure(text=" 已刪除關係線")

    def _set_edge_style(self, i, style):
        if self.doc.set_edge_style(i, style):
            self.request_render()
            self.status.configure(text=f" 關係線樣式：{ {'double':'雙箭頭','single':'單箭頭因果','measure':'無箭頭量測'}[style] }")

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
            if cells[p]["type"] == "BUS":           # 原為 BUS -> 保留延續，不覆蓋
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
        if t is None:                                    # 拖曳模式不繪製
            return
        cells = self.model.signals[s]["cells"]
        if t == "BUS" and cells[p]["type"] == "BUS":     # 已是 BUS -> 改值
            cur = cells[p].get("text", "")
            new = simpledialog.askstring("BUS 資料", "輸入資料值:", initialvalue=cur, parent=self)
            if new is not None:
                self.doc.set_cell(s, p, "BUS", new)
        else:
            self._paint_cell(s, p, t, self._drag_value)

    # ---- 複製 / 貼上 (波形級 + 訊號級) ----
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
            self.status.configure(text=f" 已複製 {len(idxs)} 條訊號；Ctrl+V 貼在選取列之後")
        elif self.cell_sel is not None:
            s0, s1, p0, p1 = self.cell_sel
            self.clip = [[{"type": self.model.signals[s]["cells"][p]["type"],
                           "text": self.model.signals[s]["cells"][p].get("text", "")}
                          for p in range(p0, p1 + 1)] for s in range(s0, s1 + 1)]
            self._clip_kind = "cells"
            self.status.configure(text=f" 已複製 {s1-s0+1}x{p1-p0+1} 波形；移到目標格 Ctrl+V 貼上")

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
            self.status.configure(text=f" 已貼上 {len(self.clip_signals)} 條訊號（複本未分組）")
        elif self._clip_kind == "cells" and self.clip:
            s0, p0 = self._hover or (self.selected, 0)
            self.doc.begin()                     # 一次貼上 = 一個 undo 單位
            while len(self.model.signals) < s0 + len(self.clip):
                self.doc.add_signal()
            for ds, row in enumerate(self.clip):
                for dp, c in enumerate(row):
                    self.doc.set_cell(s0 + ds, p0 + dp, c["type"], c.get("text", ""))
            self.doc.commit()
            self.request_render(); self.status.configure(text=f" 已貼上波形於 訊號{s0} T{p0}")

    # ---- 調色 ----
    def pick_color(self):
        if not self.model.signals:
            return
        init = self.model.signals[self.selected].get("color") or Style.WAVE
        try:
            _, hx = colorchooser.askcolor(color=init, parent=self, title="訊號顏色")
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

    # ---- 名稱欄 (點選 / 拖曳排序) ----
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
            if item is None or abs(cy - py) < self.geom.row_h / 2:   # 門檻=列高一半
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
                    self.status.configure(text=" 已移動訊號" +
                                          ("（併入群組）" if tgt["container"] else "（移到頂層）"))
                else:
                    self.doc.move_group_to(self._drag_ref, tgt["container"], tgt["index"])
                    self.status.configure(text=" 已移動群組" +
                                          ("（巢狀為子群組）" if tgt["container"] else "（頂層）"))
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
        if item[0] == "group":              # 點群組標頭 = 折疊/展開
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

    # ---- 拖曳落點解析 (容器 + 插入索引)、容器高亮、插入線 ----
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
        """容器 children 第 index 個子節點的首個可見列 (供插入線定位)；index==len 回末端。"""
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
        # index==len：落在容器尾端
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
        if rf >= len(rows):                     # 游標在所有列之下：移出到頂層尾端
            top = self.doc.container_children(None)                # 群組收底時也能拖出成員
            self._drop_target = {"container": None, "index": len(top), "valid": True}
            self._drop = {"y": HH + len(rows) * RH, "valid": True, "hl": None}
            return
        r = max(0, min(len(rows) - 1, int(rf)))
        lower = (rf - int(rf)) >= 0.5
        row = rows[r]
        container = None; index = 0; hl = None

        if row.kind == "group":
            gid = row.ref
            if not lower:                       # 上半：插在此群組之前 (同層、群組的父容器)
                pg, _lst, idx = self.doc.locate(
                    lambda nd: nd.get("type") == "group" and nd.get("gid") == gid)
                container, index, hl = pg, idx, pg
            else:                               # 下半：放進此群組最前
                container, index, hl = gid, 0, gid
        else:                                   # 訊號列：容器=其直接父，索引=同層位置±半列
            sid = self.model.signals[row.ref]["sid"]
            loc = self.doc.locate(lambda nd: nd.get("type") == "sig" and nd.get("sid") == sid)
            pg, _lst, idx = loc
            container, index, hl = pg, idx + (1 if lower else 0), pg

        valid = True
        if self._drag_kind == "group":          # 防呆：不可移入自己或子孫
            if container is not None and self.doc.is_self_or_descendant(self._drag_ref, container):
                valid = False

        # 插入線 y：對齊容器內 index 的首個可見列
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
        # 點亮「將落入的容器」：框出該群組整塊
        hl = self._drop.get("hl")
        if hl is not None and self._drop.get("valid"):
            span = self._group_visible_span(rows, hl)
            if span:
                y0 = HH + span[0] * RH; y1 = HH + (span[1] + 1) * RH
                for cv, w in ((self.name_cv, NW), (self.wave_cv, WW)):
                    cv.create_rectangle(1, y0 + 1, w - 1, y1 - 1,
                                        outline=Style.MARQUEE, width=2)
        # 插入線
        y = self._drop["y"]; col = Style.MARQUEE if self._drop["valid"] else "#CC2222"
        self.name_cv.create_line(0, y, NW, y, fill=col, width=3)
        self.wave_cv.create_line(0, y, WW, y, fill=col, width=3)

    def on_name_menu(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":              # ---- 群組標頭選單 ----
            gid = item[1]; meta = self.model.groups.get(gid, {})
            m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            m.add_command(label=("展開" if meta.get("collapsed") else "折疊"),
                          command=lambda: self._toggle_group(gid))
            m.add_command(label="群組調色…", command=lambda: self._color_group(gid))
            m.add_command(label="設定群組位移…", command=lambda: self._offset_group(gid))
            m.add_command(label="重新命名群組…", command=lambda: self._rename_group(gid))
            others = [g for g in self.model.groups if g != gid]
            if others:
                sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
                for g in others:
                    sub.add_command(label=self.model.groups[g].get("name", g),
                                    command=lambda t=g: self._merge_group_into(gid, t))
                m.add_cascade(label="合併至群組", menu=sub)
            m.add_separator()
            m.add_command(label="複製群組", command=lambda: self._copy_group(gid))
            if self.clip_group:
                m.add_command(label="貼上群組", command=self._paste_group)
            m.add_separator()
            m.add_command(label="解散群組（保留成員）", command=lambda: self._dissolve_group(gid))
            m.add_command(label="刪除群組（含成員）", command=lambda: self._delete_group(gid))
            try:
                m.tk_popup(e.x_root, e.y_root)
            finally:
                m.grab_release()
            return
        s = item[1]                          # ---- 訊號選單 ----
        if s not in self.sig_sel:
            self.sig_sel = {s}; self.selected = s; self._sig_anchor = s
            self.request_render()
        self._copy_ctx = "signals"
        n = len(self.sig_sel)
        scope = f"（{n} 條）" if n > 1 else ""
        grouped = any(self.model.signals[i].get("group") for i in self.sig_sel
                      if 0 <= i < len(self.model.signals))
        m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        m.add_command(label=f"調色…{scope}", command=self.pick_color)
        m.add_command(label=f"清除顏色{scope}", command=self.clear_color)
        m.add_separator()
        m.add_command(label=f"設定位移…{scope}", command=self.set_offset_dialog)
        m.add_separator()
        m.add_command(label=f"建立新群組…{scope}", command=self.group_selected)
        if self.model.groups:
            sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            for g, me in self.model.groups.items():
                sub.add_command(label=me.get("name", g),
                                command=lambda t=g: self._merge_selected_into(t))
            m.add_cascade(label=f"合併至群組{scope}", menu=sub)
        if grouped:
            m.add_command(label=f"移出群組{scope}", command=self._remove_from_group)
        m.add_separator()
        m.add_command(label="重新命名…", command=lambda: self._rename_signal(s))
        m.add_command(label=f"刪除訊號{scope}", command=self.del_signal)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _rename_signal(self, s):
        if 0 <= s < len(self.model.signals):
            new = simpledialog.askstring("改名", "訊號名稱:",
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

    # ---- 群組操作 ----
    def group_selected(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        if not idxs:
            return
        name = simpledialog.askstring("建立新群組", "群組名稱:", initialvalue="群組", parent=self)
        if name is None:
            return
        sids = {self.model.signals[i]["sid"] for i in idxs}
        gid = self.doc.group_signals(idxs, name)
        if gid:
            newidx = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
            self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
            self.request_render()
            nm = self.model.groups.get(gid, {}).get("name", gid)
            self.status.configure(text=f" 已建立群組「{nm}」（{len(newidx)} 條）；點標頭可折疊")

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
        self.status.configure(text=f" 已併入群組「{nm}」（{len(newpos)} 條）")

    def _merge_group_into(self, src_gid, target_gid):
        res = self.doc.merge_groups(src_gid, target_gid)
        if res:
            self.request_render()
            self.status.configure(
                text=f" 已將群組巢狀至「{self.model.groups.get(target_gid, {}).get('name', target_gid)}」")
        else:
            self.status.configure(text=" 無法合併（不可移入自己的子群組）")

    def _remove_from_group(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        moved = self.doc.remove_from_group(idxs)
        self.request_render()
        self.status.configure(text=(f" 已移出 {moved} 條訊號（顏色回預設）" if moved
                                    else " 選取的訊號不在任何群組中"))

    def _dissolve_group(self, gid):
        self.doc.ungroup([gid])             # 解散：children 提升一層 (保留巢狀子群組)
        self.request_render()
        self.status.configure(text=" 已解散群組（成員/子群組保留、提升一層）")

    def _delete_group(self, gid):
        nm = self.model.groups.get(gid, {}).get("name", gid)
        n = len(self.doc.group_member_indices(gid))
        if not messagebox.askyesno("刪除群組",
                                   f"確定刪除群組「{nm}」及其 {n} 條訊號？"):
            return
        self.doc.delete_group(gid)
        if self.model.signals:
            self.selected = min(self.selected, len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._hover_node = None; self._hover_edge = None
        self.request_render()
        self.status.configure(text=f" 已刪除群組「{nm}」及 {n} 條訊號")

    def _offset_group(self, gid):
        members = self.doc.group_member_indices(gid)
        if not members:
            return
        cur = self.model.signals[members[0]].get("offset", 0.0)
        v = simpledialog.askfloat("群組位移", "位移 (0 ~ 0.95，整組含子群組套用相同值):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        self.doc.set_offset(members, v)
        self.request_render()
        self.status.configure(text=f" 群組整組位移設為 {round(v,2)}（{len(members)} 條）")

    def _copy_group(self, gid):
        meta = self.model.groups.get(gid, {})
        members = [self._copy_signal(self.model.signals[i])
                   for i in self.doc.group_member_indices(gid)]
        if not members:
            return
        self.clip_group = {"name": meta.get("name", gid), "color": meta.get("color"),
                           "signals": members}
        self._clip_kind = "group"
        self.status.configure(text=f" 已複製群組「{self.clip_group['name']}」（{len(members)} 條）；Ctrl+V 貼上")

    def _paste_group(self):
        res = self.doc.paste_group(self.clip_group)
        if res is None:
            return
        gname, newidx = res
        self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
        self.request_render()
        self.status.configure(text=f" 已貼上群組「{gname}」（{len(newidx)} 條，新群組於底部）")

    def _toggle_group(self, gid):
        if self.doc.toggle_group(gid) is not None:
            self.request_render()

    def _rename_group(self, gid):
        meta = self.model.groups.get(gid)
        if meta:
            new = simpledialog.askstring("群組改名", "群組名稱:",
                                         initialvalue=meta.get("name", gid), parent=self)
            if new:
                self.doc.rename_group(gid, new); self.request_render()

    def _color_group(self, gid):
        meta = self.model.groups.get(gid)
        if not meta:
            return
        try:
            _, hx = colorchooser.askcolor(color=meta.get("color") or Style.WAVE,
                                          parent=self, title="群組顏色")
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
                "刪除訊號", f"確定刪除選取的 {len(targets)} 條訊號？"):
            return
        self.doc.remove_signals(targets)
        if self.model.signals:
            self.selected = min(targets[0], len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._refresh_offset_field(); self.request_render()

    # ---- Undo / Redo（快照式，深度 5；一個手勢 = 一步）----
    def do_undo(self):
        if self._is_typing():
            return
        if self.doc.undo():
            self._after_history_jump("已復原")
        else:
            self.status.configure(text=" 沒有可復原的步驟")

    def do_redo(self):
        if self._is_typing():
            return
        if self.doc.redo():
            self._after_history_jump("已重做")
        else:
            self.status.configure(text=" 沒有可重做的步驟")

    def _after_history_jump(self, verb):
        """undo/redo 後文件已整份置換：夾住選取、清掉指向舊內容的暫態。"""
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
            text=f" {verb}（可復原 {u}/{self.doc.UNDO_DEPTH}、可重做 {r}）")

    def do_new(self):
        if messagebox.askyesno("新增", "清空目前內容並新建？"):
            self.doc.new_document()
            self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None; self.clip = None
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self._refresh_offset_field(); self.request_render()

    def do_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                filetypes=[("波型 JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        data = self.model.to_dict(); data["view"] = self.geom.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("儲存", f"已儲存:\n{path}")

    def do_open(self):
        path = filedialog.askopenfilename(filetypes=[("波型 JSON", "*.json"), ("所有檔案", "*.*")])
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
                    text=f" 已開啟；偵測到無法對應的標注，已清除錨點 {cn}、關係線 {ce}")
        except Exception as ex:
            messagebox.showerror("開啟失敗", str(ex))

    def do_export(self):
        path = filedialog.asksaveasfilename(defaultextension=".png",
                filetypes=[("PNG 圖片", "*.png"), ("SVG 向量圖", "*.svg"),
                           ("EPS 向量圖", "*.eps"), ("PostScript", "*.ps")])
        if not path:
            return
        rows = self.model.layout()
        total_h = self.geom.header_h + len(rows) * self.geom.row_h
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        wave_w = self.model.n_periods * self.geom.period_w + max_off * self.geom.period_w
        lo = path.lower()
        if lo.endswith(".png"):
            scale = simpledialog.askinteger("PNG 解析度", "倍率 (1~4，越大越清晰):",
                                            initialvalue=2, minvalue=1, maxvalue=4, parent=self)
            if scale is None:
                return
            try:
                export_png(self.model, self.geom, path, scale)
                messagebox.showinfo("匯出", f"已輸出 PNG（{scale}× 解析度）:\n{path}")
            except ImportError:
                messagebox.showwarning("匯出",
                    "PNG 匯出只需要 Pillow（不需要 Ghostscript）。\n請先安裝：\n  pip install pillow")
            except Exception as ex:
                messagebox.showerror("匯出失敗", str(ex))
        elif lo.endswith(".svg"):
            try:
                export_svg(self.model, self.geom, path)
                messagebox.showinfo("匯出", f"已輸出 SVG（向量、可無限縮放）:\n{path}")
            except Exception as ex:
                messagebox.showerror("匯出失敗", str(ex))
        else:                                   # EPS / PS：tkinter 內建，無需任何套件
            sel = self.cell_sel; self.cell_sel = None; self.render()   # postscript 直接快照畫布，須同步重繪
            self.wave_cv.postscript(file=path, colormode="color",
                                    x=0, y=0, width=wave_w, height=total_h)
            self.cell_sel = sel; self.render()
            messagebox.showinfo("匯出", f"已輸出:\n{path}")



    # ---- WaveDrom 匯出 (交換格式；顏色/統一斜率視覺不保留，node/edge 可帶過去) ----
    def do_export_wavedrom(self):
        path = filedialog.asksaveasfilename(
            title="匯出 WaveDrom JSON", defaultextension=".json",
            filetypes=[("WaveDrom JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            export_wavedrom(self.model, path)
            messagebox.showinfo("匯出 WaveDrom",
                                f"已輸出 WaveDrom JSON：\n{path}\n\n"
                                "可貼到 wavedrom.com 或用 wavedrom-cli 算圖。\n"
                                "註：顏色與統一斜率等視覺由 WaveDrom 自行重畫，不會保留。")
        except Exception as ex:
            messagebox.showerror("匯出失敗", str(ex))


    def help_usage(self):
        messagebox.showinfo("使用說明",
            "【畫波形】選元件後：點一格畫一格；拖曳沿起始列刷 (鎖列)。\n"
            "  · BUS：原本是 BUS 的格會保留延續；非 BUS 的格才轉成 BUS。\n"
            "         再點同格可輸入/修改資料值。\n"
            "【框選 (畫布)】Shift 或 Ctrl + 拖曳都是純框選：\n"
            "  · 框選後按元件鍵 = 整塊填入 (BUS 問一次文字)。\n"
            "  · Ctrl+C 複製、移到目標格 Ctrl+V 貼上 (超出列數自動新增列)。\n"
            "【名稱欄】點選訊號 (Ctrl/Shift 多選)；按住上下拖曳可移動：\n"
            "  · 拖到群組標頭下半/群組內 = 併入該群組(游標位置即插入點，合併+排序一次到位)。\n"
            "  · 拖到群組標頭上半 = 移到該群組之前(同層)；拖到頂層訊號間 = 移出到頂層。\n"
            "  · 拖群組標頭 = 整組移動，落在另一群組上即巢狀為子群組(不可落入自己子孫)。\n"
            "  · 拖曳時背景反灰、點亮將落入的容器並顯示插入線。\n"
            "  · 群組標頭右鍵：折疊/調色/群組位移/複製/合併(巢狀)/解散/刪除(含成員)。\n"
            "  · 巢狀：訊號右鍵「合併至群組」可放入；群組右鍵「合併至群組」成為子群組。\n"
            "【標注】波形右鍵 →「在此建立錨點」(吸附到最近的格邊緣)。\n"
            "  · 游標移到錨點上會高亮；按住錨點拖曳到另一錨點即建立關係線\n"
            "    (拉線時波形會反灰冷凍，凸顯前景)；放開後輸入標籤 (如 t_su)。\n"
            "  · 錨點/關係線：游標移上去高亮後按 Del 刪除；關係線右鍵可改標籤/箭頭樣式。\n"
            "【拖曳模式】按 Esc 退回拖曳模式（取消元件選擇、清除框選）：\n"
            "  · 左鍵拖曳 = 平移畫布（不會誤畫元件）。\n"
            "  · Shift/Ctrl + 左鍵拖曳 = 框選（與繪製模式相同）。\n"
            "  · 點元件鈕或按 1~6 數字鍵即回到繪製模式。\n"
            "【位移】右移 offset 後左緣自動延伸第一格準位、右端裁齊，呈現延續感。\n"
            "【匯出】圖片 PNG(1–4×)/SVG(向量)/EPS；另可匯出 WaveDrom JSON 交換格式。\n"
            "【其他】波形右鍵亦可「清成 L」；雙擊名稱改名；Esc 退回拖曳模式並清除框選。")

    def help_keys(self):
        messagebox.showinfo("快捷鍵",
            "Ctrl+N/O/S/E 新增/開啟/儲存/匯出   Ctrl+C/V 複製/貼上\n"
            "Ctrl+Z/Y 復原/重做（最近 5 步；一次筆刷/填入/貼上=一步）\n"
            "1~6 切換元件 (CLK/H/L/BUS/HiZ/Unknown)\n"
            "Esc 拖曳模式(取消元件選擇/清除框選)；拖曳模式下左鍵拖曳=平移畫布\n"
            "Shift/Ctrl+拖曳 框選(兩種模式皆可)   按元件鍵=填入框選\n"
            "名稱欄 Ctrl/Shift+點擊 多選 -> 右鍵選單(調色/位移/群組/改名/刪除)\n"
            "波形右鍵 建立錨點/清成L；拖曳錨點拉關係線；Del 刪除標注\n"
            "雙擊名稱 改名")

    def help_about(self):
        messagebox.showinfo("關於", f"RetroWave v{__version__}\n數位電路波型繪製工具\nPython + tkinter")


def main():
    App().mainloop()
