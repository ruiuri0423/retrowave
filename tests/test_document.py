# -*- coding: utf-8 -*-
"""v1.24 delivery-layer tests (headless, no window):
command routing, the four error policies, coalesced event dispatch, gesture transactions, snapshot-based Undo/Redo (depth 5)."""
import pytest

from retrowave.document import Document, unique_name
from conftest import assert_invariants


@pytest.fixture
def doc():
    return Document()                        # scheduler=None -> events dispatched synchronously


@pytest.fixture
def events(doc):
    log = []
    doc.subscribe(lambda scopes: log.append(set(scopes)))
    return log


# ---------------------------------------------------------------- commands + events
def test_set_cell_emits_cells_scope(doc, events):
    assert doc.set_cell(0, 0, "H") is True
    assert doc.model.signals[0]["cells"][0]["type"] == "H"
    assert events == [{"cells"}]
    assert_invariants(doc.model)


def test_structure_commands_emit_structure(doc, events):
    idx = doc.add_signal("X")
    assert idx == 3
    gid = doc.group_signals([1, 2], name="SPI")
    assert gid in doc.model.groups
    assert all(s == {"structure"} for s in events) and len(events) == 2
    assert_invariants(doc.model)


def test_scheduler_coalesces_events(events_log=None):
    queued = []
    doc = Document(scheduler=queued.append)  # fake scheduler: collect flushes
    log = []
    doc.subscribe(lambda scopes: log.append(set(scopes)))
    doc.set_cell(0, 0, "H")
    doc.add_signal("X")
    doc.set_cell(0, 1, "L")
    assert log == [] and len(queued) == 1    # three commands -> only one flush scheduled
    queued[0]()                              # simulate idle
    assert log == [{"cells", "structure"}]   # coalesced into one notification (scope union)


# ---------------------------------------------------------------- error policies
def test_invalid_returns_false_no_event_no_undo(doc, events):
    assert doc.set_cell(99, 0, "H") is False          # out of range -> False (policy 4: no silent third state)
    assert doc.set_cell(0, 99, "H") is False
    assert doc.remove_signals([99]) == 0
    assert doc.rename_signal(0, "") is False
    assert doc.set_offset([], 0.5) == 0
    assert doc.delete_group("no_such") == 0
    assert doc.toggle_group("no_such") is None
    assert doc.move_leaves_to({999}, 0) is False      # non-existent sid (single = one-element set)
    assert events == [] and not doc.can_undo()        # failures emit no event and don't enter undo
    assert_invariants(doc.model)


def test_move_group_into_descendant_refused_atomic(doc, events):
    g1 = doc.group_signals([0], name="A")
    g2 = doc.group_signals([2], name="B")
    doc.merge_groups(g2, g1)
    snap = doc.model.to_dict()
    events.clear()
    assert doc.move_group_to(g1, 0, container_gid=g2) is False   # user-level invalid
    assert doc.model.to_dict() == snap                # document unchanged (atomic)
    assert events == []
    assert_invariants(doc.model)


def test_load_document_bad_data_raises_and_restores(doc):
    before = doc.model.to_dict()
    with pytest.raises(Exception):
        doc.load_document({"signals": "garbage"})     # program-level error -> raises
    assert doc.model.to_dict() == before              # and the document is restored (atomic)
    assert_invariants(doc.model)


# ---------------------------------------------------------------- gesture transactions
def test_transaction_is_single_undo_unit(doc):
    doc.begin()
    for p in range(5):
        doc.set_cell(0, p, "H")
    assert not doc.can_undo()                         # not settled mid-transaction
    assert doc.commit() is True
    assert len(doc._undo) == 1                        # five set_cell calls = one undo unit
    doc.undo()
    assert all(c["type"] == "CLK" for c in doc.model.signals[0]["cells"][:5])
    assert_invariants(doc.model)


def test_empty_transaction_not_recorded(doc):
    doc.begin()
    assert doc.commit() is False                      # no change -> not pushed onto the stack
    assert not doc.can_undo()


def test_transaction_events_still_flow(doc, events):
    doc.begin()
    doc.set_cell(0, 0, "H")
    doc.set_cell(0, 1, "H")
    doc.commit()
    assert events == [{"cells"}, {"cells"}]           # events still fire during the transaction (one per command under the sync scheduler)


