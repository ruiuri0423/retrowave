# -*- coding: utf-8 -*-
"""Template library (logic unit): independent of project files; index stored in ~/.retrowave/templates_index.json."""
import json
import os


class TemplateLibrary:
    DIR = os.path.join(os.path.expanduser("~"), ".retrowave")
    INDEX = os.path.join(DIR, "templates_index.json")

    def __init__(self):
        self.entries = []                      # [{name, path}]

    def load(self):
        """Read the index file and return (available list, missing list). Missing entries are auto-removed from the index."""
        try:
            with open(self.INDEX, encoding="utf-8") as f:
                items = json.load(f).get("templates", [])
        except Exception:
            items = []
        avail, missing = [], []
        for it in items:
            p = it.get("path")
            nm = it.get("name") or (os.path.splitext(os.path.basename(p))[0] if p else "Template")
            (avail if (p and os.path.isfile(p)) else missing).append({"name": nm, "path": p})
        self.entries = avail
        if missing:
            self.save()                        # update the index file, dropping missing entries
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
        self.entries = [e for e in self.entries if e.get("path") != path]   # dedupe by path
        self.entries.append({"name": name, "path": path}); self.save()

    def remove(self, name):
        self.entries = [e for e in self.entries if e.get("name") != name]; self.save()

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
