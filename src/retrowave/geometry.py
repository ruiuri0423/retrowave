# -*- coding: utf-8 -*-
"""幾何參數：週期寬/列高/統一斜率比與座標換算（共用底層，零依賴）。
設計文件 §2.5/§3；copy_scaled 供高解析匯出。"""


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

    def copy_scaled(self, k):
        """回傳一份座標等比放大 k 倍的幾何 (比例欄位不變)；供高解析點陣匯出。"""
        g = Geometry()
        g.period_w = int(round(self.period_w * k)); g.row_h = int(round(self.row_h * k))
        g.header_h = int(round(self.header_h * k)); g.name_w = int(round(self.name_w * k))
        g.ramp_ratio = self.ramp_ratio
        g.level_hi = self.level_hi; g.level_lo = self.level_lo
        return g
