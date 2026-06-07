# -*- coding: utf-8 -*-
"""v1.22 套件邊界測試：邏輯/繪圖單元必須 headless（設計文件 §14 R2 的基礎）。"""
import ast
import os
import subprocess
import sys

import retrowave

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))

CORE_MODULES = ["theme", "geometry", "model", "elements", "engine", "backends",
                "templates", "export", "document"]


def test_core_and_drawing_modules_are_headless():
    """子行程鐵證：匯入套件與所有核心/繪圖模組後，tkinter 不得出現在 sys.modules。"""
    code = (
        "import sys; import retrowave; "
        + "; ".join(f"import retrowave.{m}" for m in CORE_MODULES) + "; "
        "assert 'tkinter' not in sys.modules, 'tkinter leaked: ' + "
        "','.join(k for k in sys.modules if 'tkinter' in k); "
        "m = retrowave.Model(); m.layout(); m.to_dict(); "        # 核心可完整運作
        "print('headless-ok')"
    )
    env = dict(os.environ, PYTHONPATH=SRC)
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "headless-ok" in r.stdout


def test_only_shell_imports_tkinter():
    """靜態檢查：套件內除 shell 層（app/tutorial/__main__）外，任何模組不得 import tkinter。"""
    SHELL = ("app.py", "tutorial.py", "__main__.py")
    pkg_dir = os.path.dirname(retrowave.__file__)
    for fn in sorted(os.listdir(pkg_dir)):
        if not fn.endswith(".py") or fn in SHELL:
            continue
        tree = ast.parse(open(os.path.join(pkg_dir, fn), encoding="utf-8").read())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                assert m.split(".")[0] != "tkinter", f"{fn} 不得 import tkinter（違反 §14）"


def test_public_api_reexported():
    """__init__ re-export 完整（含 PEP 562 延遲載入的 UI 名稱）。"""
    for name in ("Model", "Row", "DEFAULT_PERIODS", "Geometry", "Engine", "Style",
                 "PILCanvas", "SVGCanvas", "TemplateLibrary", "WAVE_TYPES",
                 "App", "make_key_button", "SHIFT_MASK", "CTRL_MASK", "__version__"):
        assert hasattr(retrowave, name), f"retrowave.{name} 遺失"


def test_app_writes_only_via_document():
    """R1 守門：shell 不得私有存取 Model、不得直接操作文件結構（§14 / DEVELOPMENT §8）。"""
    pkg_dir = os.path.dirname(retrowave.__file__)
    src = open(os.path.join(pkg_dir, "app.py"), encoding="utf-8").read()
    import re
    forbidden = [
        (r"self\.model\._", "私有存取 model._*"),
        (r"self\.model\s*=", "直接替換 model（應走 doc.new_document/load_document）"),
        (r"\.group_tree\.(insert|append|remove)", "直接操作群組樹"),
        (r"\.signals\.append", "直接操作訊號池"),
        (r"_after_tree_change|_new_sid\(", "呼叫 Model 私有對帳/發號"),
        (r"self\.model\.set_cell|self\.model\.add_signal\(|self\.model\.remove_signal",
         "繞過命令層直呼 Model 變更方法"),
    ]
    for pat, why in forbidden:
        assert not re.search(pat, src), f"app.py 違反 R1：{why}（pattern: {pat}）"


def test_version_single_source():
    """視窗標題/關於對話框使用 __version__，程式內不殘留硬編版本字串。"""
    pkg_dir = os.path.dirname(retrowave.__file__)
    import re
    for fn in sorted(os.listdir(pkg_dir)):
        if not fn.endswith(".py") or fn == "__init__.py":
            continue
        src = open(os.path.join(pkg_dir, fn), encoding="utf-8").read()
        assert not re.search(r"v1\.\d+", src), f"{fn} 含硬編版本字串，應使用 __version__"
