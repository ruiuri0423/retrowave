# -*- coding: utf-8 -*-
"""文件核心（邏輯單元）：訊號池 + 群組樹 + 標注 + 持久化。
完全 headless（不得 import tkinter）。設計文件 §2/§5/§10；
不變量 §2.6 的可執行版本在 tests/conftest.py::assert_invariants。

呼叫追蹤（閱讀/除錯用）：設環境變數 RETROWAVE_TRACE=1 後啟動，
Model 的每個方法呼叫會以縮排樹印到 stderr（高頻唯讀方法 layout/new_cell 除外；
RETROWAVE_TRACE=all 連它們也追）。預設關閉，零開銷。"""
import functools
import os
import sys
from collections import namedtuple

# 可見列：kind='group'|'sig'；ref=gid 或 signal index；depth=巢狀深度；gcol=繼承的群組色
Row = namedtuple("Row", "kind ref depth gcol")

DEFAULT_PERIODS = 12


class Model:
    def __init__(self):
        self.n_periods = DEFAULT_PERIODS; self.signals = []
        self.groups = {}              # gid -> group 節點 (由群組樹重建，供既有程式以 gid 取 meta)
        self.group_tree = []          # 結構真相：巢狀群組樹 (節點見下)，葉以 sid 參考訊號實體
        self.nodes = {}               # nid -> {sid, period, edge}  (標注錨點)
        self.edges = []               # [{frm, to, label, style}]   (關係線)
        self._gid_seq = 0; self._sid_seq = 0
        self.add_signal("CLK", fill="CLK")
        self.add_signal("RST_N", fill="H")
        self.add_signal("DATA", fill="L")
        self._demo()

    def _new_sid(self):
        self._sid_seq += 1
        return self._sid_seq

    def _demo(self):
        d = self.signals[2]["cells"]
        d[2] = self.new_cell("BUS", "A5"); d[3] = self.new_cell("BUS", "A5")
        d[4] = self.new_cell("BUS", "0F"); d[5] = self.new_cell("HiZ")
        d[6] = self.new_cell("BUS", "0x4"); d[7] = self.new_cell("H"); d[8] = self.new_cell("L")

    def new_cell(self, t="L", text=""):
        return {"type": t, "text": text}

    def add_signal(self, name=None, fill="L"):
        if name is None:
            name = f"SIG{len(self.signals)}"
        sid = self._new_sid()
        self.signals.append({"name": name, "offset": 0.0, "color": None, "group": None,
                             "sid": sid,
                             "cells": [self.new_cell(fill) for _ in range(self.n_periods)]})
        self.group_tree.append({"type": "sig", "sid": sid})   # 新訊號落在頂層 (葉序==signals 序)

    def remove_signal(self, idx):
        if 0 <= idx < len(self.signals):
            sid = self.signals[idx]["sid"]
            del self.signals[idx]
            self._detach_sid(sid)
            self._prune_empty_groups(self.group_tree)
            self._reindex_groups()

    def set_n_periods(self, n):
        n = max(1, int(n))
        if n > self.n_periods:
            for s in self.signals:
                s["cells"] += [self.new_cell("L") for _ in range(n - self.n_periods)]
        elif n < self.n_periods:
            for s in self.signals:
                del s["cells"][n:]
        self.n_periods = n

    def set_cell(self, sig, per, t, text=""):
        if 0 <= sig < len(self.signals) and 0 <= per < self.n_periods:
            self.signals[sig]["cells"][per] = self.new_cell(t, text)

    # ---- 群組 (群組樹為結構真相；signals 維持與 DFS 葉序一致；signal['group']=直接父 gid 快取) ----
    def layout(self):
        """遞迴展開群組樹，回傳可見列 Row(kind, ref, depth, gcol)。
        群組列 ref=gid、gcol=該群自身色；訊號列 ref=signal index、gcol=繼承最近祖先群組色。
        折疊的群組不展開其 children。"""
        rows = []
        sid2idx = {s["sid"]: i for i, s in enumerate(self.signals)}

        def walk(nodes, depth, inh):
            for nd in nodes:
                if nd.get("type") == "group":
                    rows.append(Row("group", nd["gid"], depth, nd.get("color")))
                    if not nd.get("collapsed"):
                        walk(nd.get("children", []), depth + 1, nd.get("color") or inh)
                else:
                    si = sid2idx.get(nd.get("sid"))
                    if si is not None:
                        rows.append(Row("sig", si, depth, inh))
        walk(self.group_tree, 0, None)
        return rows

    # ---- 群組樹的低階操作 ----
    def _dfs_leaves(self, nodes=None):
        if nodes is None:
            nodes = self.group_tree
        out = []
        for nd in nodes:
            if nd.get("type") == "group":
                out += self._dfs_leaves(nd.get("children", []))
            else:
                out.append(nd)
        return out

    def _detach_sid(self, sid):
        def rec(nodes):
            for k, nd in enumerate(nodes):
                if nd.get("type") == "sig" and nd.get("sid") == sid:
                    return nodes.pop(k)
                if nd.get("type") == "group":
                    r = rec(nd.get("children", []))
                    if r is not None:
                        return r
            return None
        return rec(self.group_tree)

    def _find_group_node(self, gid, nodes=None):
        if nodes is None:
            nodes = self.group_tree
        for nd in nodes:
            if nd.get("type") == "group":
                if nd["gid"] == gid:
                    return nd
                r = self._find_group_node(gid, nd.get("children", []))
                if r is not None:
                    return r
        return None

    def _find_leaf_loc(self, sid):
        """回傳 (children_list, index) 指向該 sid 的葉節點，找不到回 None。"""
        def rec(nodes):
            for k, nd in enumerate(nodes):
                if nd.get("type") == "sig" and nd.get("sid") == sid:
                    return nodes, k
                if nd.get("type") == "group":
                    r = rec(nd.get("children", []))
                    if r:
                        return r
            return None
        return rec(self.group_tree)

    def _locate(self, pred, nodes=None, parent_gid=None):
        """回傳 (parent_gid, children_list, index)，parent_gid=None 表示頂層。"""
        if nodes is None:
            nodes = self.group_tree
        for k, nd in enumerate(nodes):
            if pred(nd):
                return parent_gid, nodes, k
            if nd.get("type") == "group":
                r = self._locate(pred, nd.get("children", []), nd["gid"])
                if r:
                    return r
        return None

    def _container_children(self, gid):
        if gid is None:
            return self.group_tree
        node = self._find_group_node(gid)
        return node.get("children") if node is not None else None

    def _is_self_or_descendant(self, gid, other):
        """other 是否為 gid 自己或其子孫群組。"""
        if gid == other:
            return True
        node = self._find_group_node(gid)
        if node is None:
            return False
        return self._find_group_node(other, node.get("children", [])) is not None

    def move_leaf_to(self, sid, container_gid, index):
        """把訊號葉移到指定容器(None=頂層)的 children 指定位置。標記法自動修正索引位移。"""
        cont = self._container_children(container_gid)
        if cont is None:
            return False
        index = max(0, min(len(cont), index))
        marker = {"type": "_marker"}
        cont.insert(index, marker)
        _t(f"step1: marker 插入 {container_gid or '頂層'}[{index}]")
        node = self._detach_sid(sid)
        if node is None:
            _t("sid 不在樹中 -> 撤回 marker")
            cont.remove(marker); self._after_tree_change(); return False
        _t(f"step2/3: 已摘下葉 sid={sid}，取代 marker")
        cont[cont.index(marker)] = node
        self._after_tree_change()
        return True

    def move_group_to(self, gid, container_gid, index):
        """把群組移到指定容器指定位置 (容器為群組則成巢狀)。防呆：不可移入自己或子孫。"""
        if self._find_group_node(gid) is None:
            return False
        if container_gid is not None and self._is_self_or_descendant(gid, container_gid):
            _t(f"防呆: {container_gid} 是 {gid} 自己或其子孫，拒絕移動")
            return False
        cont = self._container_children(container_gid)
        if cont is None:
            return False
        index = max(0, min(len(cont), index))
        marker = {"type": "_marker"}
        cont.insert(index, marker)
        _t(f"step1: marker 插入 {container_gid or '頂層'}[{index}]")
        node = self._detach_group(gid)
        if node is None:
            _t("群組不在樹中 -> 撤回 marker")
            cont.remove(marker); self._after_tree_change(); return False
        _t(f"step2/3: 已摘下群組 {gid}，取代 marker")
        cont[cont.index(marker)] = node
        self._after_tree_change()
        return True

    def _detach_group(self, gid):
        def rec(nodes):
            for k, nd in enumerate(nodes):
                if nd.get("type") == "group":
                    if nd["gid"] == gid:
                        return nodes.pop(k)
                    r = rec(nd.get("children", []))
                    if r is not None:
                        return r
            return None
        return rec(self.group_tree)

    def _top_index_of_sid(self, sid):
        for k, nd in enumerate(self.group_tree):
            if nd.get("type") == "sig" and nd.get("sid") == sid:
                return k
            if nd.get("type") == "group" and any(l.get("sid") == sid
                                                 for l in self._dfs_leaves(nd.get("children", []))):
                return k
        return len(self.group_tree)

    def _prune_empty_groups(self, nodes):
        i = 0
        while i < len(nodes):
            nd = nodes[i]
            if nd.get("type") == "group":
                self._prune_empty_groups(nd.get("children", []))
                if not nd.get("children"):
                    _t(f"剪除空群組 {nd.get('gid')}")
                    del nodes[i]; continue
            i += 1

    def _resync_signals(self):
        order = [nd["sid"] for nd in self._dfs_leaves()]
        present = set(order)
        for s in self.signals:                  # 保險：樹中遺漏的訊號補回頂層
            if s["sid"] not in present:
                _t(f"修復: 樹漏列 sid={s['sid']} -> 補回頂層")
                self.group_tree.append({"type": "sig", "sid": s["sid"]})
                order.append(s["sid"]); present.add(s["sid"])
        by = {s["sid"]: s for s in self.signals}
        self.signals = [by[sid] for sid in order if sid in by]

    def _reindex_groups(self):
        self.groups = {}
        by = {s["sid"]: s for s in self.signals}

        def rec(nodes, parent_gid):
            for nd in nodes:
                if nd.get("type") == "group":
                    nd.setdefault("collapsed", False); nd.setdefault("color", None)
                    nd.setdefault("name", nd["gid"])
                    self.groups[nd["gid"]] = nd
                    rec(nd.get("children", []), nd["gid"])
                else:
                    s = by.get(nd.get("sid"))
                    if s is not None:
                        s["group"] = parent_gid       # 直接父群組 gid 快取
        rec(self.group_tree, None)

    def _after_tree_change(self):
        self._prune_empty_groups(self.group_tree)
        self._resync_signals()
        self._reindex_groups()

    def new_gid(self):
        self._gid_seq += 1
        gid = f"g{self._gid_seq}"
        while self._find_group_node(gid) is not None:
            self._gid_seq += 1; gid = f"g{self._gid_seq}"
        return gid

    def group_signals(self, indices, name=None):
        """把選取訊號組成一個全新群組 (插在第一個選取者所在的頂層位置)。回傳 gid。"""
        sids = [self.signals[i]["sid"] for i in indices if 0 <= i < len(self.signals)]
        order = {nd["sid"]: k for k, nd in enumerate(self._dfs_leaves())}
        sids = sorted(set(sids), key=lambda s: order.get(s, 1 << 30))
        if not sids:
            return None
        _t(f"選取按葉序排序: sids={sids}")
        marker = {"type": "_marker"}
        self.group_tree.insert(self._top_index_of_sid(sids[0]), marker)
        _t(f"marker 插在第一個成員 sid={sids[0]} 的頂層位置")
        children = [c for c in (self._detach_sid(s) for s in sids) if c]
        _t(f"摘下 {len(children)} 葉作為新群組 children")
        gid = self.new_gid()
        node = {"type": "group", "gid": gid, "name": name or f"群組{self._gid_seq}",
                "collapsed": False, "color": None, "children": children}
        self.group_tree[self.group_tree.index(marker)] = node
        self._after_tree_change()
        return gid

    def merge_into_group(self, indices, target_gid):
        """把選取訊號移入指定群組 (附加到該群 children 尾端)。"""
        tgt = self._find_group_node(target_gid)
        if tgt is None:
            return None
        sids = [self.signals[i]["sid"] for i in indices if 0 <= i < len(self.signals)]
        order = {nd["sid"]: k for k, nd in enumerate(self._dfs_leaves())}
        sids = sorted(set(sids), key=lambda s: order.get(s, 1 << 30))
        for s in sids:
            if self.signals[[x["sid"] for x in self.signals].index(s)].get("group") == target_gid:
                _t(f"sid={s} 已在 {target_gid}，跳過")
                continue
            node = self._detach_sid(s)
            if node:
                tgt["children"].append(node)
                _t(f"sid={s} 附加到 {target_gid} children 尾端")
        self._after_tree_change()
        return target_gid

    def merge_groups(self, src_gid, target_gid):
        """把 src 群組整個移入 target 群組成為其子群組 (巢狀)。"""
        if src_gid == target_gid:
            return None
        tgt = self._find_group_node(target_gid)
        if tgt is None:
            return None
        # 不可把群組移進自己的子孫
        if self._find_group_node(target_gid, [self._find_group_node(src_gid)] if
                                 self._find_group_node(src_gid) else []):
            return None
        node = self._detach_group(src_gid)
        if node is None:
            self._after_tree_change(); return None
        tgt["children"].append(node)
        _t(f"群組 {src_gid} 整棵巢入 {target_gid} 成為子群組")
        self._after_tree_change()
        return target_gid

    def remove_from_group(self, indices):
        """把選取的(有群組)訊號移到頂層 (移出所有群組)；移出後色彩回預設。回傳數量。"""
        sids = [self.signals[i]["sid"] for i in indices
                if 0 <= i < len(self.signals) and self.signals[i].get("group")]
        order = {nd["sid"]: k for k, nd in enumerate(self._dfs_leaves())}
        sids = sorted(set(sids), key=lambda s: order.get(s, 1 << 30))
        if not sids:
            return 0
        marker = {"type": "_marker"}
        self.group_tree.insert(self._top_index_of_sid(sids[0]), marker)
        moved = 0
        by = {s["sid"]: s for s in self.signals}
        for s in sids:
            node = self._detach_sid(s)
            if node:
                at = self.group_tree.index(marker)
                self.group_tree.insert(at + 1, node)
                if by.get(s):
                    by[s]["color"] = None
                moved += 1
                _t(f"sid={s} 重插於 marker 之後（頂層[{at + 1}]），清除自訂色")
        self.group_tree.remove(marker)
        _t("移除 marker")
        self._after_tree_change()
        return moved

    def ungroup(self, gids):
        """解散群組：把其 children 就地提升一層 (保留巢狀子群組與成員)。"""
        gids = set(gids)

        def rec(nodes):
            i = 0
            while i < len(nodes):
                nd = nodes[i]
                if nd.get("type") == "group":
                    rec(nd.get("children", []))
                    if nd["gid"] in gids:
                        kids = nd.get("children", [])
                        _t(f"解散 {nd['gid']}：{len(kids)} 個 children 就地提升一層")
                        nodes[i:i + 1] = kids
                        i += len(kids); continue
                i += 1
        rec(self.group_tree)
        self._after_tree_change()

    def delete_group(self, gid):
        """刪除群組連同其整棵子樹的所有訊號。回傳刪除的訊號數。"""
        node = self._detach_group(gid)
        if node is None:
            return 0
        sids = {l["sid"] for l in self._dfs_leaves([node])}
        _t(f"子樹葉 sids={sorted(sids)} 自訊號池移除")
        self.signals = [s for s in self.signals if s["sid"] not in sids]
        self._after_tree_change()
        self.prune_annotations()
        return len(sids)

    def prune_groups(self):
        self._prune_empty_groups(self.group_tree)
        self._reindex_groups()

    # ---- 標注 (錨點 node + 關係線 edge；獨立層，以 sid 錨定不受重排影響) ----
    def new_nid(self):
        import string
        for ch in string.ascii_lowercase:
            if ch not in self.nodes:
                return ch
        for a in string.ascii_lowercase:
            for b in string.ascii_lowercase:
                if (a + b) not in self.nodes:
                    return a + b
        return f"n{len(self.nodes)}"

    def add_node(self, sid, period, edge):
        nid = self.new_nid()
        self.nodes[nid] = {"sid": sid, "period": int(period), "edge": edge}
        return nid

    def remove_node(self, nid):
        self.nodes.pop(nid, None)
        self.edges = [e for e in self.edges if e["frm"] != nid and e["to"] != nid]

    def add_edge(self, frm, to, label="", style="double"):
        if frm == to or frm not in self.nodes or to not in self.nodes:
            return None
        self.edges.append({"frm": frm, "to": to, "label": label, "style": style})
        return self.edges[-1]

    def prune_annotations(self):
        valid_sids = {s.get("sid") for s in self.signals}
        orphan_nodes = [n for n, nd in self.nodes.items() if nd.get("sid") not in valid_sids]
        before_edges = len(self.edges)
        if orphan_nodes:
            _t(f"清除孤兒錨點 {orphan_nodes}（其 sid 已不存在）")
        for nid in orphan_nodes:
            self.remove_node(nid)
        self.edges = [e for e in self.edges
                      if e["frm"] in self.nodes and e["to"] in self.nodes]
        return len(orphan_nodes), before_edges - len(self.edges)   # (清除錨點數, 清除關係線數)

    def to_dict(self):
        return {"version": "2.0", "n_periods": self.n_periods,
                "signals": self.signals, "group_tree": self.group_tree,
                "nodes": self.nodes, "edges": self.edges}

    def _migrate_flat_to_tree(self, gmeta):
        """舊格式 (signal['group']=gid + groups dict) -> 單層群組樹。"""
        self.group_tree = []; i = 0; n = len(self.signals)
        while i < n:
            g = self.signals[i].get("group")
            meta = gmeta.get(g) if isinstance(gmeta, dict) else None
            if g and isinstance(meta, dict):
                node = {"type": "group", "gid": g, "name": meta.get("name", g),
                        "collapsed": meta.get("collapsed", False),
                        "color": meta.get("color"), "children": []}
                while i < n and self.signals[i].get("group") == g:
                    node["children"].append({"type": "sig", "sid": self.signals[i]["sid"]}); i += 1
                self.group_tree.append(node)
            else:
                self.group_tree.append({"type": "sig", "sid": self.signals[i]["sid"]}); i += 1

    def load_dict(self, d):
        self.n_periods = int(d.get("n_periods", DEFAULT_PERIODS))
        self.signals = d.get("signals", [])
        self.nodes = d.get("nodes", {})
        self.edges = d.get("edges", [])
        self._sid_seq = 0
        for s in self.signals:
            s.setdefault("offset", 0.0)
            s.setdefault("color", None)
            s.setdefault("group", None)
            if not s.get("sid"):
                s["sid"] = self._new_sid()
            else:
                self._sid_seq = max(self._sid_seq, int(s["sid"]))
            cells = s.get("cells", [])
            while len(cells) < self.n_periods:
                cells.append(self.new_cell("L"))
            del cells[self.n_periods:]
            s["cells"] = cells
        _t(f"載入 {len(self.signals)} 條訊號（n_periods={self.n_periods}，sid 序號還原至 {self._sid_seq}）")
        gt = d.get("group_tree")
        if gt is not None:                      # 新格式：直接採用群組樹
            _t("新格式: 直接採用 group_tree")
            self.group_tree = gt
        else:                                   # 舊格式：扁平群組 -> 樹 (向後相容)
            _t("舊格式: 扁平 groups -> 樹遷移")
            self._migrate_flat_to_tree(d.get("groups", {}))
        # 還原 gid 序號 (避免新建群組撞名)
        self._gid_seq = 0
        for nd in self._all_group_nodes():
            try:
                self._gid_seq = max(self._gid_seq, int(str(nd["gid"]).lstrip("g") or 0))
            except ValueError:
                pass
        self._after_tree_change()
        return self.prune_annotations()        # (清除錨點數, 清除關係線數)

    def _all_group_nodes(self, nodes=None):
        if nodes is None:
            nodes = self.group_tree
        out = []
        for nd in nodes:
            if nd.get("type") == "group":
                out.append(nd); out += self._all_group_nodes(nd.get("children", []))
        return out


