# -*- coding: utf-8 -*-
"""Export backends (drawing units): duck-type implementations of the Canvas create_* interface,
so the Engine can output raster (PILCanvas, needs Pillow) and vector (SVGCanvas, zero dependencies)
without any changes. Design spec §4/§9."""


def _load_pil_fonts(scale=1):
    from PIL import ImageFont
    reg_cands = ["msjh.ttc", "msyh.ttc", "mingliu.ttc", "NotoSansCJKtc-Regular.otf",
                 "PingFang.ttc", "tahoma.ttf", "arial.ttf", "DejaVuSans.ttf"]
    bold_cands = ["msjhbd.ttc", "msyhbd.ttc", "tahomabd.ttf", "arialbd.ttf",
                  "DejaVuSans-Bold.ttf"] + reg_cands
    size = max(8, int(round(12 * scale)))

    def pick(cands, sz):
        for c in cands:
            try:
                return ImageFont.truetype(c, sz)
            except Exception:
                pass
        return ImageFont.load_default()
    return {"reg": pick(reg_cands, size), "bold": pick(bold_cands, size)}


class PILCanvas:
    """Minimal tkinter Canvas interface that actually draws to a Pillow ImageDraw.
    scale is used for high-resolution export: line widths and annotation sizes scale up
    accordingly (coordinates are already supplied by the scaled Geometry)."""
    def __init__(self, draw, fonts, scale=1):
        self.d = draw
        self.fonts = fonts
        self.export_scale = scale

    @staticmethod
    def _c(v):
        return None if v in (None, "") else v

    def _w(self, width):
        return max(1, int(round(width * self.export_scale)))

    def _font(self, f):
        bold = isinstance(f, (tuple, list)) and "bold" in f
        return self.fonts["bold"] if bold else self.fonts["reg"]

    def create_line(self, *coords, fill=None, width=1, dash=None, **kw):
        f = self._c(fill)
        if f:
            self.d.line(list(coords), fill=f, width=self._w(width))

    def create_rectangle(self, x0, y0, x1, y1, fill=None, outline=None,
                         width=1, dash=None, stipple=None, **kw):
        f = self._c(fill); o = self._c(outline)
        if f or o:
            self.d.rectangle([x0, y0, x1, y1], fill=f, outline=o, width=self._w(width) if o else 1)

    def create_polygon(self, pts, fill=None, outline=None, **kw):
        self.d.polygon(list(pts), fill=self._c(fill), outline=self._c(outline))

    def create_oval(self, x0, y0, x1, y1, fill=None, outline=None, width=1, **kw):
        self.d.ellipse([x0, y0, x1, y1], fill=self._c(fill),
                       outline=self._c(outline), width=self._w(width) if self._c(outline) else 1)

    def create_text(self, x, y, text="", font=None, fill=None, anchor="center", **kw):
        f = self._c(fill) or "#000000"
        anc = {"center": "mm", "w": "lm", "e": "rm"}.get(anchor, "mm")
        try:
            self.d.text((x, y), str(text), fill=f, font=self._font(font), anchor=anc)
        except TypeError:                       # older Pillow has no anchor parameter
            self.d.text((x, y), str(text), fill=f, font=self._font(font))

    def configure(self, **kw):
        pass

    def delete(self, *a):
        pass


class SVGCanvas:
    """Maps the tkinter Canvas interface to SVG elements (vector, infinite resolution).
    Multiple instances can share the same elements list and use xoff for horizontal offset
    (composing the name column / waveform area into a single file)."""
    CJK = "'Microsoft JhengHei','PingFang TC','Noto Sans CJK TC','Heiti TC',sans-serif"

    def __init__(self, elements, xoff=0):
        self.e = elements
        self.xoff = xoff

    def _x(self, x):
        return x + self.xoff

    @staticmethod
    def _c(v):
        return None if v in (None, "") else v

    @staticmethod
    def _esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    def _pts(self, coords):
        return " ".join(f"{self._x(coords[i]):.1f},{coords[i+1]:.1f}"
                        for i in range(0, len(coords) - 1, 2))

    def create_line(self, *coords, fill=None, width=1, dash=None, **kw):
        f = self._c(fill)
        if not f:
            return
        da = f' stroke-dasharray="{dash[0]},{dash[1]}"' if dash else ""
        self.e.append(f'<polyline points="{self._pts(coords)}" fill="none" '
                      f'stroke="{f}" stroke-width="{width}"{da}/>')

    def create_rectangle(self, x0, y0, x1, y1, fill=None, outline=None,
                         width=1, dash=None, stipple=None, **kw):
        f = self._c(fill); o = self._c(outline)
        if not (f or o):
            return
        X0, X1 = self._x(min(x0, x1)), self._x(max(x0, x1))
        Y0, Y1 = min(y0, y1), max(y0, y1)
        a = f'fill="{f}"' if f else 'fill="none"'
        if o:
            a += f' stroke="{o}" stroke-width="{width}"'
        self.e.append(f'<rect x="{X0:.1f}" y="{Y0:.1f}" width="{X1-X0:.1f}" '
                      f'height="{Y1-Y0:.1f}" {a}/>')

    def create_polygon(self, pts, fill=None, outline=None, **kw):
        f = self._c(fill); o = self._c(outline)
        a = f'fill="{f}"' if f else 'fill="none"'
        if o:
            a += f' stroke="{o}"'
        self.e.append(f'<polygon points="{self._pts(list(pts))}" {a}/>')

    def create_oval(self, x0, y0, x1, y1, fill=None, outline=None, width=1, **kw):
        cx = (self._x(x0) + self._x(x1)) / 2; cy = (y0 + y1) / 2
        rx = abs(x1 - x0) / 2; ry = abs(y1 - y0) / 2
        f = self._c(fill); o = self._c(outline)
        a = f'fill="{f}"' if f else 'fill="none"'
        if o:
            a += f' stroke="{o}" stroke-width="{width}"'
        self.e.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" {a}/>')

    def create_text(self, x, y, text="", font=None, fill=None, anchor="center", **kw):
        f = self._c(fill) or "#000000"
        size, bold = 12, False
        if isinstance(font, (tuple, list)):
            for v in font:
                if isinstance(v, int):
                    size = int(round(abs(v) * 1.33))
                elif v == "bold":
                    bold = True
        ta = {"center": "middle", "w": "start", "e": "end"}.get(anchor, "middle")
        wt = ' font-weight="bold"' if bold else ""
        self.e.append(f'<text x="{self._x(x):.1f}" y="{y:.1f}" font-size="{size}" '
                      f'font-family="{self.CJK}" text-anchor="{ta}" '
                      f'dominant-baseline="middle" fill="{f}"{wt}>{self._esc(text)}</text>')

    def configure(self, **kw):
        pass

    def delete(self, *a):
        pass
