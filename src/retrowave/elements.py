# -*- coding: utf-8 -*-
"""Waveform elements (drawing units): drawing algorithms for six element types, with the
transition slope unified = swing/tw.
Design spec §6.3; draws only to a duck-type Canvas, must not import tkinter."""
from .theme import Style

WAVE_TYPES = ["CLK", "H", "L", "BUS", "HiZ", "Unknown"]


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
        elif pe.kind == "DATA":                         # previous is BUS: both tracks converge to this level (right side, unified slope)
            whi = abs(hi - y) * tw / swing; wlo = abs(lo - y) * tw / swing
            xflat = x0 + min(whi, wlo)
            cv.create_line(xflat, y, x1, y, fill=col, width=W)
            if whi > 0.5: cv.create_line(x0, hi, x0 + whi, y, fill=col, width=W)
            if wlo > 0.5: cv.create_line(x0, lo, x0 + wlo, y, fill=col, width=W)
        elif pe.kind == "CLK":                          # CLK<->LEVEL: right angle
            if abs(lo - y) > 0.5:
                cv.create_line(x0, lo, x0, y, fill=col, width=W)
            cv.create_line(x0, y, x1, y, fill=col, width=W)
        else:                                           # LEVEL<->LEVEL: unified slope
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
        elif prevDATA:                                  # data change: X crossover
            xm = x0 + tw / 2
            left_lines += [(x0, hi, xm, mid), (x0, lo, xm, mid),
                           (xm, mid, x0 + tw, hi), (xm, mid, x0 + tw, lo)]
            xLhi = xLlo = x0 + tw
        else:                                           # opening from level/clk/none
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