# ============================================================================
# 呼叫追蹤（閱讀/除錯用；RETROWAVE_TRACE=1 啟用，預設關閉、零開銷）
# ----------------------------------------------------------------------------
#   輸出（stderr），縮排 = 呼叫深度：
#     >  進入（含參數）              <  返回（僅在有回傳值時印）
#     .  方法內的細步（_t()：marker 三步驟、對帳修復、載檔階段…）
#     ~  狀態差異（方法返回時自動 diff：樹形/池序/群組/標注/週期，
#        只印有變的面向 — 每一步的「淨效果」一目了然，連樹中暫存的
#        #marker 都看得見）
#   範例：
#     [model] > move_leaf_to(1, 'g1', 1)
#     [model]   . step1: marker 插入 g1[1]
#     [model]   > _detach_sid(1)
#     [model]     ~ tree: [1, g1(2, #marker, 3)] -> [g1(2, #marker, 3)]
#     [model]   . step2/3: 已摘下葉 sid=1，取代 marker
#     ...
# ============================================================================
TRACE = os.environ.get("RETROWAVE_TRACE", "")
_TRACE_ON = bool(TRACE) and TRACE != "0"
_TRACE_SKIP = () if TRACE == "all" else ("layout", "new_cell")   # 高頻唯讀方法預設不追
_DEPTH = [0]


