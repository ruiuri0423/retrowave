# -*- coding: utf-8 -*-
"""
RetroWave - 數位電路波型繪製工具 (原型 v1.7)
本版重點 :
  1. 所有轉換線斜率統一 = 擺幅/tw (BUS↔HiZ 不再不一致)。
  2/3/4. BUS 拖曳：原為 BUS 的格保留延續、非 BUS 的格才取代 (不蓋既有資料)。
  5. Ctrl+拖曳框選 -> Ctrl+C/V 複製貼上；貼上超出列數自動新增列。
  6. 名稱欄 Ctrl/Shift 多選訊號，位移欄一次套用到所有選取訊號。
  7. 移除「選取」鈕，改用 Shift/Ctrl 修飾鍵 (Windows 慣例)。

風格 : Windows 95/XP 米白主題    框架 : Python 標準庫 tkinter
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, colorchooser
import json
import os

SHIFT_MASK = 0x0001
CTRL_MASK = 0x0004


class Style:
    FACE = "#ECE9D8"; FACE_DARK = "#ACA899"; CANVAS_BG = "#FBFBF6"
    GRID = "#C8C8C8"; DASH = "#B9B9A8"; WAVE = "#101010"; TEXT = "#202020"
    SEL = "#BFD9FF"; UNK_FILL = "#E79B9B"; UNK_HATCH = "#A83232"
    MARQUEE = "#1F5FBF"; MARQUEE_FILL = "#3A6EA5"
    UI_FONT = ("Tahoma", 9); KEY_FONT = ("Tahoma", 9, "bold")
    NAME_FONT = ("Tahoma", 9, "bold"); LABEL_FONT = ("Consolas", 9, "bold")
    BUS_FONT = ("Consolas", 9)


def make_key_button(parent, text, command, width=None):
    b = tk.Button(parent, text=text, command=command, font=Style.KEY_FONT,
                  bg=Style.FACE, activebackground="#F5F3E7",
                  relief=tk.RAISED, bd=3, padx=8, pady=3, highlightthickness=0)
    if width:
        b.configure(width=width)
    return b


WAVE_TYPES = ["CLK", "H", "L", "BUS", "HiZ", "Unknown"]
DEFAULT_PERIODS = 12


class Geometry:
    def __init__(self):
        self.period_w = 84; self.row_h = 64; self.header_h = 26
        self.name_w = 150; self.ramp_ratio = 0.20
        self.level_hi = 0.20; self.level_lo = 0.80

    def tw(self):
        return min(self.period_w * self.ramp_ratio, self.period_w * 0.45)

    def levels(self, row_top):
        hi = row_top + self.level_hi * self.row_h
        lo = row_top + self.level_lo * self.row_h
        return hi, (hi + lo) / 2.0, lo

    def to_dict(self):
        return {"period_w": self.period_w, "row_h": self.row_h, "ramp_ratio": self.ramp_ratio,
                "level_hi": self.level_hi, "level_lo": self.level_lo}

    def load(self, d):
        self.period_w = int(d.get("period_w", self.period_w))
        self.row_h = int(d.get("row_h", self.row_h))
        self.ramp_ratio = float(d.get("ramp_ratio", self.ramp_ratio))
        self.level_hi = float(d.get("level_hi", self.level_hi))
        self.level_lo = float(d.get("level_lo", self.level_lo))


class Model:
    def __init__(self):
        self.n_periods = DEFAULT_PERIODS; self.signals = []
        self.groups = {}              # gid -> {name, collapsed, color}
        self._gid_seq = 0
        self.add_signal("CLK", fill="CLK")
        self.add_signal("RST_N", fill="H")
        self.add_signal("DATA", fill="L")
        self._demo()

    def _demo(self):
        d = self.signals[2]["cells"]
        d[2] = self.new_cell("BUS", "A5"); d[3] = self.new_cell("BUS", "A5")
        d[4] = self.new_cell("BUS", "0F"); d[5] = self.new_cell("HiZ")
        d[6] = self.new_cell("BUS", "0x4"); d[7] = self.new_cell("H"); d[8] = self.new_cell("L")

    def new_cell(self, t="L", text=""):
        return {"type": t, "text": text}

    def add_signal(self, name=None, fill="L"):
        if name is None:
            name = f"SIG{len(self.signals)}"
        self.signals.append({"name": name, "offset": 0.0, "color": None, "group": None,
                             "cells": [self.new_cell(fill) for _ in range(self.n_periods)]})

    def remove_signal(self, idx):
        if 0 <= idx < len(self.signals):
            del self.signals[idx]

    def set_n_periods(self, n):
        n = max(1, int(n))
        if n > self.n_periods:
            for s in self.signals:
                s["cells"] += [self.new_cell("L") for _ in range(n - self.n_periods)]
        elif n < self.n_periods:
            for s in self.signals:
                del s["cells"][n:]
        self.n_periods = n

    def set_cell(self, sig, per, t, text=""):
        if 0 <= sig < len(self.signals) and 0 <= per < self.n_periods:
            self.signals[sig]["cells"][per] = self.new_cell(t, text)

    # ---- 群組 (視圖/標籤層；訊號本體仍只存在 self.signals) ----
    def layout(self):
        """回傳可見列清單：[('group', gid) | ('sig', signal_index), ...]。
        每次重繪即時重建，訊號列只放整數索引 (直接陣列定址，非搜尋/雜湊)。"""
        rows = []; i = 0; n = len(self.signals)
        while i < n:
            g = self.signals[i].get("group")
            if g and g in self.groups:
                rows.append(("group", g))
                collapsed = self.groups[g].get("collapsed", False)
                j = i
                while j < n and self.signals[j].get("group") == g:
                    if not collapsed:
                        rows.append(("sig", j))
                    j += 1
                i = j
            else:
                rows.append(("sig", i)); i += 1
        return rows

    def new_gid(self):
        self._gid_seq += 1
        gid = f"g{self._gid_seq}"
        while gid in self.groups:
            self._gid_seq += 1; gid = f"g{self._gid_seq}"
        return gid

    def group_signals(self, indices, name=None):
        """建立新群組：把選取訊號移出原群組、聚攏相鄰、組成全新群組。
        永遠新建 (不自動合併)；回傳 (gid, 新的連續索引清單)。"""
        idxs = sorted({i for i in indices if 0 <= i < len(self.signals)})
        if not idxs:
            return None
        block = [self.signals[i] for i in idxs]
        for i in reversed(idxs):
            del self.signals[i]
        at = idxs[0]
        # 避免新組插進某既有群組的連續區段中間 -> 若會分裂，移到該區段結尾
        if 0 < at < len(self.signals):
            gp = self.signals[at - 1].get("group")
            if gp and self.signals[at].get("group") == gp:
                while at < len(self.signals) and self.signals[at].get("group") == gp:
                    at += 1
        gid = self.new_gid()
        for s in block:
            s["group"] = gid
        self.signals[at:at] = block
        self.groups[gid] = {"name": name or f"群組{self._gid_seq}", "collapsed": False, "color": None}
        self.prune_groups()                # 舊群組若被掏空則移除
        return gid, list(range(at, at + len(block)))

    def merge_into_group(self, indices, target_gid):
        """把選取訊號併入指定群組 (置於該群尾端、維持相鄰)。
        已在該群者略過 (併入當前群組 = 無動作)。回傳 (gid, 新位置)。"""
        if target_gid not in self.groups:
            return None
        sel = sorted({i for i in indices
                      if 0 <= i < len(self.signals) and self.signals[i].get("group") != target_gid})
        if not sel:
            return target_gid, []
        block = [self.signals[i] for i in sel]
        for i in reversed(sel):
            del self.signals[i]
        for s in block:
            s["group"] = target_gid
        last = max((k for k, s in enumerate(self.signals) if s.get("group") == target_gid),
                   default=len(self.signals) - 1)
        at = last + 1
        self.signals[at:at] = block
        self.prune_groups()
        return target_gid, list(range(at, at + len(block)))

    def merge_groups(self, src_gid, target_gid):
        if src_gid == target_gid or src_gid not in self.groups or target_gid not in self.groups:
            return None
        idxs = [i for i, s in enumerate(self.signals) if s.get("group") == src_gid]
        return self.merge_into_group(idxs, target_gid)

    def remove_from_group(self, indices):
        """把選取的(有群組)訊號逐一移出其群組，置於原群尾端以維持相鄰；
        移出後 color 設回預設(黑)。回傳被移出的數量。"""
        idxs = sorted({i for i in indices
                       if 0 <= i < len(self.signals) and self.signals[i].get("group")})
        if not idxs:
            return 0
        block = [self.signals[i] for i in idxs]
        for i in reversed(idxs):
            del self.signals[i]
        moved = len(block)
        for s in block:
            fg = s.get("group")
            s["group"] = None; s["color"] = None       # 移出後回預設色
            last = max((k for k, t in enumerate(self.signals) if t.get("group") == fg),
                       default=-1)
            at = last + 1 if last != -1 else len(self.signals)
            self.signals[at:at] = [s]
        self.prune_groups()
        return moved

    def ungroup(self, gids):
        gids = set(gids)
        for s in self.signals:
            if s.get("group") in gids:
                s["group"] = None
        for g in gids:
            self.groups.pop(g, None)

    def prune_groups(self):
        used = {s.get("group") for s in self.signals}
        for g in list(self.groups):
            if g not in used:
                del self.groups[g]

    def to_dict(self):
        return {"version": "1.4", "n_periods": self.n_periods,
                "signals": self.signals, "groups": self.groups}

    def load_dict(self, d):
        self.n_periods = int(d.get("n_periods", DEFAULT_PERIODS))
        self.signals = d.get("signals", [])
        self.groups = d.get("groups", {})
        self._gid_seq = len(self.groups)
        for s in self.signals:
            s.setdefault("offset", 0.0)
            s.setdefault("color", None)
            s.setdefault("group", None)
            cells = s.get("cells", [])
            while len(cells) < self.n_periods:
                cells.append(self.new_cell("L"))
            del cells[self.n_periods:]
            s["cells"] = cells
        self.prune_groups()


# ============================================================================
# 元件類別階層 (轉換線斜率統一 = 擺幅/tw)
# ============================================================================
class Element:
    name = ""; kind = "NONE"; accepts_text = False
    def exit_y(self, hi, mid, lo):  return None
    def entry_y(self, hi, mid, lo): return None
    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo): pass


class LevelElement(Element):
    kind = "LEVEL"
    def y(self, hi, mid, lo): raise NotImplementedError
    def exit_y(self, hi, mid, lo):  return self.y(hi, mid, lo)
    def entry_y(self, hi, mid, lo): return self.y(hi, mid, lo)

    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo):
        pw = geom.period_w; x1 = x0 + pw; tw = geom.tw(); W = 2; col = eng._wcol
        swing = lo - hi
        y = self.y(hi, mid, lo)
        pe = eng.elem(prev["type"]) if prev else None
        if pe is None:
            cv.create_line(x0, y, x1, y, fill=col, width=W)
        elif pe.kind == "DATA":                         # 前為 BUS：兩軌道收斂到本準位 (線右側, 統一斜率)
            whi = abs(hi - y) * tw / swing; wlo = abs(lo - y) * tw / swing
            xflat = x0 + min(whi, wlo)
            cv.create_line(xflat, y, x1, y, fill=col, width=W)
            if whi > 0.5: cv.create_line(x0, hi, x0 + whi, y, fill=col, width=W)
            if wlo > 0.5: cv.create_line(x0, lo, x0 + wlo, y, fill=col, width=W)
        elif pe.kind == "CLK":                          # CLK<->LEVEL：直角
            if abs(lo - y) > 0.5:
                cv.create_line(x0, lo, x0, y, fill=col, width=W)
            cv.create_line(x0, y, x1, y, fill=col, width=W)
        else:                                           # LEVEL<->LEVEL：統一斜率
            py = pe.exit_y(hi, mid, lo); dy = y - py
            if abs(dy) < 0.5:
                cv.create_line(x0, y, x1, y, fill=col, width=W)
            else:
                w = abs(dy) / swing * tw
                cv.create_line(x0, py, x0 + w, y, fill=col, width=W)
                cv.create_line(x0 + w, y, x1, y, fill=col, width=W)


class HighElement(LevelElement):
    name = "H"
    def y(self, hi, mid, lo): return hi


class LowElement(LevelElement):
    name = "L"
    def y(self, hi, mid, lo): return lo


class HiZElement(LevelElement):
    name = "HiZ"
    def y(self, hi, mid, lo): return mid


class ClkElement(Element):
    name = "CLK"; kind = "CLK"
    def exit_y(self, hi, mid, lo): return lo

    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo):
        pw = geom.period_w; x1 = x0 + pw; xm = x0 + pw / 2; W = 2; col = eng._wcol
        pt = prev["type"] if prev else None
        rise = eng.meet(pt, "CLK", hi, mid, lo) if pt else lo
        if rise is None:
            rise = lo
        if abs(rise - hi) > 0.5:
            cv.create_line(x0, rise, x0, hi, fill=col, width=W)
        cv.create_line(x0, hi, xm, hi, fill=col, width=W)
        cv.create_line(xm, hi, xm, lo, fill=col, width=W)
        cv.create_line(xm, lo, x1, lo, fill=col, width=W)


class BusElement(Element):
    name = "BUS"; kind = "DATA"; accepts_text = True
    fill = None; hatch = False; text_color = Style.TEXT

    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo):
        pw = geom.period_w; x1 = x0 + pw; tw = geom.tw(); W = 2; col = eng._wcol
        swing = lo - hi
        def wl(dv): return abs(dv) * tw / swing
        pt = prev["type"] if prev else None
        nt = nxt["type"] if nxt else None
        pe = eng.elem(pt); ne = eng.elem(nt)
        sameL = eng.same_data(prev, cell); sameR = eng.same_data(cell, nxt)
        trailing = (not sameR) and (ne is None or ne.kind == "CLK")
        prevDATA = (pe is not None and pe.kind == "DATA") and not sameL

        left_lines = []
        vyL = None
        if sameL:
            xLhi = xLlo = x0
        elif prevDATA:                                  # 資料變化 X 交叉
            xm = x0 + tw / 2
            left_lines += [(x0, hi, xm, mid), (x0, lo, xm, mid),
                           (xm, mid, x0 + tw, hi), (xm, mid, x0 + tw, lo)]
            xLhi = xLlo = x0 + tw
        else:                                           # 由 level/clk/none 開口
            vyL = eng.meet(pt, self.name, hi, mid, lo) or mid
            whi = wl(hi - vyL); wlo = wl(lo - vyL)
            if whi > 0.5: left_lines.append((x0, vyL, x0 + whi, hi))
            if wlo > 0.5: left_lines.append((x0, vyL, x0 + wlo, lo))
            xLhi = x0 + whi; xLlo = x0 + wlo

        right_lines = []
        if trailing:
            vyR = eng.meet(self.name, nt, hi, mid, lo) or mid
            whi = wl(hi - vyR); wlo = wl(lo - vyR)
            xRhi = x1 - whi; xRlo = x1 - wlo
            if whi > 0.5: right_lines.append((x1 - whi, hi, x1, vyR))
            if wlo > 0.5: right_lines.append((x1 - wlo, lo, x1, vyR))
        else:
            xRhi = xRlo = x1

        if self.fill:
            poly = []
            if sameL or prevDATA:
                poly += [x0, hi]; bl = [x0, lo]
            else:
                poly += [x0, vyL, xLhi, hi]; bl = [xLlo, lo]
            if trailing:
                poly += [xRhi, hi, x1, vyR, xRlo, lo]
            else:
                poly += [x1, hi, x1, lo]
            poly += bl
            cv.create_polygon(poly, fill=self.fill, outline="")
            hxL = min(xLhi, xLlo); hxR = max(xRhi, xRlo); xt = hxL - swing
            while xt < hxR:
                xs = max(xt, hxL); xe = min(xt + swing, hxR)
                if xs < xe:
                    cv.create_line(xs, hi + (xs - xt), xe, hi + (xe - xt),
                                   fill=Style.UNK_HATCH, width=1)
                xt += 7

        cv.create_line(xLhi, hi, xRhi, hi, fill=col, width=W)
        cv.create_line(xLlo, lo, xRlo, lo, fill=col, width=W)
        for ln in left_lines + right_lines:
            cv.create_line(*ln, fill=col, width=W)
        if self.accepts_text and cell.get("text") and not sameL:
            cv.create_text((x0 + x1) / 2, mid, text=cell["text"],
                           font=Style.BUS_FONT, fill=self.text_color)


class UnknownElement(BusElement):
    name = "Unknown"; accepts_text = False
    fill = Style.UNK_FILL; hatch = True; text_color = "#3A0000"


# ============================================================================
# 繪圖引擎
# ============================================================================
class Engine:
    def __init__(self):
        self.elements = {e.name: e for e in (
            HighElement(), LowElement(), HiZElement(),
            ClkElement(), BusElement(), UnknownElement())}
        self._wcol = Style.WAVE

    def elem(self, t):
        return self.elements.get(t)

    def meet(self, Lt, Rt, hi, mid, lo):
        eL = self.elements[Lt].exit_y(hi, mid, lo) if Lt in self.elements else None
        eR = self.elements[Rt].entry_y(hi, mid, lo) if Rt in self.elements else None
        if eL is not None and eR is not None:
            return eL if eL == eR else None
        if eL is not None: return eL
        if eR is not None: return eR
        return mid

    @staticmethod
    def same_data(a, b):
        return bool(a and b and a["type"] == b["type"]
                    and a["type"] in ("BUS", "Unknown")
                    and a.get("text", "") == b.get("text", ""))

    def draw(self, name_cv, wave_cv, model, sig_sel, geom, cell_sel=None):
        name_cv.delete("all"); wave_cv.delete("all")
        n = len(model.signals); npd = model.n_periods
        HH, RH, PW, NW = geom.header_h, geom.row_h, geom.period_w, geom.name_w
        rows = model.layout()
        total_h = HH + len(rows) * RH; grid_w = npd * PW
        max_off = max((s.get("offset", 0.0) for s in model.signals), default=0.0)
        wave_cv.configure(scrollregion=(0, 0, max(grid_w + max_off * PW, 10), max(total_h, 10)))
        name_cv.configure(scrollregion=(0, 0, NW, max(total_h, 10)))

        name_cv.create_rectangle(0, 0, NW, HH, fill=Style.FACE, outline=Style.FACE_DARK)
        name_cv.create_text(NW // 2, HH // 2, text="SIGNAL", font=Style.UI_FONT, fill=Style.TEXT)
        for p in range(npd):
            x = p * PW
            wave_cv.create_text(x + PW / 2, HH / 2, text=f"T{p}", font=Style.LABEL_FONT, fill=Style.TEXT)
            wave_cv.create_line(x, HH, x, total_h, fill=Style.DASH, dash=(2, 3))
        wave_cv.create_line(grid_w, HH, grid_w, total_h, fill=Style.DASH, dash=(2, 3))
        wave_cv.create_line(0, HH, grid_w, HH, fill=Style.GRID)

        sig_row = {}                       # signal index -> 可見列 (給 cell_sel 高亮)
        for r, (kind, ref) in enumerate(rows):
            row_top = HH + r * RH; row_bot = row_top + RH
            if kind == "group":            # ---- 群組標頭列 ----
                meta = model.groups.get(ref, {})
                gcol = meta.get("color")
                tri = "▸" if meta.get("collapsed") else "▾"
                name_cv.create_rectangle(0, row_top, NW, row_bot, fill=Style.FACE, outline=Style.FACE_DARK)
                name_cv.create_text(8, (row_top + row_bot) // 2,
                                    text=f"{tri} {meta.get('name', ref)}",
                                    anchor="w", font=Style.NAME_FONT, fill=(gcol or Style.TEXT))
                wave_cv.create_rectangle(0, row_top, grid_w, row_bot, fill=Style.FACE, outline="")
                if gcol:
                    wave_cv.create_rectangle(0, row_top, grid_w, row_top + 3, fill=gcol, outline="")
                wave_cv.create_line(0, row_bot, grid_w, row_bot, fill=Style.GRID)
                continue
            si = ref; sig = model.signals[si]; sig_row[si] = r    # ---- 訊號列 ----
            hi, mid, lo = geom.levels(row_top)
            ox = sig.get("offset", 0.0) * PW
            gcol = model.groups.get(sig.get("group"), {}).get("color") if sig.get("group") else None
            self._wcol = sig.get("color") or gcol or Style.WAVE   # 自訂色 > 群組色 > 預設
            namecol = sig.get("color") or gcol or Style.TEXT
            indent = 20 if sig.get("group") else 8
            if si in sig_sel:
                name_cv.create_rectangle(0, row_top, NW, row_bot, fill=Style.SEL, outline="")
            name_cv.create_rectangle(0, row_top, NW, row_bot,
                                     fill="" if si in sig_sel else Style.CANVAS_BG, outline=Style.GRID)
            label = sig["name"] + (f"  Δ{sig['offset']:.2f}" if sig.get("offset") else "")
            name_cv.create_text(indent, (row_top + row_bot) // 2, text=label,
                                anchor="w", font=Style.NAME_FONT, fill=namecol)
            wave_cv.create_line(0, row_bot, grid_w, row_bot, fill=Style.GRID)
            cells = sig["cells"]
            for p in range(npd):
                pc = cells[p - 1] if p > 0 else None
                nc = cells[p + 1] if p < npd - 1 else None
                el = self.elem(cells[p]["type"])
                if el:
                    el.draw(self, wave_cv, geom, cells[p], pc, nc, p * PW + ox, hi, mid, lo)

        if cell_sel:
            s0, s1, p0, p1 = cell_sel
            for s in range(s0, s1 + 1):
                if s in sig_row:           # 折疊隱藏的列跳過
                    ox = model.signals[s].get("offset", 0.0) * PW
                    y0 = HH + sig_row[s] * RH; y1 = y0 + RH
                    wave_cv.create_rectangle(p0 * PW + ox, y0, (p1 + 1) * PW + ox, y1,
                                             fill=Style.MARQUEE_FILL, stipple="gray12",
                                             outline=Style.MARQUEE, dash=(3, 2), width=1)


# ============================================================================
# PNG 匯出：Pillow 轉接層 (重用 Engine 的繪圖邏輯，不需 Ghostscript)
# ----------------------------------------------------------------------------
#   PILCanvas 把 tkinter Canvas 的 create_* 介面對應到 Pillow ImageDraw，
#   因此 Engine.draw 與各元件 draw() 可原封不動畫到影像上。
# ============================================================================
def _load_pil_fonts():
    from PIL import ImageFont
    reg_cands = ["msjh.ttc", "msyh.ttc", "mingliu.ttc", "NotoSansCJKtc-Regular.otf",
                 "PingFang.ttc", "tahoma.ttf", "arial.ttf", "DejaVuSans.ttf"]
    bold_cands = ["msjhbd.ttc", "msyhbd.ttc", "tahomabd.ttf", "arialbd.ttf",
                  "DejaVuSans-Bold.ttf"] + reg_cands

    def pick(cands, size):
        for c in cands:
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
        return ImageFont.load_default()
    return {"reg": pick(reg_cands, 12), "bold": pick(bold_cands, 12)}


class PILCanvas:
    """最小化的 tkinter Canvas 介面，實際畫到 Pillow ImageDraw。"""
    def __init__(self, draw, fonts):
        self.d = draw
        self.fonts = fonts

    @staticmethod
    def _c(v):
        return None if v in (None, "") else v

    def _font(self, f):
        bold = isinstance(f, (tuple, list)) and "bold" in f
        return self.fonts["bold"] if bold else self.fonts["reg"]

    def create_line(self, *coords, fill=None, width=1, dash=None, **kw):
        f = self._c(fill)
        if f:
            self.d.line(list(coords), fill=f, width=max(1, int(width)))

    def create_rectangle(self, x0, y0, x1, y1, fill=None, outline=None,
                         width=1, dash=None, stipple=None, **kw):
        f = self._c(fill); o = self._c(outline)
        if f or o:
            self.d.rectangle([x0, y0, x1, y1], fill=f, outline=o)

    def create_polygon(self, pts, fill=None, outline=None, **kw):
        self.d.polygon(list(pts), fill=self._c(fill), outline=self._c(outline))

    def create_text(self, x, y, text="", font=None, fill=None, anchor="center", **kw):
        f = self._c(fill) or "#000000"
        anc = {"center": "mm", "w": "lm", "e": "rm"}.get(anchor, "mm")
        try:
            self.d.text((x, y), str(text), fill=f, font=self._font(font), anchor=anc)
        except TypeError:                       # 舊版 Pillow 無 anchor 參數
            self.d.text((x, y), str(text), fill=f, font=self._font(font))

    def configure(self, **kw):
        pass

    def delete(self, *a):
        pass


# ============================================================================
# 範本庫 (獨立於專案檔；索引存使用者目錄，記錄各範本 JSON 的路徑)
# ============================================================================
class TemplateLibrary:
    DIR = os.path.join(os.path.expanduser("~"), ".retrowave")
    INDEX = os.path.join(DIR, "templates_index.json")

    def __init__(self):
        self.entries = []                      # [{name, path}]

    def load(self):
        """讀索引檔，回傳 (可用清單, 找不到的清單)。找不到的會自動從索引移除。"""
        try:
            with open(self.INDEX, encoding="utf-8") as f:
                items = json.load(f).get("templates", [])
        except Exception:
            items = []
        avail, missing = [], []
        for it in items:
            p = it.get("path")
            nm = it.get("name") or (os.path.splitext(os.path.basename(p))[0] if p else "範本")
            (avail if (p and os.path.isfile(p)) else missing).append({"name": nm, "path": p})
        self.entries = avail
        if missing:
            self.save()                        # 更新路徑檔，去掉找不到的
        return avail, missing

    def save(self):
        try:
            os.makedirs(self.DIR, exist_ok=True)
            with open(self.INDEX, "w", encoding="utf-8") as f:
                json.dump({"templates": self.entries}, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def add(self, name, path):
        self.entries = [e for e in self.entries if e.get("path") != path]   # 同路徑去重
        self.entries.append({"name": name, "path": path}); self.save()

    def remove(self, name):
        self.entries = [e for e in self.entries if e.get("name") != name]; self.save()

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)


# ============================================================================
# 介面層
# ============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RetroWave - 數位波型繪製工具  v1.7")
        self.geometry("1160x660"); self.minsize(900, 470)
        self.configure(bg=Style.FACE)
        self.model = Model(); self.geom = Geometry(); self.engine = Engine()
        self.active_tool = "H"; self.tool_btns = {}
        self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
        self.cell_sel = None; self.clip = None; self.clip_signals = None
        self.clip_group = None
        self._clip_kind = None; self._copy_ctx = "cells"
        self._press = None; self._press_xy = (0, 0); self._moved = False
        self._marquee = None; self._selecting = False
        self._drag_value = None; self._hover = None
        self.lib = TemplateLibrary()
        self._build_menubar(); self._build_toolbar(); self._build_main()
        self._build_statusbar(); self._bind_keys()
        self._set_tool("H"); self.render()
        self.after(150, self._startup_templates)    # 視窗顯示後再載入範本/提示缺檔

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
        sigs = self.model.signals; npd = self.model.n_periods
        at = len(sigs)                          # 範本插在末端 (整塊、可預期)
        gid = self.model.new_gid()
        gname = self._unique_name(entry["name"], {me.get("name") for me in self.model.groups.values()})
        names = {s["name"] for s in sigs}
        block = []
        for ts in tsignals:
            ns = {"name": ts.get("name", "SIG"), "offset": float(ts.get("offset", 0.0)),
                  "color": ts.get("color"), "group": gid,
                  "cells": [{"type": c.get("type", "L"), "text": c.get("text", "")}
                            for c in ts.get("cells", [])]}
            ns["name"] = self._unique_name(ns["name"], names); names.add(ns["name"])
            while len(ns["cells"]) < npd:
                ns["cells"].append(self.model.new_cell("L"))
            del ns["cells"][npd:]
            block.append(ns)
        sigs[at:at] = block
        self.model.groups[gid] = {"name": gname, "collapsed": False, "color": None}
        self.sig_sel = set(range(at, at + len(block))); self.selected = at; self._sig_anchor = at
        self.render()
        self.status.configure(text=f" 已插入範本「{gname}」（{len(block)} 條，已成群組）")

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
        self.render()

    def _apply_periods(self):
        try:
            n = max(1, int(float(self.sp_p.get())))
        except ValueError:
            return
        self.model.set_n_periods(n); self.cell_sel = None; self.render()

    def set_offset_dialog(self):
        if not self.model.signals:
            return
        cur = self.model.signals[self.selected].get("offset", 0.0)
        v = simpledialog.askfloat("設定位移", "位移 (0 ~ 0.95 週期):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        for s in (self.sig_sel or {self.selected}):
            if 0 <= s < len(self.model.signals):
                self.model.signals[s]["offset"] = round(v, 2)
        self.render()

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
        self.wave_cv.bind("<Button-3>", self.on_erase)
        self.wave_cv.bind("<Motion>", self.on_hover)
        self.name_cv.bind("<Button-1>", self.on_name_click)
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
        self.bind("<Escape>", lambda e: self._clear_cell_sel())

        def keyed(fn):
            def handler(e):
                if self._is_typing():
                    return
                fn()
            return handler
        for i, t in enumerate(WAVE_TYPES, start=1):
            self.bind(str(i), keyed(lambda x=t: self._set_tool(x)))

    def _yview(self, *a):
        self.wave_cv.yview(*a); self.name_cv.yview(*a)

    def _on_wheel(self, e):
        d = -1 if (getattr(e, "delta", 0) > 0 or e.num == 4) else 1
        self.wave_cv.yview_scroll(d, "units"); self.name_cv.yview_scroll(d, "units")

    # ---- 工具 ----
    def _set_tool(self, t):
        if self.cell_sel is not None:          # 有框選 -> 填入該範圍
            self._fill_selection(t); return
        self.active_tool = t; self._refresh_tools(); self.render()

    def _refresh_tools(self):
        for k, b in self.tool_btns.items():
            on = (k == self.active_tool)
            b.configure(relief=tk.SUNKEN if on else tk.RAISED, bg="#DAD7C2" if on else Style.FACE)

    def _clear_cell_sel(self):
        if self.cell_sel is not None:
            self.cell_sel = None; self.render()

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
        for s in range(s0, s1 + 1):
            for p in range(p0, p1 + 1):
                self.model.set_cell(s, p, payload[0], payload[1])
        return f"已填入 {payload[0]}" + (f" = '{payload[1]}'" if payload[0] == "BUS" else "")

    def _fill_selection(self, t):
        if self.cell_sel is None:
            return
        msg = self._fill_rect(self.cell_sel, t)
        if msg:
            self.render(); self.status.configure(text=" " + msg + "（選取保留，Esc 清除）")

    def _update_status(self):
        if self.active_tool == "BUS":
            hint = "點/拖曳=畫BUS(原為BUS保留, 非BUS取代);再點同格=改值"
        else:
            hint = "點/拖曳上色(鎖列)"
        self.status.configure(
            text=f" 筆刷:{self.active_tool} | {hint} | Shift/Ctrl拖曳=框選(按元件鍵填入/Ctrl+C複製) "
                 f"| 名稱Ctrl/Shift多選 -> 右鍵: 調色/位移/刪除 | 週期{self.model.n_periods}")

    def render(self):
        self.name_cv.configure(width=self.geom.name_w)
        self.engine.draw(self.name_cv, self.wave_cv, self.model, self.sig_sel, self.geom, self.cell_sel)
        self._update_status()

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
        kind, ref = rows[r]
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
        self._hover = self._cell_from_xy(*self._ev_xy(e))

    def on_press(self, e):
        self.wave_cv.focus_set()
        cx, cy = self._ev_xy(e)
        self._press_xy = (cx, cy)
        self._press = self._cell_from_xy(cx, cy)
        self._moved = False
        ctrl = bool(e.state & CTRL_MASK); shift = bool(e.state & SHIFT_MASK)
        self._selecting = ctrl or shift          # Shift/Ctrl 拖曳皆為純框選
        if self._press:
            self.selected = self._press[0]
        self._drag_value = None
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
            self.cell_sel = None; self.render()

    def on_motion(self, e):
        cx, cy = self._ev_xy(e)
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
            self.render()

    def on_release(self, e):
        cx, cy = self._ev_xy(e)
        if self._selecting:
            a = self._cell_from_xy(*self._press_xy, clamp=True)
            b = self._cell_from_xy(cx, cy, clamp=True)
            if a and b:
                s0, s1 = sorted((a[0], b[0])); p0, p1 = sorted((a[1], b[1]))
                self.cell_sel = (s0, s1, p0, p1)
                self._copy_ctx = "cells"
            self._erase_marquee(); self.render()
            if self.cell_sel:
                self.status.configure(text=" 已框選；按元件鍵填入、或 Ctrl+C 複製")
        else:
            if not self._moved and self._press:
                self._click_cell(*self._press)
            self.render()

    def on_erase(self, e):
        cur = self._cell_from_xy(*self._ev_xy(e))
        if cur:
            self.model.set_cell(cur[0], cur[1], "L"); self.render()

    def _paint_cell(self, s, p, t, drag_value=None):
        cells = self.model.signals[s]["cells"]
        if t == "BUS":
            if cells[p]["type"] == "BUS":           # 原為 BUS -> 保留延續，不覆蓋
                return
            if drag_value is not None:
                text = drag_value
            else:
                text = cells[p - 1]["text"] if (p > 0 and cells[p - 1]["type"] == "BUS") else ""
            self.model.set_cell(s, p, "BUS", text)
        elif t == "Unknown":
            self.model.set_cell(s, p, "Unknown", "")
        else:
            self.model.set_cell(s, p, t)

    def _click_cell(self, s, p):
        t = self.active_tool
        cells = self.model.signals[s]["cells"]
        if t == "BUS" and cells[p]["type"] == "BUS":     # 已是 BUS -> 改值
            cur = cells[p].get("text", "")
            new = simpledialog.askstring("BUS 資料", "輸入資料值:", initialvalue=cur, parent=self)
            if new is not None:
                self.model.set_cell(s, p, "BUS", new)
        else:
            self._paint_cell(s, p, t, self._drag_value)

    # ---- 複製 / 貼上 (波形級 + 訊號級) ----
    @staticmethod
    def _copy_signal(sig):
        return {"name": sig["name"], "offset": sig.get("offset", 0.0),
                "color": sig.get("color"),
                "cells": [{"type": c["type"], "text": c.get("text", "")} for c in sig["cells"]]}

    @staticmethod
    def _unique_name(name, existing):
        if name not in existing:
            return name
        i = 2
        while f"{name}_{i}" in existing:
            i += 1
        return f"{name}_{i}"

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
            sigs = self.model.signals
            at = self.selected + 1
            if 0 <= self.selected < len(sigs):       # 若選取列在群組中，插到該群尾端(不分裂群組)
                g = sigs[self.selected].get("group")
                if g:
                    j = self.selected
                    while j < len(sigs) and sigs[j].get("group") == g:
                        j += 1
                    at = j
            names = {s["name"] for s in sigs}
            for k, sig in enumerate(self.clip_signals):
                ns = self._copy_signal(sig)
                ns["name"] = self._unique_name(ns["name"], names); names.add(ns["name"])
                ns["group"] = None                   # 複本預設不分組(群組級複製留待 Phase C)
                cells = ns["cells"]
                while len(cells) < self.model.n_periods:
                    cells.append(self.model.new_cell("L"))
                del cells[self.model.n_periods:]
                sigs.insert(at + k, ns)
            self.selected = at
            self.sig_sel = set(range(at, at + len(self.clip_signals))); self._sig_anchor = at
            self._refresh_offset_field(); self.render()
            self.status.configure(text=f" 已貼上 {len(self.clip_signals)} 條訊號（複本未分組）")
        elif self._clip_kind == "cells" and self.clip:
            s0, p0 = self._hover or (self.selected, 0)
            while len(self.model.signals) < s0 + len(self.clip):
                self.model.add_signal()
            for ds, row in enumerate(self.clip):
                for dp, c in enumerate(row):
                    self.model.set_cell(s0 + ds, p0 + dp, c["type"], c.get("text", ""))
            self.render(); self.status.configure(text=f" 已貼上波形於 訊號{s0} T{p0}")

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
            for s in (self.sig_sel or {self.selected}):
                if 0 <= s < len(self.model.signals):
                    self.model.signals[s]["color"] = hx
            self.render()

    def clear_color(self):
        for s in (self.sig_sel or {self.selected}):
            if 0 <= s < len(self.model.signals):
                self.model.signals[s]["color"] = None
        self.render()

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

    # ---- 名稱欄 (Ctrl/Shift 多選訊號) ----
    def on_name_click(self, e):
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
        self._refresh_offset_field(); self.render()

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
            m.add_command(label="解散群組", command=lambda: self._dissolve_group(gid))
            try:
                m.tk_popup(e.x_root, e.y_root)
            finally:
                m.grab_release()
            return
        s = item[1]                          # ---- 訊號選單 ----
        if s not in self.sig_sel:
            self.sig_sel = {s}; self.selected = s; self._sig_anchor = s
            self.render()
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
                self.model.signals[s]["name"] = new; self.render()

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
        res = self.model.group_signals(idxs, name)
        if res:
            gid, newidx = res
            self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
            self.render()
            nm = self.model.groups.get(gid, {}).get("name", gid)
            self.status.configure(text=f" 已建立群組「{nm}」（{len(newidx)} 條）；點標頭可折疊")

    def _merge_selected_into(self, target_gid):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        res = self.model.merge_into_group(idxs, target_gid)
        if not res:
            return
        gid, newpos = res
        nm = self.model.groups.get(gid, {}).get("name", gid)
        if newpos:
            self.sig_sel = set(newpos); self.selected = newpos[0]; self._sig_anchor = newpos[0]
            self.render()
            self.status.configure(text=f" 已併入群組「{nm}」（{len(newpos)} 條）")
        else:
            self.status.configure(text=f" 選取訊號已在群組「{nm}」中，無變更")

    def _merge_group_into(self, src_gid, target_gid):
        res = self.model.merge_groups(src_gid, target_gid)
        if res:
            self.render()
            self.status.configure(
                text=f" 已將群組合併至「{self.model.groups.get(target_gid, {}).get('name', target_gid)}」")

    def _remove_from_group(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        moved = self.model.remove_from_group(idxs)
        self.render()
        self.status.configure(text=(f" 已移出 {moved} 條訊號（顏色回預設）" if moved
                                    else " 選取的訊號不在任何群組中"))

    def _dissolve_group(self, gid):
        for s in self.model.signals:        # 整組拆掉、成員回預設色
            if s.get("group") == gid:
                s["group"] = None; s["color"] = None
        self.model.groups.pop(gid, None)
        self.render()
        self.status.configure(text=" 已解散群組（成員保留、顏色回預設）")

    def _copy_group(self, gid):
        meta = self.model.groups.get(gid, {})
        members = [self._copy_signal(s) for s in self.model.signals if s.get("group") == gid]
        if not members:
            return
        self.clip_group = {"name": meta.get("name", gid), "color": meta.get("color"),
                           "signals": members}
        self._clip_kind = "group"
        self.status.configure(text=f" 已複製群組「{self.clip_group['name']}」（{len(members)} 條）；Ctrl+V 貼上")

    def _paste_group(self):
        if not self.clip_group:
            return
        cg = self.clip_group; sigs = self.model.signals; npd = self.model.n_periods
        at = self.selected + 1                  # 插在選取所屬群組尾端 (避免分裂)
        if 0 <= self.selected < len(sigs):
            g = sigs[self.selected].get("group")
            if g:
                j = self.selected
                while j < len(sigs) and sigs[j].get("group") == g:
                    j += 1
                at = j
        gid = self.model.new_gid()
        gname = self._unique_name(cg["name"], {me.get("name") for me in self.model.groups.values()})
        names = {s["name"] for s in sigs}
        block = []
        for sd in cg["signals"]:
            ns = self._copy_signal(sd)
            ns["name"] = self._unique_name(ns["name"], names); names.add(ns["name"])
            ns["group"] = gid
            while len(ns["cells"]) < npd:
                ns["cells"].append(self.model.new_cell("L"))
            del ns["cells"][npd:]
            block.append(ns)
        sigs[at:at] = block
        self.model.groups[gid] = {"name": gname, "collapsed": False, "color": cg.get("color")}
        self.sig_sel = set(range(at, at + len(block))); self.selected = at; self._sig_anchor = at
        self.render()
        self.status.configure(text=f" 已貼上群組「{gname}」（{len(block)} 條，新群組）")

    def _toggle_group(self, gid):
        meta = self.model.groups.get(gid)
        if meta is not None:
            meta["collapsed"] = not meta.get("collapsed", False); self.render()

    def _rename_group(self, gid):
        meta = self.model.groups.get(gid)
        if meta:
            new = simpledialog.askstring("群組改名", "群組名稱:",
                                         initialvalue=meta.get("name", gid), parent=self)
            if new:
                meta["name"] = new; self.render()

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
            meta["color"] = hx; self.render()

    def add_signal(self):
        self.model.add_signal(); self.selected = len(self.model.signals) - 1
        self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        self._refresh_offset_field(); self.render()

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
        for s in reversed(targets):
            self.model.remove_signal(s)
        self.model.prune_groups()
        if self.model.signals:
            self.selected = min(targets[0], len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._refresh_offset_field(); self.render()

    def do_new(self):
        if messagebox.askyesno("新增", "清空目前內容並新建？"):
            self.model = Model(); self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None; self.clip = None
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self._refresh_offset_field(); self.render()

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
            self.model.load_dict(d)
            if "view" in d:
                self.geom.load(d["view"])
                self.sp_w.delete(0, tk.END); self.sp_w.insert(0, str(self.geom.period_w))
                self.sp_h.delete(0, tk.END); self.sp_h.insert(0, str(self.geom.row_h))
                self.sp_r.delete(0, tk.END); self.sp_r.insert(0, str(int(self.geom.ramp_ratio * 100)))
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None; self._refresh_offset_field(); self.render()
        except Exception as ex:
            messagebox.showerror("開啟失敗", str(ex))

    def do_export(self):
        path = filedialog.asksaveasfilename(defaultextension=".png",
                filetypes=[("PNG 圖片", "*.png"), ("EPS 向量圖", "*.eps"), ("PostScript", "*.ps")])
        if not path:
            return
        total_h = self.geom.header_h + len(self.model.signals) * self.geom.row_h
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        wave_w = self.model.n_periods * self.geom.period_w + max_off * self.geom.period_w
        if path.lower().endswith(".png"):
            try:
                self._export_png(path, int(self.geom.name_w + wave_w), int(total_h))
                messagebox.showinfo("匯出", f"已輸出:\n{path}")
            except ImportError:
                messagebox.showwarning("匯出",
                    "PNG 匯出只需要 Pillow（不需要 Ghostscript）。\n請先安裝：\n  pip install pillow")
            except Exception as ex:
                messagebox.showerror("匯出失敗", str(ex))
        else:                                   # EPS / PS：tkinter 內建，無需任何套件
            sel = self.cell_sel; self.cell_sel = None; self.render()
            self.wave_cv.postscript(file=path, colormode="color",
                                    x=0, y=0, width=wave_w, height=total_h)
            self.cell_sel = sel; self.render()
            messagebox.showinfo("匯出", f"已輸出:\n{path}")

    def _export_png(self, path, w, h):
        from PIL import Image, ImageDraw
        fonts = _load_pil_fonts()
        NW = self.geom.name_w
        wave_w = max(1, w - NW)
        name_img = Image.new("RGB", (max(1, NW), max(1, h)), Style.CANVAS_BG)
        wave_img = Image.new("RGB", (wave_w, max(1, h)), Style.CANVAS_BG)
        nd = PILCanvas(ImageDraw.Draw(name_img), fonts)
        wd = PILCanvas(ImageDraw.Draw(wave_img), fonts)
        self.engine.draw(nd, wd, self.model, set(), self.geom, None)   # 不含選取高亮
        final = Image.new("RGB", (max(1, w), max(1, h)), Style.CANVAS_BG)
        final.paste(name_img, (0, 0)); final.paste(wave_img, (NW, 0))
        final.save(path)

    def help_usage(self):
        messagebox.showinfo("使用說明",
            "【畫波形】選元件後：點一格畫一格；拖曳沿起始列刷 (鎖列)。\n"
            "  · BUS：原本是 BUS 的格會保留延續；非 BUS 的格才轉成 BUS。\n"
            "         再點同格可輸入/修改資料值。\n"
            "【框選 (畫布)】Shift 或 Ctrl + 拖曳都是純框選：\n"
            "  · 框選後按元件鍵 = 整塊填入 (BUS 問一次文字)。\n"
            "  · Ctrl+C 複製、移到目標格 Ctrl+V 貼上 (超出列數自動新增列)。\n"
            "【名稱欄多選】Ctrl+點擊加選、Shift+點擊範圍；對選取的訊號：\n"
            "  · 右鍵選單可「調色／清色／設定位移／改名／刪除」(套用到所有選取)。\n"
            "  · Ctrl+C 複製選取訊號、Ctrl+V 貼在選取列之後 (名稱自動去重)。\n"
            "【其他】右鍵清成 L；雙擊名稱改名；Esc 清除框選。\n"
            "  · Ctrl+C/V 會依你最後操作的是「名稱多選」或「格框選」自動分流。")

    def help_keys(self):
        messagebox.showinfo("快捷鍵",
            "Ctrl+N/O/S/E 新增/開啟/儲存/匯出   Ctrl+C/V 複製/貼上\n"
            "1~6 切換元件 (CLK/H/L/BUS/HiZ/Unknown)\n"
            "Shift/Ctrl+拖曳 框選   按元件鍵=填入框選   Esc 清除框選\n"
            "名稱欄 Ctrl/Shift+點擊 多選 -> 右鍵選單(調色/位移/改名/刪除)\n"
            "右鍵 清成 L   雙擊名稱 改名")

    def help_about(self):
        messagebox.showinfo("關於", "RetroWave v1.7\n數位電路波型繪製工具\nPython + tkinter")


if __name__ == "__main__":
    App().mainloop()