# ---------------------------------------------------------------- Undo / Redo
def test_undo_redo_roundtrip(doc):
    doc.set_cell(0, 0, "H")
    doc.rename_signal(2, "BUS_A")
    assert doc.undo() is True
    assert doc.model.signals[2]["name"] == "DATA"
    assert doc.undo() is True
    assert doc.model.signals[0]["cells"][0]["type"] == "CLK"
    assert doc.undo() is False                        # stack empty
    assert doc.redo() is True and doc.model.signals[0]["cells"][0]["type"] == "H"
    assert doc.redo() is True and doc.model.signals[2]["name"] == "BUS_A"
    assert doc.redo() is False
    assert_invariants(doc.model)


def test_undo_depth_limited_to_5(doc):
    for p in range(7):                                # 7 commands, depth 5
        doc.set_cell(0, p, "H")
    n = 0
    while doc.undo():
        n += 1
    assert n == Document.UNDO_DEPTH == 5
    # the earliest two steps have been pushed out: T0/T1 are still H, T2.. restored
    assert doc.model.signals[0]["cells"][0]["type"] == "H"
    assert doc.model.signals[0]["cells"][2]["type"] == "CLK"
    assert_invariants(doc.model)


def test_new_command_clears_redo(doc):
    doc.set_cell(0, 0, "H")
    doc.undo()
    assert doc.can_redo()
    doc.set_cell(0, 1, "L")                           # new command -> redo invalidated
    assert not doc.can_redo()


def test_undo_covers_destructive_commands(doc):
    names = [s["name"] for s in doc.model.signals]
    doc.new_document()
    doc.undo()
    assert [s["name"] for s in doc.model.signals] == names
    gid = doc.group_signals([1, 2], name="G")
    doc.delete_group(gid)
    assert len(doc.model.signals) == 1
    doc.undo()
    assert len(doc.model.signals) == 3 and gid in doc.model.groups
    assert_invariants(doc.model)


def test_undo_emits_document_scope(doc, events):
    doc.set_cell(0, 0, "H")
    events.clear()
    doc.undo()
    assert events == [{"document"}]


# ---------------------------------------------------------------- paste / template
def test_paste_signals_fresh_sids_after_insert_point(doc):
    payloads = [{"name": "CLK", "offset": 0.0, "color": None,
                 "cells": [{"type": "H", "text": ""}] * 12}]
    before = {s["sid"] for s in doc.model.signals}
    newidx = doc.paste_signals(payloads, at_idx=0)
    assert len(newidx) == 1
    ns = doc.model.signals[newidx[0]]
    assert ns["sid"] not in before                    # rule 2
    assert ns["name"] == "CLK_2"                      # name clash renamed
    assert newidx[0] == 1                             # inserted after CLK
    assert_invariants(doc.model)


def test_paste_group_and_template(doc):
    res = doc.paste_group({"name": "SPI", "color": "#123456",
                           "signals": [{"name": "MOSI", "cells": [{"type": "L", "text": ""}] * 4}]})
    gname, newidx = res
    gid = doc.model.signals[newidx[0]]["group"]
    assert doc.model.groups[gid]["color"] == "#123456"
    res2 = doc.insert_template("SPI", [{"name": "MISO", "cells": []}])
    assert res2[0] == "SPI_2"                         # group name clash renamed
    assert len(doc.model.signals[-1]["cells"]) == doc.model.n_periods   # periods padded
    assert doc.paste_group(None) is None
    assert doc.insert_template("X", []) is None
    assert_invariants(doc.model)


# ---------------------------------------------------------------- annotations
def test_anchor_edge_commands(doc, events):
    sid = doc.model.signals[0]["sid"]
    a = doc.add_anchor(sid, 1, "start")
    b = doc.add_anchor(doc.model.signals[1]["sid"], 3, "end")
    assert a and b
    assert doc.add_anchor(999, 0, "start") is None    # invalid sid
    assert doc.add_edge(a, a) is None                 # self-loop
    assert doc.add_edge(a, b, "t_su") is not None
    assert doc.set_edge_label(0, "t_h") and doc.set_edge_style(0, "single")
    assert doc.remove_edge(5) is False
    assert doc.remove_edge(0) is True
    assert doc.remove_anchor(a) and not doc.remove_anchor(a)
    assert all(s == {"annotations"} for s in events if s != set())
    assert_invariants(doc.model)


def test_unique_name():
    assert unique_name("A", set()) == "A"
    assert unique_name("A", {"A"}) == "A_2"
    assert unique_name("A", {"A", "A_2"}) == "A_3"
