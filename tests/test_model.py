# -*- coding: utf-8 -*-
"""Model unit tests: signal pool + group tree + annotations + persistence (no window).
Every test that mutates the Model ends by running the §2.6 invariant check (conftest.assert_invariants)."""
import json

import pytest

import retrowave
from retrowave import Model


# ---------------------------------------------------------------- basic signal ops
def test_demo_initial_state(model, check):
    assert len(model.signals) == 3
    assert [s["name"] for s in model.signals] == ["CLK", "RST_N", "DATA"]
    assert model.n_periods == retrowave.DEFAULT_PERIODS
    assert model.signals[2]["cells"][2] == {"type": "BUS", "text": "A5"}
    check(model)


def test_add_signal_appends_top_level(model, check):
    model.add_signal("X")
    assert model.signals[-1]["name"] == "X"
    assert model.group_tree[-1] == {"type": "sig", "sid": model.signals[-1]["sid"]}
    check(model)


def test_add_signal_default_name_and_fresh_sid(model, check):
    before = {s["sid"] for s in model.signals}
    model.add_signal()
    assert model.signals[-1]["name"] == "SIG3"
    assert model.signals[-1]["sid"] not in before
    check(model)


def test_remove_signal(model, check):
    sid = model.signals[1]["sid"]
    model.remove_signal(1)
    assert [s["name"] for s in model.signals] == ["CLK", "DATA"]
    assert all(nd.get("sid") != sid for nd in model._dfs_leaves())
    check(model)


def test_remove_signal_out_of_range_noop(model, check):
    model.remove_signal(99)
    model.remove_signal(-1)
    assert len(model.signals) == 3
    check(model)


def test_set_n_periods_grow_pads_low(model, check):
    model.set_n_periods(16)
    assert model.n_periods == 16
    assert all(len(s["cells"]) == 16 for s in model.signals)
    assert model.signals[0]["cells"][-1] == {"type": "L", "text": ""}
    check(model)


def test_set_n_periods_shrink_truncates(model, check):
    model.set_n_periods(4)
    assert all(len(s["cells"]) == 4 for s in model.signals)
    check(model)


def test_set_n_periods_clamps_to_one(model, check):
    model.set_n_periods(0)
    assert model.n_periods == 1
    check(model)


def test_set_cell_and_bounds(model, check):
    model.set_cell(0, 0, "H")
    assert model.signals[0]["cells"][0]["type"] == "H"
    model.set_cell(99, 0, "H")     # out of range -> no-op
    model.set_cell(0, 99, "H")
    check(model)


# ---------------------------------------------------------------- group tree
def test_group_signals_creates_group_at_first_member(model, check):
    gid = model.group_signals([1, 2], name="SPI")
    assert gid in model.groups and model.groups[gid]["name"] == "SPI"
    # group is inserted at the first member's original top-level position: after CLK
    assert model.group_tree[0]["sid"] == model.signals[0]["sid"]
    assert model.group_tree[1]["gid"] == gid
    assert [s["group"] for s in model.signals] == [None, gid, gid]
    check(model)


def test_group_signals_empty_returns_none(model, check):
    assert model.group_signals([]) is None
    check(model)


def test_merge_into_group_appends_at_tail(model, check):
    gid = model.group_signals([1], name="G")
    model.merge_into_group([0, 2], gid)
    node = model._find_group_node(gid)
    assert [c["sid"] for c in node["children"]] == [s["sid"] for s in model.signals]
    assert all(s["group"] == gid for s in model.signals)
    check(model)


def test_merge_groups_nests(model, check):
    g1 = model.group_signals([0], name="A")
    g2 = model.group_signals([2], name="B")
    assert model.merge_groups(g2, g1) == g1
    node = model._find_group_node(g1)
    assert any(c.get("gid") == g2 for c in node["children"])
    check(model)


def test_merge_groups_refuses_self_and_descendant(model, check):
    g1 = model.group_signals([0], name="A")
    g2 = model.group_signals([2], name="B")
    model.merge_groups(g2, g1)                       # g2 nested under g1
    assert model.merge_groups(g1, g1) is None        # self
    assert model.merge_groups(g1, g2) is None        # descendant
    check(model)


def test_move_group_into_own_descendant_refused(model, check):
    g1 = model.group_signals([0], name="A")
    g2 = model.group_signals([2], name="B")
    model.merge_groups(g2, g1)
    assert model.move_group_to(g1, g2, 0) is False
    assert model.move_group_to(g1, g1, 0) is False
    check(model)


