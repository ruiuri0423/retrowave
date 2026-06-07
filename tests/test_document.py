# -*- coding: utf-8 -*-
"""v1.24 傳遞層測試（headless，不開視窗）：
命令路由、錯誤策略四條、事件合併派發、手勢交易、快照式 Undo/Redo（深度 5）。"""
import pytest

from retrowave.document import Document, unique_name
from conftest import assert_invariants


@pytest.fixture
def doc():
    return Document()                        # scheduler=None → 事件同步派發


@pytest.fixture
def events(doc):
    log = []
    doc.subscribe(lambda scopes: log.append(set(scopes)))
    return log


# ---------------------------------------------------------------- 命令 + 事件
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
    doc = Document(scheduler=queued.append)  # 假 scheduler：收集 flush
    log = []
    doc.subscribe(lambda scopes: log.append(set(scopes)))
    doc.set_cell(0, 0, "H")
    doc.add_signal("X")
    doc.set_cell(0, 1, "L")
    assert log == [] and len(queued) == 1    # 三個命令 → 只排程一次 flush
    queued[0]()                              # 模擬 idle
    assert log == [{"cells", "structure"}]   # 合併為一次通知（scope 聯集）


# ---------------------------------------------------------------- 錯誤策略
def test_invalid_returns_false_no_event_no_undo(doc, events):
    assert doc.set_cell(99, 0, "H") is False          # 越界 → False（策略 4：無靜默第三態）
    assert doc.set_cell(0, 99, "H") is False
    assert doc.remove_signals([99]) == 0
    assert doc.rename_signal(0, "") is False
    assert doc.set_offset([], 0.5) == 0
    assert doc.delete_group("no_such") == 0
    assert doc.toggle_group("no_such") is None
    assert doc.move_leaf_to(999, None, 0) is False    # 不存在的 sid
    assert events == [] and not doc.can_undo()        # 失敗不發事件、不入 undo
    assert_invariants(doc.model)


def test_move_group_into_descendant_refused_atomic(doc, events):
    g1 = doc.group_signals([0], name="A")
    g2 = doc.group_signals([2], name="B")
    doc.merge_groups(g2, g1)
    snap = doc.model.to_dict()
    events.clear()
    assert doc.move_group_to(g1, g2, 0) is False      # 使用者級不合法
    assert doc.model.to_dict() == snap                # 文件不變（原子）
    assert events == []
    assert_invariants(doc.model)


def test_load_document_bad_data_raises_and_restores(doc):
    before = doc.model.to_dict()
    with pytest.raises(Exception):
        doc.load_document({"signals": "garbage"})     # 程式級錯誤 → 拋例外
    assert doc.model.to_dict() == before              # 且文件還原（原子）
    assert_invariants(doc.model)


# ---------------------------------------------------------------- 手勢交易
def test_transaction_is_single_undo_unit(doc):
    doc.begin()
    for p in range(5):
        doc.set_cell(0, p, "H")
    assert not doc.can_undo()                         # 交易中不結算
    assert doc.commit() is True
    assert len(doc._undo) == 1                        # 五次 set_cell = 一個 undo 單位
    doc.undo()
    assert all(c["type"] == "CLK" for c in doc.model.signals[0]["cells"][:5])
    assert_invariants(doc.model)


def test_empty_transaction_not_recorded(doc):
    doc.begin()
    assert doc.commit() is False                      # 無變更 → 不入棧
    assert not doc.can_undo()


def test_transaction_events_still_flow(doc, events):
    doc.begin()
    doc.set_cell(0, 0, "H")
    doc.set_cell(0, 1, "H")
    doc.commit()
    assert events == [{"cells"}, {"cells"}]           # 交易中即時發事件（同步 scheduler 下逐次）


# ---------------------------------------------------------------- Undo / Redo
def test_undo_redo_roundtrip(doc):
    doc.set_cell(0, 0, "H")
    doc.rename_signal(2, "BUS_A")
    assert doc.undo() is True
    assert doc.model.signals[2]["name"] == "DATA"
    assert doc.undo() is True
    assert doc.model.signals[0]["cells"][0]["type"] == "CLK"
    assert doc.undo() is False                        # 棧空
    assert doc.redo() is True and doc.model.signals[0]["cells"][0]["type"] == "H"
    assert doc.redo() is True and doc.model.signals[2]["name"] == "BUS_A"
    assert doc.redo() is False
    assert_invariants(doc.model)


def test_undo_depth_limited_to_5(doc):
    for p in range(7):                                # 7 個命令，深度 5
        doc.set_cell(0, p, "H")
    n = 0
    while doc.undo():
        n += 1
    assert n == Document.UNDO_DEPTH == 5
    # 最早兩步已被擠出：T0/T1 仍是 H，T2.. 已還原
    assert doc.model.signals[0]["cells"][0]["type"] == "H"
    assert doc.model.signals[0]["cells"][2]["type"] == "CLK"
    assert_invariants(doc.model)


def test_new_command_clears_redo(doc):
    doc.set_cell(0, 0, "H")
    doc.undo()
    assert doc.can_redo()
    doc.set_cell(0, 1, "L")                           # 新命令 → redo 失效
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


# ---------------------------------------------------------------- 貼上 / 範本
def test_paste_signals_fresh_sids_after_insert_point(doc):
    payloads = [{"name": "CLK", "offset": 0.0, "color": None,
                 "cells": [{"type": "H", "text": ""}] * 12}]
    before = {s["sid"] for s in doc.model.signals}
    newidx = doc.paste_signals(payloads, at_idx=0)
    assert len(newidx) == 1
    ns = doc.model.signals[newidx[0]]
    assert ns["sid"] not in before                    # 鐵則 2
    assert ns["name"] == "CLK_2"                      # 撞名改名
    assert newidx[0] == 1                             # 插在 CLK 之後
    assert_invariants(doc.model)


def test_paste_group_and_template(doc):
    res = doc.paste_group({"name": "SPI", "color": "#123456",
                           "signals": [{"name": "MOSI", "cells": [{"type": "L", "text": ""}] * 4}]})
    gname, newidx = res
    gid = doc.model.signals[newidx[0]]["group"]
    assert doc.model.groups[gid]["color"] == "#123456"
    res2 = doc.insert_template("SPI", [{"name": "MISO", "cells": []}])
    assert res2[0] == "SPI_2"                         # 群組撞名改名
    assert len(doc.model.signals[-1]["cells"]) == doc.model.n_periods   # 補齊週期
    assert doc.paste_group(None) is None
    assert doc.insert_template("X", []) is None
    assert_invariants(doc.model)


# ---------------------------------------------------------------- 標注
def test_anchor_edge_commands(doc, events):
    sid = doc.model.signals[0]["sid"]
    a = doc.add_anchor(sid, 1, "start")
    b = doc.add_anchor(doc.model.signals[1]["sid"], 3, "end")
    assert a and b
    assert doc.add_anchor(999, 0, "start") is None    # 無效 sid
    assert doc.add_edge(a, a) is None                 # 自迴圈
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
