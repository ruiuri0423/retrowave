# -*- coding: utf-8 -*-
"""範本庫（邏輯單元）：獨立於專案檔；索引存於 ~/.retrowave/templates_index.json。"""
import json
import os


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