def test_move_leaf_downward_same_container_no_off_by_one(model, check):
    """Regression test for rule 4: downward moves use the marker method; the landing spot must not shift."""
    model.add_signal("S3"); model.add_signal("S4")   # CLK RST DATA S3 S4
    sid = model.signals[0]["sid"]                    # move CLK to index 3 (after S3)
    assert model.move_leaf_to(sid, None, 4)          # target: before original S4 (index=4 when the tree still contains self)
    assert [s["name"] for s in model.signals] == ["RST_N", "DATA", "S3", "CLK", "S4"]
    check(model)


def test_move_leaf_into_group_at_position(model, check):
    gid = model.group_signals([1, 2], name="G")
    sid = model.signals[0]["sid"]                    # CLK
    assert model.move_leaf_to(sid, gid, 1)           # insert in the middle of the group's children
    node = model._find_group_node(gid)
    assert [c["sid"] for c in node["children"]][1] == sid
    assert model.signals[[s["sid"] for s in model.signals].index(sid)]["group"] == gid
    check(model)


def test_move_leaf_to_bad_container(model, check):
    assert model.move_leaf_to(model.signals[0]["sid"], "no_such_gid", 0) is False
    check(model)


def test_remove_from_group_promotes_and_clears_color(model, check):
    gid = model.group_signals([1, 2], name="G")
    model.signals[1]["color"] = "#FF0000"
    moved = model.remove_from_group([1])
    assert moved == 1
    s = model.signals[[i for i, x in enumerate(model.signals) if x["name"] == "RST_N"][0]]
    assert s["group"] is None and s["color"] is None
    assert gid in model.groups                        # group still has DATA
    check(model)


def test_remove_from_group_last_member_prunes_group(model, check):
    gid = model.group_signals([2], name="G")
    model.remove_from_group([2])
    assert gid not in model.groups
    check(model)


def test_ungroup_promotes_children_keeps_subgroup(model, check):
    g1 = model.group_signals([1, 2], name="OUT")
    g2 = model.group_signals([2], name="IN")          # IN nested inside OUT
    model.merge_groups(g2, g1)
    model.ungroup([g1])
    assert g1 not in model.groups and g2 in model.groups
    # IN promoted to top level, RST_N back at top level too
    assert model._find_group_node(g2) in model.group_tree
    check(model)


def test_delete_group_removes_subtree_and_annotations(model, check):
    g1 = model.group_signals([1, 2], name="G")
    sid = model.signals[-1]["sid"]
    nid = model.add_node(sid, 2, "start")
    n2 = model.add_node(model.signals[0]["sid"], 0, "start")
    model.add_edge(nid, n2, "t_x")
    deleted = model.delete_group(g1)
    assert deleted == 2
    assert [s["name"] for s in model.signals] == ["CLK"]
    assert nid not in model.nodes and len(model.edges) == 0
    assert n2 in model.nodes                          # anchor on the surviving signal must be kept
    check(model)


def test_new_gid_skips_existing(model, check):
    g1 = model.group_signals([0], name="A")
    model._gid_seq = 0                                # deliberate reset, simulating a post-load id clash
    g2 = model.group_signals([1], name="B")
    assert g1 != g2
    check(model)


# ---------------------------------------------------------------- layout
def test_layout_rows_headers_and_depth(model, check):
    gid = model.group_signals([1, 2], name="G")
    rows = model.layout()
    assert [(r.kind, r.depth) for r in rows] == [
        ("sig", 0), ("group", 0), ("sig", 1), ("sig", 1)]
    assert rows[1].ref == gid
    check(model)


def test_layout_collapsed_hides_subtree(model, check):
    gid = model.group_signals([1, 2], name="G")
    model.groups[gid]["collapsed"] = True
    rows = model.layout()
    assert [(r.kind,) for r in rows] == [("sig",), ("group",)]
    check(model)


def test_layout_color_inheritance_nearest_ancestor_wins(model):
    outer = model.group_signals([1, 2], name="OUT")
    inner = model.group_signals([2], name="IN")
    model.merge_groups(inner, outer)
    model.groups[outer]["color"] = "#0000FF"
    model.groups[inner]["color"] = "#00FF00"
    rows = {(r.kind, r.ref): r for r in model.layout()}
    idx = {s["name"]: i for i, s in enumerate(model.signals)}
    assert rows[("sig", idx["RST_N"])].gcol == "#0000FF"   # directly under OUT
    assert rows[("sig", idx["DATA"])].gcol == "#00FF00"    # IN is nearer, wins


