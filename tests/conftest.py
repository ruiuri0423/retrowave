# -*- coding: utf-8 -*-
"""Shared pytest setup: add src/ to the import path, provide invariant checks and fake-event tools."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("RETROWAVE_NO_TUTORIAL", "1")   # don't auto-pop the onboarding tutorial in tests

import retrowave  # noqa: E402


class Ev:
    """Fake tkinter event (only carries fields the handlers use)."""

    def __init__(self, x=0, y=0, state=0, delta=0, num=0):
        self.x, self.y, self.state = x, y, state
        self.delta, self.num = delta, num


def assert_invariants(m):
    """Design doc §2.6: invariants that must hold after every edit."""
    # 1. sid is unique
    sids = [s["sid"] for s in m.signals]
    assert len(sids) == len(set(sids)), f"duplicate sid: {sids}"

    # 2. signals order == DFS leaf order of the group tree
    leaf_order = [nd["sid"] for nd in m._dfs_leaves()]
    assert sids == leaf_order, f"signals order {sids} != DFS leaf order {leaf_order}"

    # 3. no leftover markers in the tree, no empty groups
    def walk(nodes):
        for nd in nodes:
            assert nd.get("type") in ("sig", "group"), f"illegal leftover node: {nd}"
            if nd.get("type") == "group":
                assert nd.get("children"), f"leftover empty group: {nd.get('gid')}"
                walk(nd["children"])
    walk(m.group_tree)

    # 4. groups dict and tree nodes correspond one-to-one (same object)
    tree_nodes = {nd["gid"]: nd for nd in m._all_group_nodes()}
    assert set(m.groups) == set(tree_nodes)
    for gid in m.groups:
        assert m.groups[gid] is tree_nodes[gid]

    # 5. signal['group'] cache == direct parent group in the tree
    def parent_of(sid, nodes, parent_gid=None):
        for nd in nodes:
            if nd.get("type") == "sig" and nd.get("sid") == sid:
                return parent_gid
            if nd.get("type") == "group":
                r = parent_of(sid, nd.get("children", []), nd["gid"])
                if r is not False:
                    return r
        return False
    for s in m.signals:
        assert s.get("group") == parent_of(s["sid"], m.group_tree), \
            f"signal {s['name']} group cache {s.get('group')} disagrees with tree"

    # 6. annotations anchored to valid sids; edge endpoints are all valid anchors
    valid = set(sids)
    for nid, nd in m.nodes.items():
        assert nd.get("sid") in valid, f"anchor {nid} points to a non-existent sid"
    for e in m.edges:
        assert e["frm"] in m.nodes and e["to"] in m.nodes, f"edge endpoint invalid: {e}"

    # 7. each signal's cells length == n_periods
    for s in m.signals:
        assert len(s["cells"]) == m.n_periods

    # 8. when fully expanded, layout row count = signals + groups (group headers also take a row)
    collapsed = [g for g in m._all_group_nodes() if g.get("collapsed")]
    if not collapsed:
        assert len(m.layout()) == len(m.signals) + len(m.groups)


@pytest.fixture
def model():
    return retrowave.Model()


@pytest.fixture
def check():
    return assert_invariants


@pytest.fixture(scope="session")
def _root():
    """Share one Tk root across the whole test session.
    (Repeatedly create/destroy-ing Tk in the same process triggers Tcl's tcl_findLibrary error.)"""
    a = retrowave.App()
    a.update_idletasks()
    a.update()
    yield a
    try:
        a.destroy()
    except Exception:
        pass


@pytest.fixture
def app(_root):
    """Reset the shared App back to a clean post-__init__ state before each test."""
    a = _root
    a.doc = retrowave.Document(scheduler=a.after_idle)
    a.doc.subscribe(a._on_doc_changed)
    a.selected = 0; a.sig_sel = {0}; a._sig_anchor = 0
    a.cell_sel = None; a.clip = None; a.clip_signals = None; a.clip_group = None
    a._clip_kind = None; a._copy_ctx = "cells"
    a._press = None; a._press_xy = (0, 0); a._moved = False
    a._erase_marquee(); a._selecting = False; a._panning = False; a._pan_anchor = None
    a._drag_value = None; a._hover = None; a._hover_node = None; a._hover_edge = None
    a._connecting = False; a._connect_from = None; a._connect_xy = None
    a.wave_cv.xview_moveto(0.0); a.wave_cv.yview_moveto(0.0); a.name_cv.yview_moveto(0.0)
    a._set_tool("H")
    a.render()
    a.update_idletasks()
    return a


def cell_xy(app_, row, period):
    """Center of the cell at layout row `row`, period `period` (window coords; equals canvas coords when the view is at the origin)."""
    g = app_.geom
    return (period * g.period_w + g.period_w // 2,
            g.header_h + row * g.row_h + g.row_h // 2)
