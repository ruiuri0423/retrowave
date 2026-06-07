# -*- coding: utf-8 -*-
"""
RetroWave - 數位電路波型繪製工具 (原型 v1.18)
本版重點 :
  1. 所有轉換線斜率統一 = 擺幅/tw (BUS↔HiZ 不再不一致)。
  2/3/4. BUS 拖曳：原為 BUS 的格保留延續、非 BUS 的格才取代 (不蓋既有資料)。
  5. Ctrl+拖曳框選 -> Ctrl+C/V 複製貼上；貼上超出列數自動新增列。
  6. 名稱欄 Ctrl/Shift 多選訊號，位移欄一次套用到所有選取訊號。
  7. 移除「選取」鈕，改用 Shift/Ctrl 修飾鍵 (Windows 慣例)。

風格 : Windows 95/XP 米白主題    框架 : Python 標準庫 tkinter
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, colorchooser
import json
import os
import math
from collections import namedtuple

# 可見列：kind='group'|'sig'；ref=gid 或 signal index；depth=巢狀深度；gcol=繼承的群組色
Row = namedtuple("Row", "kind ref depth gcol")

SHIFT_MASK = 0x0001
CTRL_MASK = 0x0004


class Style:
    FACE = "#ECE9D8"; FACE_DARK = "#ACA899"; CANVAS_BG = "#FBFBF6"
    GRID = "#C8C8C8"; DASH = "#B9B9A8"; WAVE = "#101010"; TEXT = "#202020"
    SEL = "#BFD9FF"; UNK_FILL = "#E79B9B"; UNK_HATCH = "#A83232"
    MARQUEE = "#1F5FBF"; MARQUEE_FILL = "#3A6EA5"
    UI_FONT = ("Tahoma", 9); KEY_FONT = ("Tahoma", 9, "bold")
    NAME_FONT = ("Tahoma", 9, "bold"); LABEL_FONT = ("Consolas", 9, "bold")
    BUS_FONT = ("Consolas", 9)


def make_key_button(parent, text, command, width=None):
    b = tk.Button(parent, text=text, command=command, font=Style.KEY_FONT,
                  bg=Style.FACE, activebackground="#F5F3E7",
                  relief=tk.RAISED, bd=3, padx=8, pady=3, highlightthickness=0)
    if width:
        b.configure(width=width)
    return b


WAVE_TYPES = ["CLK", "H", "L", "BUS", "HiZ", "Unknown"]
DEFAULT_PERIODS = 12


class Geometry:
    def __init__(self):
        self.period_w = 84; self.row_h = 64; self.header_h = 26
        self.name_w = 150; self.ramp_ratio = 0.20
        self.level_hi = 0.20; self.level_lo = 0.80

    def tw(self):
        return min(self.period_w * self.ramp_ratio, self.period_w * 0.45)

    def levels(self, row_top):
        hi = row_top + self.level_hi * self.row_h
        lo = row_top + self.level_lo * self.row_h
        return hi, (hi + lo) / 2.0, lo

    def to_dict(self):
        return {"period_w": self.period_w, "row_h": self.row_h, "ramp_ratio": self.ramp_ratio,
                "level_hi": self.level_hi, "level_lo": self.level_lo}

    def load(self, d):
        self.period_w = int(d.get("period_w", self.period_w))
        self.row_h = int(d.get("row_h", self.row_h))
        self.ramp_ratio = float(d.get("ramp_ratio", self.ramp_ratio))
        self.level_hi = float(d.get("level_hi", self.level_hi))
        self.level_lo = float(d.get("level_lo", self.level_lo))

    def copy_scaled(self, k):
        """回傳一份座標等比放大 k 倍的幾何 (比例欄位不變)；供高解析點陣匯出。"""
        g = Geometry()
        g.period_w = int(round(self.period_w * k)); g.row_h = int(round(self.row_h * k))
        g.header_h = int(round(self.header_h * k)); g.name_w = int(round(self.name_w * k))
        g.ramp_ratio = self.ramp_ratio
        g.level_hi = self.level_hi; g.level_lo = self.level_lo
        return g


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
        node = self._detach_sid(sid)
        if node is None:
            cont.remove(marker); self._after_tree_change(); return False
        cont[cont.index(marker)] = node
        self._after_tree_change()
        return True

    def move_group_to(self, gid, container_gid, index):
        """把群組移到指定容器指定位置 (容器為群組則成巢狀)。防呆：不可移入自己或子孫。"""
        if self._find_group_node(gid) is None:
            return False
        if container_gid is not None and self._is_self_or_descendant(gid, container_gid):
            return False
        cont = self._container_children(container_gid)
        if cont is None:
            return False
        index = max(0, min(len(cont), index))
        marker = {"type": "_marker"}
        cont.insert(index, marker)
        node = self._detach_group(gid)
        if node is None:
            cont.remove(marker); self._after_tree_change(); return False
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
                    del nodes[i]; continue
            i += 1

    def _resync_signals(self):
        order = [nd["sid"] for nd in self._dfs_leaves()]
        present = set(order)
        for s in self.signals:                  # 保險：樹中遺漏的訊號補回頂層
            if s["sid"] not in present:
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
        marker = {"type": "_marker"}
        self.group_tree.insert(self._top_index_of_sid(sids[0]), marker)
        children = [c for c in (self._detach_sid(s) for s in sids) if c]
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
                continue
            node = self._detach_sid(s)
            if node:
                tgt["children"].append(node)
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
        self.group_tree.remove(marker)
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
        gt = d.get("group_tree")
        if gt is not None:                      # 新格式：直接採用群組樹
            self.group_tree = gt
        else:                                   # 舊格式：扁平群組 -> 樹 (向後相容)
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
# 元件類別階層 (轉換線斜率統一 = 擺幅/tw)
# ============================================================================
class Element:
    name = ""; kind = "NONE"; accepts_text = False
    def exit_y(self, hi, mid, lo):  return None
    def entry_y(self, hi, mid, lo): return None
    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo): pass


class LevelElement(Element):
    kind = "LEVEL"
    def y(self, hi, mid, lo): raise NotImplementedError
    def exit_y(self, hi, mid, lo):  return self.y(hi, mid, lo)
    def entry_y(self, hi, mid, lo): return self.y(hi, mid, lo)

    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo):
        pw = geom.period_w; x1 = x0 + pw; tw = geom.tw(); W = 2; col = eng._wcol
        swing = lo - hi
        y = self.y(hi, mid, lo)
        pe = eng.elem(prev["type"]) if prev else None
        if pe is None:
            cv.create_line(x0, y, x1, y, fill=col, width=W)
        elif pe.kind == "DATA":                         # 前為 BUS：兩軌道收斂到本準位 (線右側, 統一斜率)
            whi = abs(hi - y) * tw / swing; wlo = abs(lo - y) * tw / swing
            xflat = x0 + min(whi, wlo)
            cv.create_line(xflat, y, x1, y, fill=col, width=W)
            if whi > 0.5: cv.create_line(x0, hi, x0 + whi, y, fill=col, width=W)
            if wlo > 0.5: cv.create_line(x0, lo, x0 + wlo, y, fill=col, width=W)
        elif pe.kind == "CLK":                          # CLK<->LEVEL：直角
            if abs(lo - y) > 0.5:
                cv.create_line(x0, lo, x0, y, fill=col, width=W)
            cv.create_line(x0, y, x1, y, fill=col, width=W)
        else:                                           # LEVEL<->LEVEL：統一斜率
            py = pe.exit_y(hi, mid, lo); dy = y - py
            if abs(dy) < 0.5:
                cv.create_line(x0, y, x1, y, fill=col, width=W)
            else:
                w = abs(dy) / swing * tw
                cv.create_line(x0, py, x0 + w, y, fill=col, width=W)
                cv.create_line(x0 + w, y, x1, y, fill=col, width=W)


class HighElement(LevelElement):
    name = "H"
    def y(self, hi, mid, lo): return hi


class LowElement(LevelElement):
    name = "L"
    def y(self, hi, mid, lo): return lo


class HiZElement(LevelElement):
    name = "HiZ"
    def y(self, hi, mid, lo): return mid


class ClkElement(Element):
    name = "CLK"; kind = "CLK"
    def exit_y(self, hi, mid, lo): return lo

    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo):
        pw = geom.period_w; x1 = x0 + pw; xm = x0 + pw / 2; W = 2; col = eng._wcol
        pt = prev["type"] if prev else None
        rise = eng.meet(pt, "CLK", hi, mid, lo) if pt else lo
        if rise is None:
            rise = lo
        if abs(rise - hi) > 0.5:
            cv.create_line(x0, rise, x0, hi, fill=col, width=W)
        cv.create_line(x0, hi, xm, hi, fill=col, width=W)
        cv.create_line(xm, hi, xm, lo, fill=col, width=W)
        cv.create_line(xm, lo, x1, lo, fill=col, width=W)


class BusElement(Element):
    name = "BUS"; kind = "DATA"; accepts_text = True
    fill = None; hatch = False; text_color = Style.TEXT

    def draw(self, eng, cv, geom, cell, prev, nxt, x0, hi, mid, lo):
        pw = geom.period_w; x1 = x0 + pw; tw = geom.tw(); W = 2; col = eng._wcol
        swing = lo - hi
        def wl(dv): return abs(dv) * tw / swing
        pt = prev["type"] if prev else None
        nt = nxt["type"] if nxt else None
        pe = eng.elem(pt); ne = eng.elem(nt)
        sameL = eng.same_data(prev, cell); sameR = eng.same_data(cell, nxt)
        trailing = (not sameR) and (ne is None or ne.kind == "CLK")
        prevDATA = (pe is not None and pe.kind == "DATA") and not sameL

        left_lines = []
        vyL = None
        if sameL:
            xLhi = xLlo = x0
        elif prevDATA:                                  # 資料變化 X 交叉
            xm = x0 + tw / 2
            left_lines += [(x0, hi, xm, mid), (x0, lo, xm, mid),
                           (xm, mid, x0 + tw, hi), (xm, mid, x0 + tw, lo)]
            xLhi = xLlo = x0 + tw
        else:                                           # 由 level/clk/none 開口
            vyL = eng.meet(pt, self.name, hi, mid, lo) or mid
            whi = wl(hi - vyL); wlo = wl(lo - vyL)
            if whi > 0.5: left_lines.append((x0, vyL, x0 + whi, hi))
            if wlo > 0.5: left_lines.append((x0, vyL, x0 + wlo, lo))
            xLhi = x0 + whi; xLlo = x0 + wlo

        right_lines = []
        if trailing:
            vyR = eng.meet(self.name, nt, hi, mid, lo) or mid
            whi = wl(hi - vyR); wlo = wl(lo - vyR)
            xRhi = x1 - whi; xRlo = x1 - wlo
            if whi > 0.5: right_lines.append((x1 - whi, hi, x1, vyR))
            if wlo > 0.5: right_lines.append((x1 - wlo, lo, x1, vyR))
        else:
            xRhi = xRlo = x1

        if self.fill:
            poly = []
            if sameL or prevDATA:
                poly += [x0, hi]; bl = [x0, lo]
            else:
                poly += [x0, vyL, xLhi, hi]; bl = [xLlo, lo]
            if trailing:
                poly += [xRhi, hi, x1, vyR, xRlo, lo]
            else:
                poly += [x1, hi, x1, lo]
            poly += bl
            cv.create_polygon(poly, fill=self.fill, outline="")
            hxL = min(xLhi, xLlo); hxR = max(xRhi, xRlo); xt = hxL - swing
            while xt < hxR:
                xs = max(xt, hxL); xe = min(xt + swing, hxR)
                if xs < xe:
                    cv.create_line(xs, hi + (xs - xt), xe, hi + (xe - xt),
                                   fill=Style.UNK_HATCH, width=1)
                xt += 7

        cv.create_line(xLhi, hi, xRhi, hi, fill=col, width=W)
        cv.create_line(xLlo, lo, xRlo, lo, fill=col, width=W)
        for ln in left_lines + right_lines:
            cv.create_line(*ln, fill=col, width=W)
        if self.accepts_text and cell.get("text") and not sameL:
            cv.create_text((x0 + x1) / 2, mid, text=cell["text"],
                           font=Style.BUS_FONT, fill=self.text_color)


class UnknownElement(BusElement):
    name = "Unknown"; accepts_text = False
    fill = Style.UNK_FILL; hatch = True; text_color = "#3A0000"


# ============================================================================
# 繪圖引擎
# ============================================================================
class Engine:
    def __init__(self):
        self.elements = {e.name: e for e in (
            HighElement(), LowElement(), HiZElement(),
            ClkElement(), BusElement(), UnknownElement())}
        self._wcol = Style.WAVE

    def elem(self, t):
        return self.elements.get(t)

    def meet(self, Lt, Rt, hi, mid, lo):
        eL = self.elements[Lt].exit_y(hi, mid, lo) if Lt in self.elements else None
        eR = self.elements[Rt].entry_y(hi, mid, lo) if Rt in self.elements else None
        if eL is not None and eR is not None:
            return eL if eL == eR else None
        if eL is not None: return eL
        if eR is not None: return eR
        return mid

    @staticmethod
    def same_data(a, b):
        return bool(a and b and a["type"] == b["type"]
                    and a["type"] in ("BUS", "Unknown")
                    and a.get("text", "") == b.get("text", ""))

    def draw(self, name_cv, wave_cv, model, sig_sel, geom, cell_sel=None):
        name_cv.delete("all"); wave_cv.delete("all")
        n = len(model.signals); npd = model.n_periods
        HH, RH, PW, NW = geom.header_h, geom.row_h, geom.period_w, geom.name_w
        rows = model.layout()
        total_h = HH + len(rows) * RH; grid_w = npd * PW
        max_off = max((s.get("offset", 0.0) for s in model.signals), default=0.0)
        wave_cv.configure(scrollregion=(0, 0, max(grid_w + max_off * PW, 10), max(total_h, 10)))
        name_cv.configure(scrollregion=(0, 0, NW, max(total_h, 10)))

        name_cv.create_rectangle(0, 0, NW, HH, fill=Style.FACE, outline=Style.FACE_DARK)
        name_cv.create_text(NW // 2, HH // 2, text="SIGNAL", font=Style.UI_FONT, fill=Style.TEXT)
        for p in range(npd):
            x = p * PW
            wave_cv.create_text(x + PW / 2, HH / 2, text=f"T{p}", font=Style.LABEL_FONT, fill=Style.TEXT)
            wave_cv.create_line(x, HH, x, total_h, fill=Style.DASH, dash=(2, 3))
        wave_cv.create_line(grid_w, HH, grid_w, total_h, fill=Style.DASH, dash=(2, 3))
        wave_cv.create_line(0, HH, grid_w, HH, fill=Style.GRID)

        sig_row = {}                       # signal index -> 可見列 (給 cell_sel 高亮)
        for r, row in enumerate(rows):
            kind, ref, depth, rgcol = row.kind, row.ref, row.depth, row.gcol
            row_top = HH + r * RH; row_bot = row_top + RH
            if kind == "group":            # ---- 群組標頭列 (依深度縮排) ----
                meta = model.groups.get(ref, {})
                gcol = rgcol
                tri = "▸" if meta.get("collapsed") else "▾"
                gx = 8 + depth * 16
                name_cv.create_rectangle(0, row_top, NW, row_bot, fill=Style.FACE, outline=Style.FACE_DARK)
                name_cv.create_text(gx, (row_top + row_bot) // 2,
                                    text=f"{tri} {meta.get('name', ref)}",
                                    anchor="w", font=Style.NAME_FONT, fill=(gcol or Style.TEXT))
                wave_cv.create_rectangle(0, row_top, grid_w, row_bot, fill=Style.FACE, outline="")
                if gcol:
                    wave_cv.create_rectangle(0, row_top, grid_w, row_top + 3, fill=gcol, outline="")
                wave_cv.create_line(0, row_bot, grid_w, row_bot, fill=Style.GRID)
                continue
            si = ref; sig = model.signals[si]; sig_row[si] = r    # ---- 訊號列 ----
            hi, mid, lo = geom.levels(row_top)
            ox = sig.get("offset", 0.0) * PW
            gcol = rgcol                       # 繼承自最近祖先群組 (layout 已算好)
            self._wcol = sig.get("color") or gcol or Style.WAVE   # 自訂色 > 群組色 > 預設
            namecol = sig.get("color") or gcol or Style.TEXT
            indent = 8 + depth * 16            # 依巢狀深度縮排
            if si in sig_sel:
                name_cv.create_rectangle(0, row_top, NW, row_bot, fill=Style.SEL, outline="")
            name_cv.create_rectangle(0, row_top, NW, row_bot,
                                     fill="" if si in sig_sel else Style.CANVAS_BG, outline=Style.GRID)
            label = sig["name"] + (f"  Δ{sig['offset']:.2f}" if sig.get("offset") else "")
            name_cv.create_text(indent, (row_top + row_bot) // 2, text=label,
                                anchor="w", font=Style.NAME_FONT, fill=namecol)
            wave_cv.create_line(0, row_bot, grid_w, row_bot, fill=Style.GRID)
            cells = sig["cells"]
            for p in range(npd):
                pc = cells[p - 1] if p > 0 else None
                nc = cells[p + 1] if p < npd - 1 else None
                el = self.elem(cells[p]["type"])
                if el:
                    el.draw(self, wave_cv, geom, cells[p], pc, nc, p * PW + ox, hi, mid, lo)
            if ox > 0:                          # 位移虛擬延伸 (純視覺，不入資料)
                f = self.elem(cells[0]["type"])
                if f is not None:
                    if f.kind == "DATA":        # BUS/Unknown：左緣收口三角 (斜率=BUS 的 swing/tw)
                        tw = geom.tw(); swing = lo - hi
                        half_w = abs(mid - hi) * tw / swing   # 半擺幅水平寬 = tw/2
                        base_x = ox - half_w    # 收口起點 (沿 BUS 斜率回推半擺幅)
                        if base_x > 0:          # 三角前若有空間則補平行帶
                            wave_cv.create_line(0, hi, base_x, hi, fill=self._wcol, width=2)
                            wave_cv.create_line(0, lo, base_x, lo, fill=self._wcol, width=2)
                            xh = xl = base_x; yh, yl = hi, lo
                        else:                   # 回推超出左界 -> 在 x=0 沿斜率裁切
                            t = (-base_x) / half_w  # 已在畫面外行進的比例
                            xh = xl = 0.0
                            yh = hi + (mid - hi) * t
                            yl = lo + (mid - lo) * t
                        wave_cv.create_line(xh, yh, ox, mid, fill=self._wcol, width=2)
                        wave_cv.create_line(xl, yl, ox, mid, fill=self._wcol, width=2)
                    elif f.kind == "CLK":       # 時脈：補靜止低準位
                        wave_cv.create_line(0, lo, ox, lo, fill=self._wcol, width=2)
                    else:                       # 單準位：補該準位
                        y = f.entry_y(hi, mid, lo)
                        if y is not None:
                            wave_cv.create_line(0, y, ox, y, fill=self._wcol, width=2)
                wave_cv.create_rectangle(grid_w + 1, row_top, grid_w + ox + 2, row_bot,
                                         fill=Style.CANVAS_BG, outline="")   # 右端裁齊

        if cell_sel:
            s0, s1, p0, p1 = cell_sel
            for s in range(s0, s1 + 1):
                if s in sig_row:           # 折疊隱藏的列跳過
                    ox = model.signals[s].get("offset", 0.0) * PW
                    y0 = HH + sig_row[s] * RH; y1 = y0 + RH
                    wave_cv.create_rectangle(p0 * PW + ox, y0, (p1 + 1) * PW + ox, y1,
                                             fill=Style.MARQUEE_FILL, stipple="gray12",
                                             outline=Style.MARQUEE, dash=(3, 2), width=1)

        # ---- 標注層：關係線 (在下) + 錨點 (在上) ----
        sid2idx = {s.get("sid"): i for i, s in enumerate(model.signals)}
        npos = self.node_positions(model, geom, sig_row, sid2idx)
        for ed in model.edges:
            a, b = npos.get(ed["frm"]), npos.get(ed["to"])
            if a and b:
                self.draw_edge(wave_cv, a, b, ed.get("label", ""), style=ed.get("style", "double"))
        for nid, xy in npos.items():
            self.draw_node(wave_cv, nid, xy)

    # ---- 標注繪製 (Engine 與 PILCanvas 共用，匯出一致) ----
    @staticmethod
    def node_positions(model, geom, sig_row, sid2idx):
        HH, RH, PW = geom.header_h, geom.row_h, geom.period_w
        ex = {"start": 0.0, "mid": 0.5, "end": 1.0}
        pos = {}
        for nid, nd in model.nodes.items():
            si = sid2idx.get(nd.get("sid"))
            if si is None or si not in sig_row:
                continue
            ox = model.signals[si].get("offset", 0.0) * PW
            x = (nd["period"] + ex.get(nd.get("edge", "start"), 0.0)) * PW + ox
            y = HH + sig_row[si] * RH + RH / 2
            pos[nid] = (x, y)
        return pos

    ANNOT = "#6A3FB5"

    @staticmethod
    def _scale_of(cv):
        s = getattr(cv, "export_scale", 1)      # 注意：tkinter Canvas 本身有 scale() 方法，故改名避免撞名
        return s if isinstance(s, (int, float)) else 1

    def draw_node(self, cv, nid, xy, hot=False):
        sc = self._scale_of(cv)
        x, y = xy; r = 4 * sc
        cv.create_oval(x - r, y - r, x + r, y + r,
                       fill=(Style.MARQUEE if hot else "#FFFFFF"), outline=self.ANNOT, width=2)
        cv.create_text(x, y - 10 * sc, text=nid, font=Style.LABEL_FONT, fill=self.ANNOT)

    def draw_edge(self, cv, a, b, label="", hot=False, style="double"):
        col = Style.MARQUEE if hot else self.ANNOT
        cv.create_line(a[0], a[1], b[0], b[1], fill=col, width=2)
        if style == "single":                   # 單箭頭：因果 frm -> to
            self._arrow(cv, b, a, col)
        elif style == "measure":                # 無箭頭：量測線 (兩端短橫標)
            self._tick(cv, a, b, col); self._tick(cv, b, a, col)
        else:                                   # double：雙箭頭 (預設)
            self._arrow(cv, b, a, col); self._arrow(cv, a, b, col)
        if label:
            cv.create_text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 8 * self._scale_of(cv),
                           text=label, font=Style.BUS_FONT, fill=col)

    @staticmethod
    def _arrow(cv, tip, frm, col):
        dx, dy = tip[0] - frm[0], tip[1] - frm[1]
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        sc = Engine._scale_of(cv)
        sz, hw = 11 * sc, 5 * sc                # 箭頭長度 / 半寬 (隨匯出倍率放大)
        bx, by = tip[0] - ux * sz, tip[1] - uy * sz
        px, py = -uy, ux
        cv.create_polygon([tip[0], tip[1],
                           bx + px * hw, by + py * hw,
                           bx - px * hw, by - py * hw], fill=col, outline=col)

    @staticmethod
    def _tick(cv, end, other, col):             # 量測線端點的垂直短橫
        dx, dy = other[0] - end[0], other[1] - end[1]
        L = math.hypot(dx, dy) or 1.0
        px, py = -dy / L, dx / L; t = 6 * Engine._scale_of(cv)
        cv.create_line(end[0] + px * t, end[1] + py * t,
                       end[0] - px * t, end[1] - py * t, fill=col, width=2)


# ============================================================================
# PNG 匯出：Pillow 轉接層 (重用 Engine 的繪圖邏輯，不需 Ghostscript)
# ----------------------------------------------------------------------------
#   PILCanvas 把 tkinter Canvas 的 create_* 介面對應到 Pillow ImageDraw，
#   因此 Engine.draw 與各元件 draw() 可原封不動畫到影像上。
# ============================================================================
def _load_pil_fonts(scale=1):
    from PIL import ImageFont
    reg_cands = ["msjh.ttc", "msyh.ttc", "mingliu.ttc", "NotoSansCJKtc-Regular.otf",
                 "PingFang.ttc", "tahoma.ttf", "arial.ttf", "DejaVuSans.ttf"]
    bold_cands = ["msjhbd.ttc", "msyhbd.ttc", "tahomabd.ttf", "arialbd.ttf",
                  "DejaVuSans-Bold.ttf"] + reg_cands
    size = max(8, int(round(12 * scale)))

    def pick(cands, sz):
        for c in cands:
            try:
                return ImageFont.truetype(c, sz)
            except Exception:
                pass
        return ImageFont.load_default()
    return {"reg": pick(reg_cands, size), "bold": pick(bold_cands, size)}


class PILCanvas:
    """最小化的 tkinter Canvas 介面，實際畫到 Pillow ImageDraw。
    scale 用於高解析匯出：線寬與標注尺寸隨之放大 (座標已由縮放後的 Geometry 提供)。"""
    def __init__(self, draw, fonts, scale=1):
        self.d = draw
        self.fonts = fonts
        self.export_scale = scale

    @staticmethod
    def _c(v):
        return None if v in (None, "") else v

    def _w(self, width):
        return max(1, int(round(width * self.export_scale)))

    def _font(self, f):
        bold = isinstance(f, (tuple, list)) and "bold" in f
        return self.fonts["bold"] if bold else self.fonts["reg"]

    def create_line(self, *coords, fill=None, width=1, dash=None, **kw):
        f = self._c(fill)
        if f:
            self.d.line(list(coords), fill=f, width=self._w(width))

    def create_rectangle(self, x0, y0, x1, y1, fill=None, outline=None,
                         width=1, dash=None, stipple=None, **kw):
        f = self._c(fill); o = self._c(outline)
        if f or o:
            self.d.rectangle([x0, y0, x1, y1], fill=f, outline=o, width=self._w(width) if o else 1)

    def create_polygon(self, pts, fill=None, outline=None, **kw):
        self.d.polygon(list(pts), fill=self._c(fill), outline=self._c(outline))

    def create_oval(self, x0, y0, x1, y1, fill=None, outline=None, width=1, **kw):
        self.d.ellipse([x0, y0, x1, y1], fill=self._c(fill),
                       outline=self._c(outline), width=self._w(width) if self._c(outline) else 1)

    def create_text(self, x, y, text="", font=None, fill=None, anchor="center", **kw):
        f = self._c(fill) or "#000000"
        anc = {"center": "mm", "w": "lm", "e": "rm"}.get(anchor, "mm")
        try:
            self.d.text((x, y), str(text), fill=f, font=self._font(font), anchor=anc)
        except TypeError:                       # 舊版 Pillow 無 anchor 參數
            self.d.text((x, y), str(text), fill=f, font=self._font(font))

    def configure(self, **kw):
        pass

    def delete(self, *a):
        pass


class SVGCanvas:
    """把 tkinter Canvas 介面對應到 SVG 元素 (向量、無限解析度)。
    多個實例可共用同一個 elements 串列，並用 xoff 水平位移 (名稱欄 / 波形區合成單檔)。"""
    CJK = "'Microsoft JhengHei','PingFang TC','Noto Sans CJK TC','Heiti TC',sans-serif"

    def __init__(self, elements, xoff=0):
        self.e = elements
        self.xoff = xoff

    def _x(self, x):
        return x + self.xoff

    @staticmethod
    def _c(v):
        return None if v in (None, "") else v

    @staticmethod
    def _esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    def _pts(self, coords):
        return " ".join(f"{self._x(coords[i]):.1f},{coords[i+1]:.1f}"
                        for i in range(0, len(coords) - 1, 2))

    def create_line(self, *coords, fill=None, width=1, dash=None, **kw):
        f = self._c(fill)
        if not f:
            return
        da = f' stroke-dasharray="{dash[0]},{dash[1]}"' if dash else ""
        self.e.append(f'<polyline points="{self._pts(coords)}" fill="none" '
                      f'stroke="{f}" stroke-width="{width}"{da}/>')

    def create_rectangle(self, x0, y0, x1, y1, fill=None, outline=None,
                         width=1, dash=None, stipple=None, **kw):
        f = self._c(fill); o = self._c(outline)
        if not (f or o):
            return
        X0, X1 = self._x(min(x0, x1)), self._x(max(x0, x1))
        Y0, Y1 = min(y0, y1), max(y0, y1)
        a = f'fill="{f}"' if f else 'fill="none"'
        if o:
            a += f' stroke="{o}" stroke-width="{width}"'
        self.e.append(f'<rect x="{X0:.1f}" y="{Y0:.1f}" width="{X1-X0:.1f}" '
                      f'height="{Y1-Y0:.1f}" {a}/>')

    def create_polygon(self, pts, fill=None, outline=None, **kw):
        f = self._c(fill); o = self._c(outline)
        a = f'fill="{f}"' if f else 'fill="none"'
        if o:
            a += f' stroke="{o}"'
        self.e.append(f'<polygon points="{self._pts(list(pts))}" {a}/>')

    def create_oval(self, x0, y0, x1, y1, fill=None, outline=None, width=1, **kw):
        cx = (self._x(x0) + self._x(x1)) / 2; cy = (y0 + y1) / 2
        rx = abs(x1 - x0) / 2; ry = abs(y1 - y0) / 2
        f = self._c(fill); o = self._c(outline)
        a = f'fill="{f}"' if f else 'fill="none"'
        if o:
            a += f' stroke="{o}" stroke-width="{width}"'
        self.e.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" {a}/>')

    def create_text(self, x, y, text="", font=None, fill=None, anchor="center", **kw):
        f = self._c(fill) or "#000000"
        size, bold = 12, False
        if isinstance(font, (tuple, list)):
            for v in font:
                if isinstance(v, int):
                    size = int(round(abs(v) * 1.33))
                elif v == "bold":
                    bold = True
        ta = {"center": "middle", "w": "start", "e": "end"}.get(anchor, "middle")
        wt = ' font-weight="bold"' if bold else ""
        self.e.append(f'<text x="{self._x(x):.1f}" y="{y:.1f}" font-size="{size}" '
                      f'font-family="{self.CJK}" text-anchor="{ta}" '
                      f'dominant-baseline="middle" fill="{f}"{wt}>{self._esc(text)}</text>')

    def configure(self, **kw):
        pass

    def delete(self, *a):
        pass


# ============================================================================
# 範本庫 (獨立於專案檔；索引存使用者目錄，記錄各範本 JSON 的路徑)
# ============================================================================
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


# ============================================================================
# 介面層
# ============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RetroWave - 數位波型繪製工具  v1.18")
        self.geometry("1160x660"); self.minsize(900, 470)
        self.configure(bg=Style.FACE)
        self.model = Model(); self.geom = Geometry(); self.engine = Engine()
        self.active_tool = "H"; self.tool_btns = {}
        self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
        self.cell_sel = None; self.clip = None; self.clip_signals = None
        self.clip_group = None
        self._clip_kind = None; self._copy_ctx = "cells"
        self._press = None; self._press_xy = (0, 0); self._moved = False
        self._marquee = None; self._selecting = False; self._panning = False
        self._drag_value = None; self._hover = None
        self._hover_node = None; self._hover_edge = None
        self._connecting = False; self._connect_from = None; self._connect_xy = None
        self._name_press = None; self._name_moved = False; self._dragging = False
        self._drag_kind = None; self._drag_ref = None; self._drop = None; self._drop_target = None
        self.lib = TemplateLibrary()
        self._build_menubar(); self._build_toolbar(); self._build_main()
        self._build_statusbar(); self._bind_keys()
        self._set_tool("H"); self.render()
        self.after(150, self._startup_templates)    # 視窗顯示後再載入範本/提示缺檔

    def _build_menubar(self):
        bar = tk.Frame(self, bg=Style.FACE, bd=1, relief=tk.RAISED); bar.pack(side=tk.TOP, fill=tk.X)
        fmb = tk.Menubutton(bar, text="File", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        fm = tk.Menu(fmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        fm.add_command(label="新增 (New)\tCtrl+N", command=self.do_new)
        fm.add_command(label="開啟… (Load)\tCtrl+O", command=self.do_open)
        fm.add_command(label="儲存… (Save)\tCtrl+S", command=self.do_save)
        fm.add_separator()
        fm.add_command(label="匯入範本… (Import Template)", command=self._import_template)
        fm.add_separator()
        fm.add_command(label="匯出圖片… (Export)\tCtrl+E", command=self.do_export)
        fm.add_command(label="匯出 WaveDrom JSON…", command=self.do_export_wavedrom)
        fm.add_separator()
        fm.add_command(label="離開 (Exit)", command=self.destroy)
        fmb.configure(menu=fm); fmb.pack(side=tk.LEFT)

        tmb = tk.Menubutton(bar, text="Template", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        self.tmpl_menu = tk.Menu(tmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        tmb.configure(menu=self.tmpl_menu); tmb.pack(side=tk.LEFT)
        self._rebuild_template_menu()
        hmb = tk.Menubutton(bar, text="Help", font=Style.UI_FONT, bg=Style.FACE, padx=10, pady=2)
        hm = tk.Menu(hmb, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        hm.add_command(label="使用說明", command=self.help_usage)
        hm.add_command(label="快捷鍵", command=self.help_keys)
        hm.add_separator()
        hm.add_command(label="關於 RetroWave", command=self.help_about)
        hmb.configure(menu=hm); hmb.pack(side=tk.LEFT)

    # ---- 範本庫 ----
    def _rebuild_template_menu(self):
        m = self.tmpl_menu
        m.delete(0, "end")
        if self.lib.entries:
            for e in self.lib.entries:
                m.add_command(label=e["name"], command=lambda en=e: self._insert_template(en))
            m.add_separator()
            rem = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            for e in self.lib.entries:
                rem.add_command(label=e["name"], command=lambda en=e: self._remove_template(en["name"]))
            self._tmpl_rem = rem               # 保留參考避免被回收
            m.add_cascade(label="移除範本", menu=rem)
        else:
            m.add_command(label="(尚無範本)", state="disabled")
        m.add_separator()
        m.add_command(label="匯入範本… (Import)", command=self._import_template)
        m.add_command(label="將目前畫布存成範本…", command=self._save_as_template)

    def _startup_templates(self):
        avail, missing = self.lib.load()
        self._rebuild_template_menu()
        if missing:
            lines = "\n".join(f"・{m['name']}    ({m.get('path') or '路徑未知'})" for m in missing)
            messagebox.showwarning(
                "範本載入", f"以下範本檔案找不到，已從清單移除：\n\n{lines}")

    def _import_template(self):
        path = filedialog.askopenfilename(
            title="匯入範本 (JSON)", filetypes=[("波型 JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            d = TemplateLibrary.read(path)
            if not isinstance(d, dict) or "signals" not in d:
                raise ValueError("不是有效的波型 JSON（缺 signals 欄位）")
        except Exception as ex:
            messagebox.showerror("匯入範本失敗", str(ex)); return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("匯入範本", "範本名稱:", initialvalue=default, parent=self)
        if not name:
            return
        self.lib.add(name, path); self._rebuild_template_menu()
        messagebox.showinfo("匯入範本",
                            f"已加入範本「{name}」。\n（此範本會在每次開啟工具時自動載入，"
                            f"從 Template 選單點選即可插入為群組。）")

    def _save_as_template(self):
        path = filedialog.asksaveasfilename(
            title="將目前畫布存成範本", defaultextension=".json",
            initialdir=TemplateLibrary.DIR, filetypes=[("波型 JSON", "*.json")])
        if not path:
            return
        data = self.model.to_dict(); data["view"] = self.geom.to_dict()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            messagebox.showerror("存成範本失敗", str(ex)); return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("存成範本", "範本名稱:", initialvalue=default, parent=self)
        if not name:
            return
        self.lib.add(name, path); self._rebuild_template_menu()
        messagebox.showinfo("範本", f"已存成範本「{name}」。")

    def _remove_template(self, name):
        self.lib.remove(name); self._rebuild_template_menu()
        self.status.configure(text=f" 已從範本庫移除「{name}」（原檔案不受影響）")

    def _insert_template(self, entry):
        try:
            tsignals = TemplateLibrary.read(entry["path"]).get("signals", [])
        except Exception as ex:
            messagebox.showerror("插入範本失敗",
                                 f"讀取失敗，檔案可能已移動或刪除。\n{entry.get('path')}\n\n{ex}")
            return
        if not tsignals:
            messagebox.showwarning("插入範本", "此範本沒有任何訊號。"); return
        npd = self.model.n_periods
        gid = self.model.new_gid()
        gname = self._unique_name(entry["name"], {me.get("name") for me in self.model.groups.values()})
        names = {s["name"] for s in self.model.signals}
        children = []
        for ts in tsignals:
            ns = {"name": ts.get("name", "SIG"), "offset": float(ts.get("offset", 0.0)),
                  "color": ts.get("color"), "group": gid, "sid": self.model._new_sid(),
                  "cells": [{"type": c.get("type", "L"), "text": c.get("text", "")}
                            for c in ts.get("cells", [])]}
            ns["name"] = self._unique_name(ns["name"], names); names.add(ns["name"])
            while len(ns["cells"]) < npd:
                ns["cells"].append(self.model.new_cell("L"))
            del ns["cells"][npd:]
            self.model.signals.append(ns)
            children.append({"type": "sig", "sid": ns["sid"]})
        self.model.group_tree.append({"type": "group", "gid": gid, "name": gname,
                                      "collapsed": False, "color": None, "children": children})
        self.model._after_tree_change()
        sids = {c["sid"] for c in children}
        newidx = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
        self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
        self.render()
        self.status.configure(text=f" 已插入範本「{gname}」（{len(children)} 條，已成群組）")

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=Style.FACE, bd=1, relief=tk.RAISED); tb.pack(side=tk.TOP, fill=tk.X)
        cfg = tk.Frame(tb, bg=Style.FACE); cfg.pack(side=tk.RIGHT, padx=6, pady=4)
        self.sp_w = self._spin(cfg, "寬度", 30, 240, 4, self.geom.period_w, self._apply_geom)
        self.sp_h = self._spin(cfg, "列高", 36, 160, 4, self.geom.row_h, self._apply_geom)
        self.sp_r = self._spin(cfg, "斜率%", 5, 45, 1, int(self.geom.ramp_ratio * 100), self._apply_geom)
        self.sp_p = self._spin(cfg, "週期", 1, 256, 1, self.model.n_periods, self._apply_periods)

        tk.Label(tb, text="元件:", bg=Style.FACE, font=Style.UI_FONT).pack(side=tk.LEFT, padx=(6, 2), pady=6)
        for t in WAVE_TYPES:
            b = make_key_button(tb, t, lambda x=t: self._set_tool(x))
            b.pack(side=tk.LEFT, padx=2, pady=6); self.tool_btns[t] = b
        tk.Frame(tb, width=2, bg=Style.FACE_DARK).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=8)
        make_key_button(tb, "＋訊號", self.add_signal).pack(side=tk.LEFT, padx=2, pady=6)
        tk.Label(tb, text="(訊號右鍵：調色/位移/群組/改名/刪除；點群組標頭折疊)", bg=Style.FACE,
                 font=Style.UI_FONT, fg="#777").pack(side=tk.LEFT, padx=(8, 2), pady=6)

    def _spin(self, parent, label, lo, hi, step, val, cmd):
        tk.Label(parent, text=label, bg=Style.FACE, font=Style.UI_FONT).pack(side=tk.LEFT, padx=(6, 1))
        sp = tk.Spinbox(parent, from_=lo, to=hi, increment=step, width=5, font=Style.UI_FONT,
                        command=cmd, relief=tk.SUNKEN, bd=2)
        sp.delete(0, tk.END); sp.insert(0, str(val))
        sp.bind("<Return>", lambda e: (cmd(), self.wave_cv.focus_set()))
        sp.bind("<FocusOut>", lambda e: cmd())
        sp.bind("<Escape>", lambda e: self.wave_cv.focus_set())
        sp.pack(side=tk.LEFT)
        return sp

    def _apply_geom(self):
        try:
            self.geom.period_w = max(20, int(float(self.sp_w.get())))
            self.geom.row_h = max(30, int(float(self.sp_h.get())))
            self.geom.ramp_ratio = max(0.02, min(0.45, float(self.sp_r.get()) / 100.0))
        except ValueError:
            return
        self.render()

    def _apply_periods(self):
        try:
            n = max(1, int(float(self.sp_p.get())))
        except ValueError:
            return
        self.model.set_n_periods(n); self.cell_sel = None; self.render()

    def set_offset_dialog(self):
        if not self.model.signals:
            return
        cur = self.model.signals[self.selected].get("offset", 0.0)
        v = simpledialog.askfloat("設定位移", "位移 (0 ~ 0.95 週期):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        for s in (self.sig_sel or {self.selected}):
            if 0 <= s < len(self.model.signals):
                self.model.signals[s]["offset"] = round(v, 2)
        self.render()

    def _refresh_offset_field(self):
        pass            # 位移已移至右鍵選單，無常駐欄位

    def _build_main(self):
        main = tk.Frame(self, bg=Style.FACE_DARK, bd=2, relief=tk.SUNKEN)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=3, pady=3)
        main.columnconfigure(1, weight=1); main.rowconfigure(0, weight=1)
        self.name_cv = tk.Canvas(main, width=self.geom.name_w, bg=Style.CANVAS_BG, highlightthickness=0)
        self.name_cv.grid(row=0, column=0, sticky="ns")
        self.wave_cv = tk.Canvas(main, bg=Style.CANVAS_BG, highlightthickness=0, takefocus=1)
        self.wave_cv.grid(row=0, column=1, sticky="nsew")
        vbar = tk.Scrollbar(main, orient=tk.VERTICAL, command=self._yview); vbar.grid(row=0, column=2, sticky="ns")
        hbar = tk.Scrollbar(main, orient=tk.HORIZONTAL, command=self.wave_cv.xview); hbar.grid(row=1, column=1, sticky="ew")
        self.wave_cv.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.wave_cv.bind("<Button-1>", self.on_press)
        self.wave_cv.bind("<B1-Motion>", self.on_motion)
        self.wave_cv.bind("<ButtonRelease-1>", self.on_release)
        self.wave_cv.bind("<Button-3>", self.on_wave_menu)
        self.wave_cv.bind("<Motion>", self.on_hover)
        self.name_cv.bind("<Button-1>", self.on_name_press)
        self.name_cv.bind("<B1-Motion>", self.on_name_drag)
        self.name_cv.bind("<ButtonRelease-1>", self.on_name_release)
        self.name_cv.bind("<Double-Button-1>", self.on_name_rename)
        self.name_cv.bind("<Button-3>", self.on_name_menu)
        for cv in (self.wave_cv, self.name_cv):
            cv.bind("<MouseWheel>", self._on_wheel)
            cv.bind("<Button-4>", self._on_wheel); cv.bind("<Button-5>", self._on_wheel)

    def _build_statusbar(self):
        self.status = tk.Label(self, text="", bg=Style.FACE, anchor="w",
                               font=Style.UI_FONT, bd=1, relief=tk.SUNKEN)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _is_typing(self):
        return isinstance(self.focus_get(), (tk.Entry, tk.Spinbox))

    def _bind_keys(self):
        self.bind("<Control-n>", lambda e: self.do_new())
        self.bind("<Control-o>", lambda e: self.do_open())
        self.bind("<Control-s>", lambda e: self.do_save())
        self.bind("<Control-e>", lambda e: self.do_export())
        self.bind("<Control-c>", lambda e: self.do_copy())
        self.bind("<Control-v>", lambda e: self.do_paste())
        self.bind("<Escape>", lambda e: self._enter_pan_mode())
        self.bind("<Delete>", lambda e: self._del_hovered_annot())

        def keyed(fn):
            def handler(e):
                if self._is_typing():
                    return
                fn()
            return handler
        for i, t in enumerate(WAVE_TYPES, start=1):
            self.bind(str(i), keyed(lambda x=t: self._set_tool(x)))

    def _yview(self, *a):
        self.wave_cv.yview(*a); self.name_cv.yview(*a)

    def _on_wheel(self, e):
        d = -1 if (getattr(e, "delta", 0) > 0 or e.num == 4) else 1
        self.wave_cv.yview_scroll(d, "units"); self.name_cv.yview_scroll(d, "units")

    # ---- 工具 ----
    def _set_tool(self, t):
        if self.cell_sel is not None:          # 有框選 -> 填入該範圍
            self._fill_selection(t); return
        self.active_tool = t; self._refresh_tools()
        self.wave_cv.configure(cursor="")
        self.render()

    def _enter_pan_mode(self):
        """Esc：任何狀態皆退回畫布拖曳模式（清除框選、取消元件選擇）。"""
        self.cell_sel = None
        self.active_tool = None; self._refresh_tools()
        self.wave_cv.configure(cursor="fleur")
        self.render()

    def _refresh_tools(self):
        for k, b in self.tool_btns.items():
            on = (k == self.active_tool)
            b.configure(relief=tk.SUNKEN if on else tk.RAISED, bg="#DAD7C2" if on else Style.FACE)

    def _clear_cell_sel(self):
        if self.cell_sel is not None:
            self.cell_sel = None; self.render()

    def _fill_rect(self, sel, t):
        s0, s1, p0, p1 = sel
        if t == "BUS":
            txt = simpledialog.askstring("填入 BUS", "此範圍的資料值:", parent=self)
            if txt is None:
                return None
            payload = ("BUS", txt)
        elif t == "Unknown":
            payload = ("Unknown", "")
        else:
            payload = (t, "")
        for s in range(s0, s1 + 1):
            for p in range(p0, p1 + 1):
                self.model.set_cell(s, p, payload[0], payload[1])
        return f"已填入 {payload[0]}" + (f" = '{payload[1]}'" if payload[0] == "BUS" else "")

    def _fill_selection(self, t):
        if self.cell_sel is None:
            return
        msg = self._fill_rect(self.cell_sel, t)
        if msg:
            self.render(); self.status.configure(text=" " + msg + "（選取保留，Esc 清除）")

    def _update_status(self):
        if self.active_tool is None:
            self.status.configure(
                text=f" 拖曳模式 | 左鍵拖曳=平移畫布 | Shift/Ctrl+左鍵拖曳=框選 "
                     f"| 點元件鈕或數字鍵回繪製 | 週期{self.model.n_periods}")
            return
        if self.active_tool == "BUS":
            hint = "點/拖曳=畫BUS(原為BUS保留, 非BUS取代);再點同格=改值"
        else:
            hint = "點/拖曳上色(鎖列)"
        self.status.configure(
            text=f" 筆刷:{self.active_tool} | {hint} | Shift/Ctrl拖曳=框選(按元件鍵填入/Ctrl+C複製) "
                 f"| 名稱Ctrl/Shift多選 -> 右鍵: 調色/位移/刪除 | Esc=拖曳模式 | 週期{self.model.n_periods}")

    def render(self):
        self.name_cv.configure(width=self.geom.name_w)
        self.engine.draw(self.name_cv, self.wave_cv, self.model, self.sig_sel, self.geom, self.cell_sel)
        self._draw_annot_overlay()
        self._draw_drag_overlay()
        self._update_status()

    # ---- 標注：座標/命中/覆蓋層 ----
    def _node_screen_positions(self):
        rows = self.model.layout()
        sig_row = {row.ref: r for r, row in enumerate(rows) if row.kind == "sig"}
        sid2idx = {s.get("sid"): i for i, s in enumerate(self.model.signals)}
        return self.engine.node_positions(self.model, self.geom, sig_row, sid2idx)

    def _node_at_xy(self, cx, cy, rad=8):
        best, bd = None, rad
        for nid, (x, y) in self._node_screen_positions().items():
            d = math.hypot(cx - x, cy - y)
            if d <= bd:
                bd = d; best = nid
        return best

    @staticmethod
    def _pt_seg_dist(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def _edge_at_xy(self, cx, cy, tol=6):
        pos = self._node_screen_positions()
        for i, ed in enumerate(self.model.edges):
            a, b = pos.get(ed["frm"]), pos.get(ed["to"])
            if a and b and self._pt_seg_dist(cx, cy, a[0], a[1], b[0], b[1]) <= tol:
                return i
        return None

    def _draw_annot_overlay(self):
        pos = self._node_screen_positions()
        if self._connecting:
            PW = self.geom.period_w
            max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
            w = self.model.n_periods * PW + max_off * PW + 4
            h = self.geom.header_h + len(self.model.layout()) * self.geom.row_h
            self.wave_cv.create_rectangle(0, 0, w, h, fill="#C2C2C2", stipple="gray50", outline="")
            for nid, xy in pos.items():
                self.engine.draw_node(self.wave_cv, nid, xy, hot=(nid == self._hover_node))
            if self._connect_from in pos and self._connect_xy:
                x0, y0 = pos[self._connect_from]; x1, y1 = self._connect_xy
                self.wave_cv.create_line(x0, y0, x1, y1, fill=Style.MARQUEE, width=2, dash=(5, 3))
                self.engine.draw_node(self.wave_cv, self._connect_from, pos[self._connect_from], hot=True)
        elif self._hover_node and self._hover_node in pos:
            self.engine.draw_node(self.wave_cv, self._hover_node, pos[self._hover_node], hot=True)
        elif self._hover_edge is not None and 0 <= self._hover_edge < len(self.model.edges):
            ed = self.model.edges[self._hover_edge]
            a, b = pos.get(ed["frm"]), pos.get(ed["to"])
            if a and b:
                self.engine.draw_edge(self.wave_cv, a, b, ed.get("label", ""),
                                      hot=True, style=ed.get("style", "double"))

    # ---- 座標 <-> 格子 (透過 layout 把可見列翻成訊號索引) ----
    def _resolve_row(self, cy):
        if cy < self.geom.header_h:
            return None
        rows = self.model.layout()
        r = int((cy - self.geom.header_h) // self.geom.row_h)
        return rows[r] if 0 <= r < len(rows) else None

    @staticmethod
    def _nearest_sig(rows, r):
        for d in range(len(rows)):
            for rr in (r - d, r + d):
                if 0 <= rr < len(rows) and rows[rr][0] == "sig":
                    return rows[rr][1]
        return None

    def _cell_from_xy(self, cx, cy, clamp=False):
        npd = self.model.n_periods
        rows = self.model.layout()
        if not self.model.signals or npd == 0 or not rows:
            return None
        r = int((cy - self.geom.header_h) // self.geom.row_h)
        if clamp:
            r = max(0, min(len(rows) - 1, r))
        elif cy < self.geom.header_h or not (0 <= r < len(rows)):
            return None
        kind, ref = rows[r].kind, rows[r].ref
        if kind == "sig":
            si = ref
        elif clamp:
            si = self._nearest_sig(rows, r)
            if si is None:
                return None
        else:
            return None
        ox = self.model.signals[si].get("offset", 0.0) * self.geom.period_w
        p = int((cx - ox) // self.geom.period_w)
        if clamp:
            p = max(0, min(npd - 1, p)); return (si, p)
        if 0 <= p < npd:
            return (si, p)
        return None

    def _ev_xy(self, e):
        return self.wave_cv.canvasx(e.x), self.wave_cv.canvasy(e.y)

    # ---- 滑鼠 ----
    def on_hover(self, e):
        cx, cy = self._ev_xy(e)
        self._hover = self._cell_from_xy(cx, cy)
        hv = self._node_at_xy(cx, cy)
        he = self._edge_at_xy(cx, cy) if hv is None else None
        if hv != self._hover_node or he != self._hover_edge:
            self._hover_node = hv; self._hover_edge = he
            self.render()

    def on_press(self, e):
        self.wave_cv.focus_set()
        cx, cy = self._ev_xy(e)
        self._press_xy = (cx, cy)
        ctrl = bool(e.state & CTRL_MASK); shift = bool(e.state & SHIFT_MASK)
        if self.active_tool is None and not (ctrl or shift):   # 拖曳模式：左鍵=平移畫布
            self._panning = True
            self.wave_cv.scan_mark(e.x, e.y)
            self._press = None; self._selecting = False; self._moved = False
            return
        nid = self._node_at_xy(cx, cy) if not (ctrl or shift) else None
        if nid:                                   # 從錨點拉線 (進入冷凍)
            self._connecting = True; self._connect_from = nid
            self._connect_xy = (cx, cy); self._press = None
            self._selecting = False; self._moved = False
            self.render(); return
        self._press = self._cell_from_xy(cx, cy)
        self._moved = False
        self._selecting = ctrl or shift          # Shift/Ctrl 拖曳皆為純框選
        if self._press:
            self.selected = self._press[0]
        self._drag_value = None
        if (not self._selecting) and self._press and self.active_tool == "BUS":
            cells = self.model.signals[self._press[0]]["cells"]; p = self._press[1]
            if cells[p]["type"] == "BUS":
                self._drag_value = cells[p]["text"]
            elif p > 0 and cells[p - 1]["type"] == "BUS":
                self._drag_value = cells[p - 1]["text"]
            else:
                self._drag_value = ""
        self._erase_marquee()
        if self.cell_sel is not None:
            self.cell_sel = None; self.render()

    def on_motion(self, e):
        if self._panning:
            self.wave_cv.scan_dragto(e.x, e.y, gain=1)
            self.name_cv.yview_moveto(self.wave_cv.yview()[0])   # 名稱欄垂直同步
            return
        cx, cy = self._ev_xy(e)
        if self._connecting:
            self._connect_xy = (cx, cy)
            hv = self._node_at_xy(cx, cy)
            self._hover_node = hv if hv != self._connect_from else None
            self.render(); return
        if self._selecting:
            self._moved = True
            self._draw_marquee(self._press_xy, (cx, cy))
        elif self._press:
            self._moved = True
            s = self._press[0]
            ox = self.model.signals[s].get("offset", 0.0) * self.geom.period_w
            p_cur = max(0, min(self.model.n_periods - 1, int((cx - ox) // self.geom.period_w)))
            p0, p1 = sorted((self._press[1], p_cur))
            for p in range(p0, p1 + 1):
                self._paint_cell(s, p, self.active_tool, self._drag_value)
            self.render()

    def on_release(self, e):
        if self._panning:
            self._panning = False
            return
        cx, cy = self._ev_xy(e)
        if self._connecting:
            target = self._node_at_xy(cx, cy)
            frm = self._connect_from
            self._connecting = False; self._connect_from = None; self._connect_xy = None
            self._hover_node = None
            if target and target != frm:
                label = simpledialog.askstring("關係線", "標籤 (可留空，例如 t_su):", parent=self) or ""
                self.model.add_edge(frm, target, label)
                self.status.configure(text=f" 已建立關係線 {frm} → {target}")
            self.render(); return
        if self._selecting:
            a = self._cell_from_xy(*self._press_xy, clamp=True)
            b = self._cell_from_xy(cx, cy, clamp=True)
            if a and b:
                s0, s1 = sorted((a[0], b[0])); p0, p1 = sorted((a[1], b[1]))
                self.cell_sel = (s0, s1, p0, p1)
                self._copy_ctx = "cells"
            self._erase_marquee(); self.render()
            if self.cell_sel:
                self.status.configure(text=" 已框選；按元件鍵填入、或 Ctrl+C 複製")
        else:
            if not self._moved and self._press:
                self._click_cell(*self._press)
            self.render()

    def on_wave_menu(self, e):
        cx, cy = self._ev_xy(e)
        m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        nid = self._node_at_xy(cx, cy)
        if nid:
            m.add_command(label=f"刪除錨點 {nid}", command=lambda: self._del_node(nid))
        else:
            ei = self._edge_at_xy(cx, cy)
            if ei is not None:
                m.add_command(label="編輯標籤…", command=lambda: self._edit_edge(ei))
                sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
                cur = self.model.edges[ei].get("style", "double")
                for sty, lab in (("double", "雙箭頭（量測）"),
                                 ("single", "單箭頭（因果）"),
                                 ("measure", "無箭頭（量測線）")):
                    mark = "● " if sty == cur else "○ "
                    sub.add_command(label=mark + lab, command=lambda s=sty: self._set_edge_style(ei, s))
                m.add_cascade(label="箭頭樣式", menu=sub)
                m.add_command(label="刪除關係線", command=lambda: self._del_edge(ei))
            else:
                c = self._cell_from_xy(cx, cy)
                if not c:
                    return
                m.add_command(label="在此建立錨點", command=lambda: self._add_node_at(cx, cy))
                m.add_separator()
                m.add_command(label="清成 L",
                              command=lambda cc=c: (self.model.set_cell(cc[0], cc[1], "L"), self.render()))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _cell_edge_from_xy(self, cx, cy):
        c = self._cell_from_xy(cx, cy)
        if not c:
            return None
        si, p = c
        ox = self.model.signals[si].get("offset", 0.0) * self.geom.period_w
        frac = ((cx - ox) / self.geom.period_w) - p
        edge = "start" if frac < 0.34 else ("end" if frac > 0.66 else "mid")
        return (si, p, edge)

    def _add_node_at(self, cx, cy):
        ce = self._cell_edge_from_xy(cx, cy)
        if not ce:
            return
        si, p, edge = ce
        nid = self.model.add_node(self.model.signals[si].get("sid"), p, edge)
        self.render(); self.status.configure(text=f" 已建立錨點 {nid}（拖曳錨點可拉關係線；Del 刪除）")

    def _del_node(self, nid):
        self.model.remove_node(nid)
        if self._hover_node == nid:
            self._hover_node = None
        self.render(); self.status.configure(text=f" 已刪除錨點 {nid}")

    def _edit_edge(self, i):
        if 0 <= i < len(self.model.edges):
            cur = self.model.edges[i].get("label", "")
            new = simpledialog.askstring("關係線標籤", "標籤:", initialvalue=cur, parent=self)
            if new is not None:
                self.model.edges[i]["label"] = new; self.render()

    def _del_edge(self, i):
        if 0 <= i < len(self.model.edges):
            del self.model.edges[i]; self._hover_edge = None
            self.render(); self.status.configure(text=" 已刪除關係線")

    def _set_edge_style(self, i, style):
        if 0 <= i < len(self.model.edges):
            self.model.edges[i]["style"] = style
            self.render()
            self.status.configure(text=f" 關係線樣式：{ {'double':'雙箭頭','single':'單箭頭因果','measure':'無箭頭量測'}[style] }")

    def _del_hovered_annot(self):
        if self._is_typing():
            return
        if self._hover_node:
            self._del_node(self._hover_node)
        elif self._hover_edge is not None:
            self._del_edge(self._hover_edge)

    def _paint_cell(self, s, p, t, drag_value=None):
        cells = self.model.signals[s]["cells"]
        if t == "BUS":
            if cells[p]["type"] == "BUS":           # 原為 BUS -> 保留延續，不覆蓋
                return
            if drag_value is not None:
                text = drag_value
            else:
                text = cells[p - 1]["text"] if (p > 0 and cells[p - 1]["type"] == "BUS") else ""
            self.model.set_cell(s, p, "BUS", text)
        elif t == "Unknown":
            self.model.set_cell(s, p, "Unknown", "")
        else:
            self.model.set_cell(s, p, t)

    def _click_cell(self, s, p):
        t = self.active_tool
        if t is None:                                    # 拖曳模式不繪製
            return
        cells = self.model.signals[s]["cells"]
        if t == "BUS" and cells[p]["type"] == "BUS":     # 已是 BUS -> 改值
            cur = cells[p].get("text", "")
            new = simpledialog.askstring("BUS 資料", "輸入資料值:", initialvalue=cur, parent=self)
            if new is not None:
                self.model.set_cell(s, p, "BUS", new)
        else:
            self._paint_cell(s, p, t, self._drag_value)

    # ---- 複製 / 貼上 (波形級 + 訊號級) ----
    @staticmethod
    def _copy_signal(sig):
        return {"name": sig["name"], "offset": sig.get("offset", 0.0),
                "color": sig.get("color"),
                "cells": [{"type": c["type"], "text": c.get("text", "")} for c in sig["cells"]]}

    @staticmethod
    def _unique_name(name, existing):
        if name not in existing:
            return name
        i = 2
        while f"{name}_{i}" in existing:
            i += 1
        return f"{name}_{i}"

    def do_copy(self):
        if self._copy_ctx == "signals" and self.sig_sel:
            idxs = sorted(i for i in self.sig_sel if 0 <= i < len(self.model.signals))
            if not idxs:
                return
            self.clip_signals = [self._copy_signal(self.model.signals[i]) for i in idxs]
            self._clip_kind = "signals"
            self.status.configure(text=f" 已複製 {len(idxs)} 條訊號；Ctrl+V 貼在選取列之後")
        elif self.cell_sel is not None:
            s0, s1, p0, p1 = self.cell_sel
            self.clip = [[{"type": self.model.signals[s]["cells"][p]["type"],
                           "text": self.model.signals[s]["cells"][p].get("text", "")}
                          for p in range(p0, p1 + 1)] for s in range(s0, s1 + 1)]
            self._clip_kind = "cells"
            self.status.configure(text=f" 已複製 {s1-s0+1}x{p1-p0+1} 波形；移到目標格 Ctrl+V 貼上")

    def do_paste(self):
        if self._clip_kind == "group" and self.clip_group:
            self._paste_group(); return
        if self._clip_kind == "signals" and self.clip_signals:
            names = {s["name"] for s in self.model.signals}
            # 插入點：選取訊號所在頂層位置之後
            at_top = len(self.model.group_tree)
            if 0 <= self.selected < len(self.model.signals):
                at_top = self.model._top_index_of_sid(self.model.signals[self.selected]["sid"]) + 1
            new_sids = []
            for k, sig in enumerate(self.clip_signals):
                ns = self._copy_signal(sig)
                ns["name"] = self._unique_name(ns["name"], names); names.add(ns["name"])
                ns["group"] = None                   # 複本預設不分組
                ns["sid"] = self.model._new_sid()    # 複本需有獨立 sid (錨點才不會錯位)
                cells = ns["cells"]
                while len(cells) < self.model.n_periods:
                    cells.append(self.model.new_cell("L"))
                del cells[self.model.n_periods:]
                self.model.signals.append(ns)
                self.model.group_tree.insert(at_top + k, {"type": "sig", "sid": ns["sid"]})
                new_sids.append(ns["sid"])
            self.model._after_tree_change()
            newidx = [i for i, s in enumerate(self.model.signals) if s["sid"] in set(new_sids)]
            self.selected = newidx[0]
            self.sig_sel = set(newidx); self._sig_anchor = newidx[0]
            self._refresh_offset_field(); self.render()
            self.status.configure(text=f" 已貼上 {len(self.clip_signals)} 條訊號（複本未分組）")
        elif self._clip_kind == "cells" and self.clip:
            s0, p0 = self._hover or (self.selected, 0)
            while len(self.model.signals) < s0 + len(self.clip):
                self.model.add_signal()
            for ds, row in enumerate(self.clip):
                for dp, c in enumerate(row):
                    self.model.set_cell(s0 + ds, p0 + dp, c["type"], c.get("text", ""))
            self.render(); self.status.configure(text=f" 已貼上波形於 訊號{s0} T{p0}")

    # ---- 調色 ----
    def pick_color(self):
        if not self.model.signals:
            return
        init = self.model.signals[self.selected].get("color") or Style.WAVE
        try:
            _, hx = colorchooser.askcolor(color=init, parent=self, title="訊號顏色")
        except Exception:
            hx = None
        if hx:
            for s in (self.sig_sel or {self.selected}):
                if 0 <= s < len(self.model.signals):
                    self.model.signals[s]["color"] = hx
            self.render()

    def clear_color(self):
        for s in (self.sig_sel or {self.selected}):
            if 0 <= s < len(self.model.signals):
                self.model.signals[s]["color"] = None
        self.render()

    # ---- marquee ----
    def _draw_marquee(self, xy0, xy1):
        self._erase_marquee()
        x0, y0 = xy0; x1, y1 = xy1
        self._marquee = self.wave_cv.create_rectangle(
            x0, y0, x1, y1, outline=Style.MARQUEE, dash=(3, 2), width=1,
            fill=Style.MARQUEE_FILL, stipple="gray12")

    def _erase_marquee(self):
        if self._marquee:
            self.wave_cv.delete(self._marquee); self._marquee = None

    # ---- 名稱欄 (點選 / 拖曳排序) ----
    def on_name_press(self, e):
        self.name_cv.focus_set()
        cy = self.name_cv.canvasy(e.y)
        self._name_press = (self._resolve_row(cy), e.x, cy)
        self._name_moved = False; self._dragging = False
        self._drag_kind = None; self._drag_ref = None
        self._drop = None; self._drop_target = None

    def on_name_drag(self, e):
        if self._name_press is None:
            return
        item, _px, py = self._name_press
        cy = self.name_cv.canvasy(e.y)
        if not self._dragging:
            if item is None or abs(cy - py) < self.geom.row_h / 2:   # 門檻=列高一半
                return
            self._dragging = True
            self._drag_kind = "group" if item[0] == "group" else "sig"
            self._drag_ref = item[1]
        self._compute_drop(cy)
        self.render()

    def on_name_release(self, e):
        if self._dragging:
            tgt = self._drop_target
            if tgt is not None and tgt.get("valid"):
                if self._drag_kind == "sig":
                    sid = self.model.signals[self._drag_ref]["sid"]
                    self.model.move_leaf_to(sid, tgt["container"], tgt["index"])
                    self.sig_sel = {i for i, s in enumerate(self.model.signals) if s["sid"] == sid}
                    self.selected = next(iter(self.sig_sel), self.selected)
                    self._sig_anchor = self.selected
                    self.status.configure(text=" 已移動訊號" +
                                          ("（併入群組）" if tgt["container"] else "（移到頂層）"))
                else:
                    self.model.move_group_to(self._drag_ref, tgt["container"], tgt["index"])
                    self.status.configure(text=" 已移動群組" +
                                          ("（巢狀為子群組）" if tgt["container"] else "（頂層）"))
            self._dragging = False; self._drop = None; self._drop_target = None
            self._name_press = None
            self._refresh_offset_field(); self.render()
        else:
            self._name_press = None
            self._name_click(e)

    def _name_click(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":              # 點群組標頭 = 折疊/展開
            self._toggle_group(item[1]); return
        s = item[1]
        ctrl = bool(e.state & CTRL_MASK); shift = bool(e.state & SHIFT_MASK)
        if ctrl:
            if s in self.sig_sel:
                self.sig_sel.discard(s)
            else:
                self.sig_sel.add(s)
            self.selected = s; self._sig_anchor = s
        elif shift and self._sig_anchor is not None:
            a, b = sorted((self._sig_anchor, s))
            self.sig_sel = set(range(a, b + 1)); self.selected = s
        else:
            self.sig_sel = {s}; self.selected = s; self._sig_anchor = s
        if not self.sig_sel:
            self.sig_sel = {s}
        self._copy_ctx = "signals"
        self._refresh_offset_field(); self.render()

    # ---- 拖曳落點解析 (容器 + 插入索引)、容器高亮、插入線 ----
    def _group_visible_span(self, rows, gid):
        r0 = next((r for r, row in enumerate(rows)
                   if row.kind == "group" and row.ref == gid), None)
        if r0 is None:
            return None
        base = rows[r0].depth; r1 = r0
        rr = r0 + 1
        while rr < len(rows) and rows[rr].depth > base:
            r1 = rr; rr += 1
        return r0, r1

    def _child_first_visible_row(self, rows, container_gid, index):
        """容器 children 第 index 個子節點的首個可見列 (供插入線定位)；index==len 回末端。"""
        children = self.model._container_children(container_gid) or []
        sid2idx = {s["sid"]: i for i, s in enumerate(self.model.signals)}
        if index < len(children):
            nd = children[index]
            if nd.get("type") == "group":
                return next((r for r, row in enumerate(rows)
                             if row.kind == "group" and row.ref == nd["gid"]), None)
            si = sid2idx.get(nd.get("sid"))
            return next((r for r, row in enumerate(rows)
                         if row.kind == "sig" and row.ref == si), None)
        # index==len：落在容器尾端
        if container_gid is None:
            return len(rows)
        span = self._group_visible_span(rows, container_gid)
        return (span[1] + 1) if span else None

    def _compute_drop(self, cy):
        HH, RH = self.geom.header_h, self.geom.row_h
        rows = self.model.layout()
        if not rows:
            self._drop = None; self._drop_target = None; return
        rf = (cy - HH) / RH
        r = max(0, min(len(rows) - 1, int(rf)))
        lower = (rf - int(rf)) >= 0.5
        row = rows[r]
        container = None; index = 0; hl = None

        if row.kind == "group":
            gid = row.ref
            if not lower:                       # 上半：插在此群組之前 (同層、群組的父容器)
                pg, _lst, idx = self.model._locate(
                    lambda nd: nd.get("type") == "group" and nd.get("gid") == gid)
                container, index, hl = pg, idx, pg
            else:                               # 下半：放進此群組最前
                container, index, hl = gid, 0, gid
        else:                                   # 訊號列：容器=其直接父，索引=同層位置±半列
            sid = self.model.signals[row.ref]["sid"]
            loc = self.model._locate(lambda nd: nd.get("type") == "sig" and nd.get("sid") == sid)
            pg, _lst, idx = loc
            container, index, hl = pg, idx + (1 if lower else 0), pg

        valid = True
        if self._drag_kind == "group":          # 防呆：不可移入自己或子孫
            if container is not None and self.model._is_self_or_descendant(self._drag_ref, container):
                valid = False

        # 插入線 y：對齊容器內 index 的首個可見列
        vr = self._child_first_visible_row(rows, container, index)
        if vr is None:
            vr = r + (1 if lower else 0)
        self._drop_target = {"container": container, "index": index, "valid": valid}
        self._drop = {"y": HH + vr * RH, "valid": valid, "hl": hl}

    def _draw_drag_overlay(self):
        if not self._dragging or not self._drop:
            return
        rows = self.model.layout()
        HH, RH = self.geom.header_h, self.geom.row_h
        H = HH + len(rows) * RH
        NW = self.geom.name_w
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        WW = self.model.n_periods * self.geom.period_w + max_off * self.geom.period_w + 4
        self.name_cv.create_rectangle(0, 0, NW, H, fill="#C2C2C2", stipple="gray50", outline="")
        self.wave_cv.create_rectangle(0, 0, WW, H, fill="#C2C2C2", stipple="gray50", outline="")
        # 點亮「將落入的容器」：框出該群組整塊
        hl = self._drop.get("hl")
        if hl is not None and self._drop.get("valid"):
            span = self._group_visible_span(rows, hl)
            if span:
                y0 = HH + span[0] * RH; y1 = HH + (span[1] + 1) * RH
                for cv, w in ((self.name_cv, NW), (self.wave_cv, WW)):
                    cv.create_rectangle(1, y0 + 1, w - 1, y1 - 1,
                                        outline=Style.MARQUEE, width=2)
        # 插入線
        y = self._drop["y"]; col = Style.MARQUEE if self._drop["valid"] else "#CC2222"
        self.name_cv.create_line(0, y, NW, y, fill=col, width=3)
        self.wave_cv.create_line(0, y, WW, y, fill=col, width=3)

    def on_name_menu(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":              # ---- 群組標頭選單 ----
            gid = item[1]; meta = self.model.groups.get(gid, {})
            m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            m.add_command(label=("展開" if meta.get("collapsed") else "折疊"),
                          command=lambda: self._toggle_group(gid))
            m.add_command(label="群組調色…", command=lambda: self._color_group(gid))
            m.add_command(label="設定群組位移…", command=lambda: self._offset_group(gid))
            m.add_command(label="重新命名群組…", command=lambda: self._rename_group(gid))
            others = [g for g in self.model.groups if g != gid]
            if others:
                sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
                for g in others:
                    sub.add_command(label=self.model.groups[g].get("name", g),
                                    command=lambda t=g: self._merge_group_into(gid, t))
                m.add_cascade(label="合併至群組", menu=sub)
            m.add_separator()
            m.add_command(label="複製群組", command=lambda: self._copy_group(gid))
            if self.clip_group:
                m.add_command(label="貼上群組", command=self._paste_group)
            m.add_separator()
            m.add_command(label="解散群組（保留成員）", command=lambda: self._dissolve_group(gid))
            m.add_command(label="刪除群組（含成員）", command=lambda: self._delete_group(gid))
            try:
                m.tk_popup(e.x_root, e.y_root)
            finally:
                m.grab_release()
            return
        s = item[1]                          # ---- 訊號選單 ----
        if s not in self.sig_sel:
            self.sig_sel = {s}; self.selected = s; self._sig_anchor = s
            self.render()
        self._copy_ctx = "signals"
        n = len(self.sig_sel)
        scope = f"（{n} 條）" if n > 1 else ""
        grouped = any(self.model.signals[i].get("group") for i in self.sig_sel
                      if 0 <= i < len(self.model.signals))
        m = tk.Menu(self, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
        m.add_command(label=f"調色…{scope}", command=self.pick_color)
        m.add_command(label=f"清除顏色{scope}", command=self.clear_color)
        m.add_separator()
        m.add_command(label=f"設定位移…{scope}", command=self.set_offset_dialog)
        m.add_separator()
        m.add_command(label=f"建立新群組…{scope}", command=self.group_selected)
        if self.model.groups:
            sub = tk.Menu(m, tearoff=0, bg=Style.FACE, font=Style.UI_FONT)
            for g, me in self.model.groups.items():
                sub.add_command(label=me.get("name", g),
                                command=lambda t=g: self._merge_selected_into(t))
            m.add_cascade(label=f"合併至群組{scope}", menu=sub)
        if grouped:
            m.add_command(label=f"移出群組{scope}", command=self._remove_from_group)
        m.add_separator()
        m.add_command(label="重新命名…", command=lambda: self._rename_signal(s))
        m.add_command(label=f"刪除訊號{scope}", command=self.del_signal)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _rename_signal(self, s):
        if 0 <= s < len(self.model.signals):
            new = simpledialog.askstring("改名", "訊號名稱:",
                                         initialvalue=self.model.signals[s]["name"], parent=self)
            if new:
                self.model.signals[s]["name"] = new; self.render()

    def on_name_rename(self, e):
        item = self._resolve_row(self.name_cv.canvasy(e.y))
        if item is None:
            return
        if item[0] == "group":
            self._rename_group(item[1])
        else:
            self._rename_signal(item[1])

    # ---- 群組操作 ----
    def group_selected(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        if not idxs:
            return
        name = simpledialog.askstring("建立新群組", "群組名稱:", initialvalue="群組", parent=self)
        if name is None:
            return
        sids = {self.model.signals[i]["sid"] for i in idxs}
        gid = self.model.group_signals(idxs, name)
        if gid:
            newidx = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
            self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
            self.render()
            nm = self.model.groups.get(gid, {}).get("name", gid)
            self.status.configure(text=f" 已建立群組「{nm}」（{len(newidx)} 條）；點標頭可折疊")

    def _merge_selected_into(self, target_gid):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        sids = {self.model.signals[i]["sid"] for i in idxs}
        res = self.model.merge_into_group(idxs, target_gid)
        if not res:
            return
        nm = self.model.groups.get(target_gid, {}).get("name", target_gid)
        newpos = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
        self.sig_sel = set(newpos); self.selected = newpos[0]; self._sig_anchor = newpos[0]
        self.render()
        self.status.configure(text=f" 已併入群組「{nm}」（{len(newpos)} 條）")

    def _merge_group_into(self, src_gid, target_gid):
        res = self.model.merge_groups(src_gid, target_gid)
        if res:
            self.render()
            self.status.configure(
                text=f" 已將群組巢狀至「{self.model.groups.get(target_gid, {}).get('name', target_gid)}」")
        else:
            self.status.configure(text=" 無法合併（不可移入自己的子群組）")

    def _remove_from_group(self):
        idxs = sorted(i for i in (self.sig_sel or {self.selected})
                      if 0 <= i < len(self.model.signals))
        moved = self.model.remove_from_group(idxs)
        self.render()
        self.status.configure(text=(f" 已移出 {moved} 條訊號（顏色回預設）" if moved
                                    else " 選取的訊號不在任何群組中"))

    def _dissolve_group(self, gid):
        self.model.ungroup([gid])           # 解散：children 提升一層 (保留巢狀子群組)
        self.render()
        self.status.configure(text=" 已解散群組（成員/子群組保留、提升一層）")

    def _delete_group(self, gid):
        nm = self.model.groups.get(gid, {}).get("name", gid)
        node = self.model._find_group_node(gid)
        n = len(self.model._dfs_leaves([node])) if node else 0
        if not messagebox.askyesno("刪除群組",
                                   f"確定刪除群組「{nm}」及其 {n} 條訊號？此動作無法復原。"):
            return
        self.model.delete_group(gid)
        if self.model.signals:
            self.selected = min(self.selected, len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._hover_node = None; self._hover_edge = None
        self.render()
        self.status.configure(text=f" 已刪除群組「{nm}」及 {n} 條訊號")

    def _offset_group(self, gid):
        node = self.model._find_group_node(gid)
        by = {s["sid"]: s for s in self.model.signals}
        members = [by[l["sid"]] for l in self.model._dfs_leaves([node])
                   if node and l["sid"] in by]
        if not members:
            return
        cur = members[0].get("offset", 0.0)
        v = simpledialog.askfloat("群組位移", "位移 (0 ~ 0.95，整組含子群組套用相同值):",
                                  initialvalue=cur, minvalue=0.0, maxvalue=0.95, parent=self)
        if v is None:
            return
        for s in members:
            s["offset"] = round(v, 2)
        self.render()
        self.status.configure(text=f" 群組整組位移設為 {round(v,2)}（{len(members)} 條）")

    def _copy_group(self, gid):
        meta = self.model.groups.get(gid, {})
        node = self.model._find_group_node(gid)
        if node is None:
            return
        by = {s["sid"]: s for s in self.model.signals}
        members = [self._copy_signal(by[l["sid"]])
                   for l in self.model._dfs_leaves([node]) if l["sid"] in by]
        if not members:
            return
        self.clip_group = {"name": meta.get("name", gid), "color": meta.get("color"),
                           "signals": members}
        self._clip_kind = "group"
        self.status.configure(text=f" 已複製群組「{self.clip_group['name']}」（{len(members)} 條）；Ctrl+V 貼上")

    def _paste_group(self):
        if not self.clip_group:
            return
        cg = self.clip_group; npd = self.model.n_periods
        gid = self.model.new_gid()
        gname = self._unique_name(cg["name"], {me.get("name") for me in self.model.groups.values()})
        names = {s["name"] for s in self.model.signals}
        children = []
        for sd in cg["signals"]:
            ns = self._copy_signal(sd)
            ns["name"] = self._unique_name(ns["name"], names); names.add(ns["name"])
            ns["group"] = gid
            ns["sid"] = self.model._new_sid()        # 複本需有獨立 sid
            while len(ns["cells"]) < npd:
                ns["cells"].append(self.model.new_cell("L"))
            del ns["cells"][npd:]
            self.model.signals.append(ns)            # 加入實體池
            children.append({"type": "sig", "sid": ns["sid"]})
        self.model.group_tree.append({"type": "group", "gid": gid, "name": gname,
                                      "collapsed": False, "color": cg.get("color"),
                                      "children": children})
        self.model._after_tree_change()
        sids = {c["sid"] for c in children}
        newidx = [i for i, s in enumerate(self.model.signals) if s["sid"] in sids]
        self.sig_sel = set(newidx); self.selected = newidx[0]; self._sig_anchor = newidx[0]
        self.render()
        self.status.configure(text=f" 已貼上群組「{gname}」（{len(children)} 條，新群組於底部）")

    def _toggle_group(self, gid):
        meta = self.model.groups.get(gid)
        if meta is not None:
            meta["collapsed"] = not meta.get("collapsed", False); self.render()

    def _rename_group(self, gid):
        meta = self.model.groups.get(gid)
        if meta:
            new = simpledialog.askstring("群組改名", "群組名稱:",
                                         initialvalue=meta.get("name", gid), parent=self)
            if new:
                meta["name"] = new; self.render()

    def _color_group(self, gid):
        meta = self.model.groups.get(gid)
        if not meta:
            return
        try:
            _, hx = colorchooser.askcolor(color=meta.get("color") or Style.WAVE,
                                          parent=self, title="群組顏色")
        except Exception:
            hx = None
        if hx:
            meta["color"] = hx; self.render()

    def add_signal(self):
        self.model.add_signal(); self.selected = len(self.model.signals) - 1
        self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        self._refresh_offset_field(); self.render()

    def del_signal(self):
        if not self.model.signals:
            return
        targets = sorted({s for s in (self.sig_sel or {self.selected})
                          if 0 <= s < len(self.model.signals)})
        if not targets:
            return
        if len(targets) > 1 and not messagebox.askyesno(
                "刪除訊號", f"確定刪除選取的 {len(targets)} 條訊號？"):
            return
        for s in reversed(targets):
            self.model.remove_signal(s)
        self.model.prune_groups(); self.model.prune_annotations()
        if self.model.signals:
            self.selected = min(targets[0], len(self.model.signals) - 1)
            self.sig_sel = {self.selected}; self._sig_anchor = self.selected
        else:
            self.selected = 0; self.sig_sel = set(); self._sig_anchor = None
        self.cell_sel = None; self._refresh_offset_field(); self.render()

    def do_new(self):
        if messagebox.askyesno("新增", "清空目前內容並新建？"):
            self.model = Model(); self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None; self.clip = None
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self._refresh_offset_field(); self.render()

    def do_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                filetypes=[("波型 JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        data = self.model.to_dict(); data["view"] = self.geom.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("儲存", f"已儲存:\n{path}")

    def do_open(self):
        path = filedialog.askopenfilename(filetypes=[("波型 JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            cleared = self.model.load_dict(d)
            if "view" in d:
                self.geom.load(d["view"])
                self.sp_w.delete(0, tk.END); self.sp_w.insert(0, str(self.geom.period_w))
                self.sp_h.delete(0, tk.END); self.sp_h.insert(0, str(self.geom.row_h))
                self.sp_r.delete(0, tk.END); self.sp_r.insert(0, str(int(self.geom.ramp_ratio * 100)))
            self.sp_p.delete(0, tk.END); self.sp_p.insert(0, str(self.model.n_periods))
            self.selected = 0; self.sig_sel = {0}; self._sig_anchor = 0
            self.cell_sel = None
            self._hover_node = None; self._hover_edge = None
            self._refresh_offset_field(); self.render()
            cn, ce = cleared or (0, 0)
            if cn or ce:
                self.status.configure(
                    text=f" 已開啟；偵測到無法對應的標注，已清除錨點 {cn}、關係線 {ce}")
        except Exception as ex:
            messagebox.showerror("開啟失敗", str(ex))

    def do_export(self):
        path = filedialog.asksaveasfilename(defaultextension=".png",
                filetypes=[("PNG 圖片", "*.png"), ("SVG 向量圖", "*.svg"),
                           ("EPS 向量圖", "*.eps"), ("PostScript", "*.ps")])
        if not path:
            return
        rows = self.model.layout()
        total_h = self.geom.header_h + len(rows) * self.geom.row_h
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        wave_w = self.model.n_periods * self.geom.period_w + max_off * self.geom.period_w
        lo = path.lower()
        if lo.endswith(".png"):
            scale = simpledialog.askinteger("PNG 解析度", "倍率 (1~4，越大越清晰):",
                                            initialvalue=2, minvalue=1, maxvalue=4, parent=self)
            if scale is None:
                return
            try:
                self._export_png(path, scale)
                messagebox.showinfo("匯出", f"已輸出 PNG（{scale}× 解析度）:\n{path}")
            except ImportError:
                messagebox.showwarning("匯出",
                    "PNG 匯出只需要 Pillow（不需要 Ghostscript）。\n請先安裝：\n  pip install pillow")
            except Exception as ex:
                messagebox.showerror("匯出失敗", str(ex))
        elif lo.endswith(".svg"):
            try:
                self._export_svg(path)
                messagebox.showinfo("匯出", f"已輸出 SVG（向量、可無限縮放）:\n{path}")
            except Exception as ex:
                messagebox.showerror("匯出失敗", str(ex))
        else:                                   # EPS / PS：tkinter 內建，無需任何套件
            sel = self.cell_sel; self.cell_sel = None; self.render()
            self.wave_cv.postscript(file=path, colormode="color",
                                    x=0, y=0, width=wave_w, height=total_h)
            self.cell_sel = sel; self.render()
            messagebox.showinfo("匯出", f"已輸出:\n{path}")

    def _export_png(self, path, scale):
        from PIL import Image, ImageDraw
        g = self.geom.copy_scaled(scale)
        fonts = _load_pil_fonts(scale)
        rows = self.model.layout()
        NW = g.name_w
        total_h = max(1, g.header_h + len(rows) * g.row_h)
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        wave_w = max(1, int(g.period_w * self.model.n_periods + max_off * g.period_w))
        name_img = Image.new("RGB", (max(1, NW), total_h), Style.CANVAS_BG)
        wave_img = Image.new("RGB", (wave_w, total_h), Style.CANVAS_BG)
        nd = PILCanvas(ImageDraw.Draw(name_img), fonts, scale=scale)
        wd = PILCanvas(ImageDraw.Draw(wave_img), fonts, scale=scale)
        self.engine.draw(nd, wd, self.model, set(), g, None)   # 不含選取高亮
        final = Image.new("RGB", (NW + wave_w, total_h), Style.CANVAS_BG)
        final.paste(name_img, (0, 0)); final.paste(wave_img, (NW, 0))
        final.save(path)

    def _export_svg(self, path):
        g = self.geom; rows = self.model.layout()
        NW = g.name_w
        total_h = g.header_h + len(rows) * g.row_h
        max_off = max((s.get("offset", 0.0) for s in self.model.signals), default=0.0)
        wave_w = int(g.period_w * self.model.n_periods + max_off * g.period_w)
        W, H = NW + wave_w, total_h
        elems = []
        name_sc = SVGCanvas(elems, xoff=0)
        wave_sc = SVGCanvas(elems, xoff=NW)
        self.engine.draw(name_sc, wave_sc, self.model, set(), g, None)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
               f'viewBox="0 0 {W} {H}">\n'
               f'<rect x="0" y="0" width="{W}" height="{H}" fill="{Style.CANVAS_BG}"/>\n'
               + "\n".join(elems) + "\n</svg>\n")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)

    # ---- WaveDrom 匯出 (交換格式；顏色/統一斜率視覺不保留，node/edge 可帶過去) ----
    def do_export_wavedrom(self):
        path = filedialog.asksaveasfilename(
            title="匯出 WaveDrom JSON", defaultextension=".json",
            filetypes=[("WaveDrom JSON", "*.json"), ("所有檔案", "*.*")])
        if not path:
            return
        try:
            self._export_wavedrom(path)
            messagebox.showinfo("匯出 WaveDrom",
                                f"已輸出 WaveDrom JSON：\n{path}\n\n"
                                "可貼到 wavedrom.com 或用 wavedrom-cli 算圖。\n"
                                "註：顏色與統一斜率等視覺由 WaveDrom 自行重畫，不會保留。")
        except Exception as ex:
            messagebox.showerror("匯出失敗", str(ex))

    def _export_wavedrom(self, path):
        m = self.model
        basech = {"CLK": "p", "H": "1", "L": "0", "HiZ": "z", "Unknown": "x", "BUS": "="}
        sid_nodes = {}                          # sid -> {period: nid}
        for nid, nd in m.nodes.items():
            sid_nodes.setdefault(nd["sid"], {})[nd["period"]] = nid

        def sig_obj(s):
            chars, data = [], []
            pt = ptxt = None
            for c in s["cells"]:
                t = c["type"]; txt = c.get("text", "")
                same = (pt == "BUS" and txt == ptxt) if t == "BUS" else (t == pt)
                if pt is not None and same:
                    chars.append(".")
                else:
                    ch = basech.get(t, "x"); chars.append(ch)
                    if ch == "=":
                        data.append(txt)
                pt, ptxt = t, txt
            o = {"name": s["name"], "wave": "".join(chars)}
            if data:
                o["data"] = data
            off = s.get("offset", 0.0)
            if off:
                o["phase"] = -round(off, 3)     # WaveDrom phase 正值=左移，故取負
            nm = sid_nodes.get(s.get("sid"))
            if nm:
                arr = ["."] * m.n_periods
                for p, nid in nm.items():
                    if 0 <= p < m.n_periods:
                        arr[p] = nid
                o["node"] = "".join(arr)
            return o

        by_sid = {s["sid"]: s for s in m.signals}

        def walk(nodes):
            out = []
            for nd in nodes:
                if nd.get("type") == "group":
                    grp = [nd.get("name", nd.get("gid", ""))]
                    grp += walk(nd.get("children", []))
                    out.append(grp)
                else:
                    s = by_sid.get(nd.get("sid"))
                    if s is not None:
                        out.append(sig_obj(s))
            return out
        sig = walk(m.group_tree)

        doc = {"signal": sig}
        if m.edges:
            op = {"double": "<->", "single": "->", "measure": "-"}
            ed = []
            for e in m.edges:
                if e["frm"] in m.nodes and e["to"] in m.nodes:
                    line = f'{e["frm"]}{op.get(e.get("style", "double"), "<->")}{e["to"]}'
                    if e.get("label"):
                        line += f' {e["label"]}'
                    ed.append(line)
            if ed:
                doc["edge"] = ed
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    def help_usage(self):
        messagebox.showinfo("使用說明",
            "【畫波形】選元件後：點一格畫一格；拖曳沿起始列刷 (鎖列)。\n"
            "  · BUS：原本是 BUS 的格會保留延續；非 BUS 的格才轉成 BUS。\n"
            "         再點同格可輸入/修改資料值。\n"
            "【框選 (畫布)】Shift 或 Ctrl + 拖曳都是純框選：\n"
            "  · 框選後按元件鍵 = 整塊填入 (BUS 問一次文字)。\n"
            "  · Ctrl+C 複製、移到目標格 Ctrl+V 貼上 (超出列數自動新增列)。\n"
            "【名稱欄】點選訊號 (Ctrl/Shift 多選)；按住上下拖曳可移動：\n"
            "  · 拖到群組標頭下半/群組內 = 併入該群組(游標位置即插入點，合併+排序一次到位)。\n"
            "  · 拖到群組標頭上半 = 移到該群組之前(同層)；拖到頂層訊號間 = 移出到頂層。\n"
            "  · 拖群組標頭 = 整組移動，落在另一群組上即巢狀為子群組(不可落入自己子孫)。\n"
            "  · 拖曳時背景反灰、點亮將落入的容器並顯示插入線。\n"
            "  · 群組標頭右鍵：折疊/調色/群組位移/複製/合併(巢狀)/解散/刪除(含成員)。\n"
            "  · 巢狀：訊號右鍵「合併至群組」可放入；群組右鍵「合併至群組」成為子群組。\n"
            "【標注】波形右鍵 →「在此建立錨點」(吸附到最近的格邊緣)。\n"
            "  · 游標移到錨點上會高亮；按住錨點拖曳到另一錨點即建立關係線\n"
            "    (拉線時波形會反灰冷凍，凸顯前景)；放開後輸入標籤 (如 t_su)。\n"
            "  · 錨點/關係線：游標移上去高亮後按 Del 刪除；關係線右鍵可改標籤/箭頭樣式。\n"
            "【拖曳模式】按 Esc 退回拖曳模式（取消元件選擇、清除框選）：\n"
            "  · 左鍵拖曳 = 平移畫布（不會誤畫元件）。\n"
            "  · Shift/Ctrl + 左鍵拖曳 = 框選（與繪製模式相同）。\n"
            "  · 點元件鈕或按 1~6 數字鍵即回到繪製模式。\n"
            "【位移】右移 offset 後左緣自動延伸第一格準位、右端裁齊，呈現延續感。\n"
            "【匯出】圖片 PNG(1–4×)/SVG(向量)/EPS；另可匯出 WaveDrom JSON 交換格式。\n"
            "【其他】波形右鍵亦可「清成 L」；雙擊名稱改名；Esc 退回拖曳模式並清除框選。")

    def help_keys(self):
        messagebox.showinfo("快捷鍵",
            "Ctrl+N/O/S/E 新增/開啟/儲存/匯出   Ctrl+C/V 複製/貼上\n"
            "1~6 切換元件 (CLK/H/L/BUS/HiZ/Unknown)\n"
            "Esc 拖曳模式(取消元件選擇/清除框選)；拖曳模式下左鍵拖曳=平移畫布\n"
            "Shift/Ctrl+拖曳 框選(兩種模式皆可)   按元件鍵=填入框選\n"
            "名稱欄 Ctrl/Shift+點擊 多選 -> 右鍵選單(調色/位移/群組/改名/刪除)\n"
            "波形右鍵 建立錨點/清成L；拖曳錨點拉關係線；Del 刪除標注\n"
            "雙擊名稱 改名")

    def help_about(self):
        messagebox.showinfo("關於", "RetroWave v1.18\n數位電路波型繪製工具\nPython + tkinter")


if __name__ == "__main__":
    App().mainloop()