# ---------------------------------------------------------------- annotations
def test_add_node_and_edge_validation(model, check):
    a = model.add_node(model.signals[0]["sid"], 1, "start")
    b = model.add_node(model.signals[1]["sid"], 3, "end")
    assert model.add_edge(a, a) is None               # self-loop
    assert model.add_edge(a, "zz") is None            # non-existent endpoint
    e = model.add_edge(a, b, "t_su", "single")
    assert e in model.edges
    check(model)


def test_remove_node_cascades_edges(model, check):
    a = model.add_node(model.signals[0]["sid"], 1, "start")
    b = model.add_node(model.signals[1]["sid"], 3, "end")
    model.add_edge(a, b)
    model.remove_node(a)
    assert a not in model.nodes and model.edges == []
    check(model)


def test_prune_annotations_after_signal_removal(model, check):
    a = model.add_node(model.signals[0]["sid"], 1, "start")
    b = model.add_node(model.signals[1]["sid"], 3, "end")
    model.add_edge(a, b)
    model.remove_signal(0)
    removed_nodes, removed_edges = model.prune_annotations()
    assert (removed_nodes, removed_edges) == (1, 1)
    assert b in model.nodes
    check(model)


def test_nid_allocation_exhausts_singles(model):
    for _ in range(26):
        model.add_node(model.signals[0]["sid"], 0, "start")
    nid = model.add_node(model.signals[0]["sid"], 0, "start")
    assert nid == "aa"                                # single letters exhausted -> double letters


# ---------------------------------------------------------------- persistence
def test_roundtrip_preserves_structure(model, check):
    gid = model.group_signals([1, 2], name="SPI")
    model.groups[gid]["color"] = "#2266CC"
    a = model.add_node(model.signals[1]["sid"], 2, "mid")
    b = model.add_node(model.signals[2]["sid"], 5, "start")
    model.add_edge(a, b, "t_h")
    blob = json.loads(json.dumps(model.to_dict()))    # through real JSON serialization

    m2 = Model()
    m2.load_dict(blob)
    assert [s["name"] for s in m2.signals] == [s["name"] for s in model.signals]
    assert [s["sid"] for s in m2.signals] == [s["sid"] for s in model.signals]
    assert m2.groups[gid]["color"] == "#2266CC"
    assert m2.edges[0]["label"] == "t_h"
    check(m2)


def test_load_restores_sid_seq_no_collision(model, check):
    blob = model.to_dict()
    m2 = Model()
    m2.load_dict(json.loads(json.dumps(blob)))
    existing = {s["sid"] for s in m2.signals}
    m2.add_signal("NEW")
    assert m2.signals[-1]["sid"] not in existing      # new sid after load must not clash
    check(m2)


def test_load_legacy_flat_format_migrates(check):
    legacy = {"version": "1.4", "n_periods": 4,
              "signals": [
                  {"name": "A", "cells": [{"type": "L", "text": ""}] * 4},
                  {"name": "B", "group": "g1", "cells": [{"type": "H", "text": ""}] * 4},
                  {"name": "C", "group": "g1", "cells": [{"type": "L", "text": ""}] * 4}],
              "groups": {"g1": {"name": "BUS_GRP", "collapsed": False, "color": "#123456"}}}
    m = Model()
    m.load_dict(legacy)
    assert set(m.groups) == {"g1"}
    assert m.groups["g1"]["name"] == "BUS_GRP"
    assert [s.get("group") for s in m.signals] == [None, "g1", "g1"]
    assert all(s["sid"] for s in m.signals)           # legacy files have no sid -> auto-assigned
    check(m)


def test_load_pads_and_truncates_cells(check):
    m = Model()
    m.load_dict({"n_periods": 6,
                 "signals": [{"name": "A", "sid": 1, "cells": [{"type": "H", "text": ""}] * 2},
                             {"name": "B", "sid": 2, "cells": [{"type": "L", "text": ""}] * 9}],
                 "group_tree": [{"type": "sig", "sid": 1}, {"type": "sig", "sid": 2}]})
    assert all(len(s["cells"]) == 6 for s in m.signals)
    check(m)


def test_load_tree_missing_leaf_repaired(check):
    """When the tree omits a signal, _resync_signals must add it back at top level (§2.6 safeguard)."""
    m = Model()
    m.load_dict({"n_periods": 4,
                 "signals": [{"name": "A", "sid": 1, "cells": [{"type": "L", "text": ""}] * 4},
                             {"name": "B", "sid": 2, "cells": [{"type": "L", "text": ""}] * 4}],
                 "group_tree": [{"type": "sig", "sid": 1}]})   # sid=2 omitted
    assert [s["sid"] for s in m.signals] == [nd["sid"] for nd in m._dfs_leaves()]
    assert len(m.signals) == 2
    check(m)
