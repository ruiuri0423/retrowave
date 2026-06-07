# -*- coding: utf-8 -*-
"""開啟教學（onboarding）：半透明反灰遮罩 + 鏤空高亮 + 分步導覽。

shell 層模組（與 app.py 同屬 UI 殼，允許 import tkinter）。
- 遮罩：覆蓋主視窗工作區的 Toplevel（alpha 半透明、深色底）。
- 高亮：Windows 用 `-transparentcolor` 把目標區域鏤空 — 該區完全清晰
  **且可直接點擊操作**（引導使用者實際動手）；不支援的平台自動退化為
  亮框標示（不鏤空）。
- 結束：最後一步勾選「下次啟動不再顯示」按完成；任何時候按「略過」
  直接結束且不再開啟。偏好存於 ~/.retrowave/settings.json（show_tutorial）。
"""
import json
import os
import tkinter as tk

from .theme import Style

SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".retrowave")
SETTINGS_FILE = "settings.json"
HOLE = "#FF00FE"            # 鏤空色（transparentcolor；UI 調色盤不使用的洋紅）
RING = "#FFD34D"            # 高亮框
CARD_BG = "#FBF8EC"; CARD_BD = "#8A867A"


def _settings_path():
    return os.path.join(SETTINGS_DIR, SETTINGS_FILE)


def load_settings():
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def tutorial_enabled():
    """預設 True（首次啟動顯示）；使用者勾選不顯示/略過後為 False。"""
    return bool(load_settings().get("show_tutorial", True))


def set_tutorial_enabled(flag):
    d = load_settings()
    d["show_tutorial"] = bool(flag)
    return save_settings(d)


class TutorialOverlay(tk.Toplevel):
    """覆蓋主視窗的教學遮罩。steps = [(target_widget|None, 標題, 內文)]。"""

    ALPHA = 0.88
    PAD = 8                  # 鏤空區外擴
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
        try:                                     # Windows：鏤空且可點擊操作
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

    # ---- 幾何 ----
    def _sync_geometry(self):
        m = self.app
        self.geometry(f"{max(m.winfo_width(), 1)}x{max(m.winfo_height(), 1)}"
                      f"+{m.winfo_rootx()}+{m.winfo_rooty()}")

    def _on_master_configure(self, _e=None):
        if self.winfo_exists():
            self._sync_geometry()
            self._show_step()

    def _target_bbox(self, widget):
        """目標 widget 在遮罩座標系中的 (x0,y0,x1,y1)；None=無高亮。"""
        if widget is None or not widget.winfo_exists():
            return None
        x0 = widget.winfo_rootx() - self.app.winfo_rootx() - self.PAD
        y0 = widget.winfo_rooty() - self.app.winfo_rooty() - self.PAD
        x1 = x0 + widget.winfo_width() + 2 * self.PAD
        y1 = y0 + widget.winfo_height() + 2 * self.PAD
        return x0, y0, x1, y1

    # ---- 繪製 ----
    def _show_step(self):
        cv = self.cv
        cv.delete("all")
        target, title, body = self.steps[self.idx]
        bbox = self._target_bbox(target)
        W = max(self.winfo_width(), 600); H = max(self.winfo_height(), 400)

        if bbox:
            x0, y0, x1, y1 = bbox
            if self._hole_ok:                    # 鏤空：該區清晰可見、可直接操作
                cv.create_rectangle(x0, y0, x1, y1, fill=HOLE, outline="")
            cv.create_rectangle(x0, y0, x1, y1, outline=RING, width=3)
            cv.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline="#7A6320", width=1)

        # ---- 說明卡片：避開高亮區（高亮在上半 → 卡片放下方，反之亦然）----
        cw = min(self.CARD_W, W - 40)
        last = self.idx == len(self.steps) - 1
        ch = 190 + (30 if last else 0)
        cx = (W - cw) // 2
        if bbox is None:
            cy = (H - ch) // 2
        elif (bbox[1] + bbox[3]) / 2 < H / 2:
            cy = min(bbox[3] + 24, H - ch - 16)
        else:
            cy = max(bbox[1] - ch - 24, 16)
        cv.create_rectangle(cx + 4, cy + 5, cx + cw + 4, cy + ch + 5,
                            fill="#15130E", outline="")          # 陰影
        cv.create_rectangle(cx, cy, cx + cw, cy + ch, fill=CARD_BG, outline=CARD_BD, width=2)
        cv.create_text(cx + 18, cy + 24, anchor="w", text=title,
                       font=("Tahoma", 12, "bold"), fill="#1A1A1A")
        cv.create_text(cx + cw - 18, cy + 24, anchor="e",
                       text=f"{self.idx + 1}/{len(self.steps)}",
                       font=Style.UI_FONT, fill="#777")
        cv.create_text(cx + 18, cy + 48, anchor="nw", text=body, width=cw - 36,
                       font=("Tahoma", 10), fill="#262626")

        # ---- 按鈕列 ----
        by = cy + ch - 38
        btn_skip = tk.Button(cv, text="略過（不再顯示）", font=Style.UI_FONT,
                             bg=CARD_BG, relief=tk.GROOVE, command=self.skip)
        cv.create_window(cx + 18, by, anchor="w", window=btn_skip)
        if self.idx > 0:
            btn_prev = tk.Button(cv, text="◀ 上一步", font=Style.UI_FONT,
                                 bg=CARD_BG, relief=tk.GROOVE, command=self.prev)
            cv.create_window(cx + cw - 118, by, anchor="e", window=btn_prev)
        btn_next = tk.Button(cv, text=("完成" if last else "下一步 ▶"),
                             font=("Tahoma", 9, "bold"), bg="#EDE7CF",
                             relief=tk.RAISED, command=(self.finish if last else self.next))
        cv.create_window(cx + cw - 18, by, anchor="e", window=btn_next)
        if last:                                  # 最後一步：下次不顯示勾選
            chk = tk.Checkbutton(cv, text="下次啟動不再顯示這個教學",
                                 variable=self.dont_show, font=Style.UI_FONT,
                                 bg=CARD_BG, activebackground=CARD_BG)
            cv.create_window(cx + 18, by - 32, anchor="w", window=chk)

    # ---- 流程 ----
    def next(self):
        if self.idx < len(self.steps) - 1:
            self.idx += 1
            self._show_step()

    def prev(self):
        if self.idx > 0:
            self.idx -= 1
            self._show_step()

    def skip(self):
        """略過：直接結束且永不再顯示。"""
        set_tutorial_enabled(False)
        self.close()

    def finish(self):
        """完成：依勾選決定下次是否顯示。"""
        set_tutorial_enabled(not self.dont_show.get())
        self.close()

    def close(self):
        try:
            self.app.unbind("<Configure>", self._cfg_id)
        except tk.TclError:
            pass
        self.destroy()
