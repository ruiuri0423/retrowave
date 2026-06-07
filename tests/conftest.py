# -*- coding: utf-8 -*-
"""pytest 共用設定：將 src/ 加入匯入路徑，提供不變量檢查與假事件工具。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import retrowave  # noqa: E402


class Ev:
    """模擬 tkinter 事件（只帶 handlers 會用到的欄位）。"""

    def __init__(self, x=0, y=0, state=0, delta=0, num=0):
        self.x, self.y, self.state = x, y, state
        self.delta, self.num = delta, num


def assert_invariants(m):
    """設計文件 §2.6：每次編輯後必須成立的不變量。"""
    # 1. sid 唯一
    sids = [s["sid"] for s in m.signals]
    assert len(sids) == len(set(sids)), f"sid 重複: {sids}"

    # 2. signals 順序 == 群組樹 DFS 葉序
    leaf_order = [nd["sid"] for nd in m._dfs_leaves()]
    assert sids == leaf_order, f"signals 順序 {sids} != DFS 葉序 {leaf_order}"

    # 3. 樹中不殘留 marker、群組不為空
    def walk(nodes):
        for nd in nodes:
            assert nd.get("type") in ("sig", "group"), f"殘留非法節點: {nd}"
            if nd.get("type") == "group":
                assert nd.get("children"), f"殘留空群組: {nd.get('gid')}"
                walk(nd["children"])
    walk(m.group_tree)

    # 4. groups dict 與樹節點一一對應（且為同一物件）
    tree_nodes = {nd["gid"]: nd for nd in m._all_group_nodes()}
    assert set(m.groups) == set(tree_nodes)
    for gid in m.groups:
        assert m.groups[gid] is tree_nodes[gid]

    # 5. signal['group'] 快取 == 樹中的直接父群組
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
            f"signal {s['name']} group 快取 {s.get('group')} 與樹不符"

    # 6. 標注以有效 sid 錨定；關係線端點都是有效錨點
    valid = set(sids)
    for nid, nd in m.nodes.items():
        assert nd.get("sid") in valid, f"錨點 {nid} 指向不存在的 sid"
    for e in m.edges:
        assert e["frm"] in m.nodes and e["to"] in m.nodes, f"關係線端點失效: {e}"

    # 7. 每條訊號 cells 長度 == n_periods
    for s in m.signals:
        assert len(s["cells"]) == m.n_periods

    # 8. 全展開時 layout 列數 = 訊號數 + 群組數（群組標頭也佔列）
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
    """整個測試 session 共用一個 Tk root。
    （同行程內反覆 create/destroy Tk 會觸發 Tcl 的 tcl_findLibrary 錯誤。）"""
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
    """每個測試前把共用 App 重置回 __init__ 後的乾淨狀態。"""
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
    """layout 第 row 列、第 period 週期的格子中心（視窗座標，視圖在原點時等於畫布座標）。"""
    g = app_.geom
    return (period * g.period_w + g.period_w // 2,
            g.header_h + row * g.row_h + g.row_h // 2)
