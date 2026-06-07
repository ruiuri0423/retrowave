# -*- coding: utf-8 -*-
"""v1.22 package boundary tests: logic/drawing units must be headless (the basis of design doc §14 R2)."""
import ast
import os
import subprocess
import sys

import retrowave

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))

CORE_MODULES = ["theme", "geometry", "model", "elements", "engine", "backends",
                "templates", "export", "document"]


def test_core_and_drawing_modules_are_headless():
    """Subprocess proof: after importing the package and all core/drawing modules, tkinter must not appear in sys.modules."""
    code = (
        "import sys; import retrowave; "
        + "; ".join(f"import retrowave.{m}" for m in CORE_MODULES) + "; "
        "assert 'tkinter' not in sys.modules, 'tkinter leaked: ' + "
        "','.join(k for k in sys.modules if 'tkinter' in k); "
        "m = retrowave.Model(); m.layout(); m.to_dict(); "        # core works fully
        "print('headless-ok')"
    )
    env = dict(os.environ, PYTHONPATH=SRC)
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "headless-ok" in r.stdout


def test_only_shell_imports_tkinter():
    """Static check: within the package, no module other than the shell layer (app/tutorial/__main__) may import tkinter."""
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
                assert m.split(".")[0] != "tkinter", f"{fn} must not import tkinter (violates §14)"


def test_public_api_reexported():
    """__init__ re-exports are complete (including PEP 562 lazily-loaded UI names)."""
    for name in ("Model", "Row", "DEFAULT_PERIODS", "Geometry", "Engine", "Style",
                 "PILCanvas", "SVGCanvas", "TemplateLibrary", "WAVE_TYPES",
                 "App", "make_key_button", "SHIFT_MASK", "CTRL_MASK", "__version__"):
        assert hasattr(retrowave, name), f"retrowave.{name} is missing"


def test_app_writes_only_via_document():
    """R1 gatekeeper: the shell must not privately access Model or directly manipulate document structure (§14 / DEVELOPMENT §8)."""
    pkg_dir = os.path.dirname(retrowave.__file__)
    src = open(os.path.join(pkg_dir, "app.py"), encoding="utf-8").read()
    import re
    forbidden = [
        (r"self\.model\._", "private access to model._*"),
        (r"self\.model\s*=", "directly replacing model (should go through doc.new_document/load_document)"),
        (r"\.group_tree\.(insert|append|remove)", "directly manipulating the group tree"),
        (r"\.signals\.append", "directly manipulating the signal pool"),
        (r"_after_tree_change|_new_sid\(", "calling Model's private reconcile/id-allocation"),
        (r"self\.model\.set_cell|self\.model\.add_signal\(|self\.model\.remove_signal",
         "bypassing the command layer to call Model mutators directly"),
    ]
    for pat, why in forbidden:
        assert not re.search(pat, src), f"app.py violates R1: {why} (pattern: {pat})"


def test_version_single_source():
    """Window title / about dialog use __version__; no hardcoded version strings remain in the code."""
    pkg_dir = os.path.dirname(retrowave.__file__)
    import re
    for fn in sorted(os.listdir(pkg_dir)):
        if not fn.endswith(".py") or fn == "__init__.py":
            continue
        src = open(os.path.join(pkg_dir, fn), encoding="utf-8").read()
        assert not re.search(r"v1\.\d+", src), f"{fn} contains a hardcoded version string, should use __version__"