def _trace_repr(v, limit=48):
    r = repr(v)
    return r #if len(r) <= limit else r[:limit - 1] + "…"


def _t(msg):
    """方法內的細步追蹤點；TRACE 關閉時為 no-op（一次旗標判斷的成本）。"""
    if _TRACE_ON:
        print(f"[model] {'  ' * _DEPTH[0]}. {msg}", file=sys.stderr)


def _tree_repr(nodes):
    """群組樹的單行精簡表示：葉=sid、群組=gid(children)、折疊=gid*、暫存=#marker。"""
    parts = []
    for nd in nodes:
        t = nd.get("type")
        if t == "group":
            mark = "*" if nd.get("collapsed") else ""
            parts.append(f"{nd.get('gid')}{mark}({_tree_repr(nd.get('children', []))})")
        elif t == "sig":
            parts.append(str(nd.get("sid")))
        else:
            parts.append("#marker")
    return ", ".join(parts)


def _snapshot(m):
    return {
        "tree": f"[{_tree_repr(m.group_tree)}]",
        "pool": [s.get("sid") for s in m.signals],
        "groups": sorted(m.groups),
        "nodes": sorted(m.nodes),
        "edges": len(m.edges),
        "n_periods": m.n_periods,
    }


def _install_trace(cls):
    def wrap(name, fn):
        @functools.wraps(fn)
        def traced(self, *a, **kw):
            pad = "  " * _DEPTH[0]
            args = ", ".join([_trace_repr(x) for x in a]
                             + [f"{k}={_trace_repr(v)}" for k, v in kw.items()])
            print(f"[model] {pad}> {name}({args})", file=sys.stderr)
            before = _snapshot(self)
            _DEPTH[0] += 1
            try:
                out = fn(self, *a, **kw)
            finally:
                _DEPTH[0] -= 1
            after = _snapshot(self)
            for key, prev in before.items():
                if prev != after[key]:
                    print(f"[model] {pad}  ~ {key}: {prev} -> {after[key]}", file=sys.stderr)
            if out is not None:
                print(f"[model] {pad}< {name} -> {_trace_repr(out)}", file=sys.stderr)
            return out
        return traced

    for name, fn in list(vars(cls).items()):
        if name.startswith("__") or name in _TRACE_SKIP or not callable(fn):
            continue
        setattr(cls, name, wrap(name, fn))


if _TRACE_ON:
    _install_trace(Model)
