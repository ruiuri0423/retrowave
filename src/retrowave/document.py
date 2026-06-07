# -*- coding: utf-8 -*-
"""傳遞層：UI 與文件核心之間唯一的「寫」通道（設計文件 §14、DEVELOPMENT.md §8）。

職責
  - 具名命令方法（§14.3 目錄）：shell 對文件的所有變更一律走這裡（R1）；
    讀路徑（layout/engine/命中測試）依 CQRS 唯讀直通 `doc.model`。
  - change 事件（§14.4）：成功變更後發 `changed(scopes)`；scheduler 為**注入式**
    （tk 下傳 `after_idle` 合併派發、測試/headless 傳 None = 同步），本模組不碰 tkinter。
  - 手勢交易 `begin()/commit()`：一次筆刷/拖曳 = 一個 undo 單位（R5），
    交易中的命令即時生效、即時發事件，commit 才結算 undo。
  - 快照式 Undo/Redo（§14.5）：深度 UNDO_DEPTH。

錯誤策略（明文化；各命令依此實作）
  1. 命令成功 → 回傳有意義的值（gid、新索引、筆數、True…）並發 changed 事件。
  2. 使用者級不合法（移入子孫、空選取、越界、無效把手…）→ 回 False/None/0/[]，
     不發事件、文件不變（原子）。
  3. 程式級錯誤（壞檔、不變量破裂）→ 拋例外，絕不吞；load 失敗自動還原。
  4. 不存在「靜默 no-op」第三態：呼叫者永遠能從回傳值區分做了/沒做。
"""
import copy

from .model import Model


def unique_name(name, existing):
    """撞名時補 _2/_3… 後綴。"""
    if name not in existing:
        return name
    i = 2
    while f"{name}_{i}" in existing:
        i += 1
    return f"{name}_{i}"


class Document:
    """命令層 facade。持有 Model（唯一一致性邊界），shell 只透過命令寫入。"""

    UNDO_DEPTH = 5
    SCOPES = ("cells", "structure", "annotations", "document")

    def __init__(self, scheduler=None):
        self._model = Model()
        self._scheduler = scheduler        # callable(fn)；None = 事件同步派發
        self._subs = []
        self._pending = set()              # 待派發 scopes
        self._flush_queued = False
        self._undo = []                    # [snapshot]，snapshot = to_dict 深拷貝
        self._redo = []
        self._txn = None                   # 手勢交易起點快照

    # ---------------------------------------------------------------- 讀路徑
    @property
    def model(self):
        """CQRS 讀路徑：渲染/版面/命中測試唯讀直通。寫入一律走命令。"""
        return self._model

    def container_children(self, gid):
        """讀：容器（None=頂層）的 children 列表（拖曳落點解析用）。"""
        return self._model._container_children(gid)

    def locate(self, pred):
        """讀：以述詞定位樹節點，回 (parent_gid, children, index) 或 None。"""
        return self._model._locate(pred)

    def is_self_or_descendant(self, gid, other):
        """讀：other 是否為 gid 自己或其子孫（拖曳防環）。"""
        return self._model._is_self_or_descendant(gid, other)

    def group_member_indices(self, gid):
        """讀：群組整棵子樹成員在訊號池中的索引（葉序）。群組不存在回 []。"""
        node = self._model._find_group_node(gid)
        if node is None:
            return []
        sid2idx = {s["sid"]: i for i, s in enumerate(self._model.signals)}
        return [sid2idx[l["sid"]] for l in self._model._dfs_leaves([node])
                if l["sid"] in sid2idx]

    # ---------------------------------------------------------------- 事件
    def subscribe(self, fn):
        """fn(scopes: set[str])；同一事件迴圈周期內的多個命令合併為一次通知。"""
        self._subs.append(fn)

    def _emit(self, scope):
        self._pending.add(scope)
        if self._scheduler is None:
            self._flush()
        elif not self._flush_queued:
            self._flush_queued = True
            self._scheduler(self._flush)

    def _flush(self):
        self._flush_queued = False
        scopes, self._pending = self._pending, set()
        if not scopes:
            return
        for fn in list(self._subs):
            fn(set(scopes))

    # ---------------------------------------------------------------- 快照 / 交易 / undo
    def _snapshot(self):
        return copy.deepcopy(self._model.to_dict())

    def _load_snapshot(self, snap):
        m = Model()
        m.load_dict(copy.deepcopy(snap))   # 深拷貝：棧中快照保持純淨
        self._model = m

    def _before(self):
        """命令開頭呼叫：交易中回 None（commit 才結算 undo），否則回快照。"""
        return None if self._txn is not None else self._snapshot()

    def _mutated(self, scope, before):
        """成功變更的統一收尾：undo 入棧（交易中除外）＋ 發事件。"""
        if before is not None:
            self._push_undo(before)
        self._emit(scope)

    def _push_undo(self, snap):
        self._undo.append(snap)
        del self._undo[:-self.UNDO_DEPTH]
        self._redo.clear()

    def begin(self):
        """開始手勢交易（巢狀呼叫安全：只認最外層）。"""
        if self._txn is None:
            self._txn = self._snapshot()

    def commit(self):
        """結束手勢交易；期間若有實際變更，整段成為一個 undo 單位。"""
        if self._txn is None:
            return False
        snap, self._txn = self._txn, None
        if snap != self._model.to_dict():
            self._push_undo(snap)
            return True
        return False

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def history(self):
        """讀：(可復原步數, 可重做步數)，供 shell 顯示狀態。"""
        return len(self._undo), len(self._redo)

    def undo(self):
        if self._txn is not None or not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._load_snapshot(self._undo.pop())
        self._emit("document")
        return True

    def redo(self):
        if self._txn is not None or not self._redo:
            return False
        self._undo.append(self._snapshot())     # 直接入棧：redo 棧不清空
        del self._undo[:-self.UNDO_DEPTH]
        self._load_snapshot(self._redo.pop())
        self._emit("document")
        return True

    # ---------------------------------------------------------------- 命令：cells
    def set_cell(self, sig, per, t, text=""):
        m = self._model
        if not (0 <= sig < len(m.signals) and 0 <= per < m.n_periods):
            return False
        before = self._before()
        m.set_cell(sig, per, t, text)
        self._mutated("cells", before)
        return True

    def set_n_periods(self, n):
        n = max(1, int(n))
        if n == self._model.n_periods:
            return False
        before = self._before()
        self._model.set_n_periods(n)
        self._mutated("structure", before)
        return True

    # ---------------------------------------------------------------- 命令：訊號
    def add_signal(self, name=None, fill="L"):
        before = self._before()
        self._model.add_signal(name, fill)
        self._mutated("structure", before)
        return len(self._model.signals) - 1

    def remove_signals(self, indices):
        m = self._model
        targets = sorted({i for i in indices if 0 <= i < len(m.signals)})
        if not targets:
            return 0
        before = self._before()
        for i in reversed(targets):
            m.remove_signal(i)
        m.prune_groups()
        m.prune_annotations()
        self._mutated("structure", before)
        return len(targets)

    def rename_signal(self, idx, name):
        m = self._model
        if not name or not (0 <= idx < len(m.signals)):
            return False
        before = self._before()
        m.signals[idx]["name"] = name
        self._mutated("structure", before)
        return True

    def set_offset(self, indices, value):
        m = self._model
        targets = [i for i in indices if 0 <= i < len(m.signals)]
        if not targets:
            return 0
        before = self._before()
        for i in targets:
            m.signals[i]["offset"] = round(value, 2)
        self._mutated("structure", before)
        return len(targets)

    def set_color(self, indices, color):
        """color=None 即清除自訂色。"""
        m = self._model
        targets = [i for i in indices if 0 <= i < len(m.signals)]
        if not targets:
            return 0
        before = self._before()
        for i in targets:
            m.signals[i]["color"] = color
        self._mutated("structure", before)
        return len(targets)

    # ---------------------------------------------------------------- 命令：群組
    def group_signals(self, indices, name=None):
        before = self._before()
        gid = self._model.group_signals(indices, name)
        if gid is None:
            return None
        self._mutated("structure", before)
        return gid

    def merge_into_group(self, indices, target_gid):
        before = self._before()
        res = self._model.merge_into_group(indices, target_gid)
        if res is None:
            return None
        self._mutated("structure", before)
        return res

    def merge_groups(self, src_gid, target_gid):
        before = self._before()
        res = self._model.merge_groups(src_gid, target_gid)
        if res is None:
            return None
        self._mutated("structure", before)
        return res

    def remove_from_group(self, indices):
        before = self._before()
        moved = self._model.remove_from_group(indices)
        if not moved:
            return 0
        self._mutated("structure", before)
        return moved

    def ungroup(self, gids):
        gids = [g for g in gids if g in self._model.groups]
        if not gids:
            return False
        before = self._before()
        self._model.ungroup(gids)
        self._mutated("structure", before)
        return True

    def delete_group(self, gid):
        before = self._before()
        n = self._model.delete_group(gid)
        if not n:
            return 0
        self._mutated("structure", before)
        return n

    def move_leaf_to(self, sid, container_gid, index):
        before = self._before()
        ok = self._model.move_leaf_to(sid, container_gid, index)
        if not ok:
            return False
        self._mutated("structure", before)
        return True

    def move_group_to(self, gid, container_gid, index):
        before = self._before()
        ok = self._model.move_group_to(gid, container_gid, index)
        if not ok:
            return False
        self._mutated("structure", before)
        return True

    def toggle_group(self, gid):
        meta = self._model.groups.get(gid)
        if meta is None:
            return None
        before = self._before()
        meta["collapsed"] = not meta.get("collapsed", False)
        self._mutated("structure", before)
        return meta["collapsed"]

    def rename_group(self, gid, name):
        meta = self._model.groups.get(gid)
        if meta is None or not name:
            return False
        before = self._before()
        meta["name"] = name
        self._mutated("structure", before)
        return True

    def set_group_color(self, gid, color):
        meta = self._model.groups.get(gid)
        if meta is None:
            return False
        before = self._before()
        meta["color"] = color
        self._mutated("structure", before)
        return True

    # ---------------------------------------------------------------- 命令：貼上 / 範本
    def _adopt_signal(self, payload, names, gid=None):
        """把剪貼簿/範本的訊號 payload 正規化成新實體（鐵則 2：配發新 sid）。"""
        m = self._model
        ns = {"name": unique_name(payload.get("name", "SIG"), names),
              "offset": float(payload.get("offset", 0.0)),
              "color": payload.get("color"), "group": gid,
              "sid": m._new_sid(),
              "cells": [{"type": c.get("type", "L"), "text": c.get("text", "")}
                        for c in payload.get("cells", [])]}
        names.add(ns["name"])
        while len(ns["cells"]) < m.n_periods:
            ns["cells"].append(m.new_cell("L"))
        del ns["cells"][m.n_periods:]
        return ns

    def _indices_of_sids(self, sids):
        return [i for i, s in enumerate(self._model.signals) if s["sid"] in sids]

    def paste_signals(self, payloads, at_idx=None):
        """貼上訊號複本（不分組），插在 at_idx 訊號所在頂層位置之後。回傳新索引。"""
        m = self._model
        if not payloads:
            return []
        before = self._before()
        names = {s["name"] for s in m.signals}
        at_top = len(m.group_tree)
        if at_idx is not None and 0 <= at_idx < len(m.signals):
            at_top = m._top_index_of_sid(m.signals[at_idx]["sid"]) + 1
        new_sids = []
        for k, payload in enumerate(payloads):
            ns = self._adopt_signal(payload, names, gid=None)
            m.signals.append(ns)
            m.group_tree.insert(at_top + k, {"type": "sig", "sid": ns["sid"]})
            new_sids.append(ns["sid"])
        m._after_tree_change()
        self._mutated("structure", before)
        return self._indices_of_sids(set(new_sids))

    def _paste_as_group(self, gname_wanted, payloads, color=None):
        """共用核心：把 payloads 立為新群組（掛在頂層尾端）。回傳 (gname, 新索引)。"""
        m = self._model
        before = self._before()
        gid = m.new_gid()
        gname = unique_name(gname_wanted, {me.get("name") for me in m.groups.values()})
        names = {s["name"] for s in m.signals}
        children = []
        for payload in payloads:
            ns = self._adopt_signal(payload, names, gid=gid)
            m.signals.append(ns)
            children.append({"type": "sig", "sid": ns["sid"]})
        m.group_tree.append({"type": "group", "gid": gid, "name": gname,
                             "collapsed": False, "color": color, "children": children})
        m._after_tree_change()
        self._mutated("structure", before)
        return gname, self._indices_of_sids({c["sid"] for c in children})

    def paste_group(self, payload):
        """貼上整個群組複本。payload = {name, color, signals}。"""
        if not payload or not payload.get("signals"):
            return None
        return self._paste_as_group(payload.get("name", "群組"),
                                    payload["signals"], payload.get("color"))

    def insert_template(self, name, tsignals):
        """插入範本：訊號立為同名群組。回傳 (群組名, 新索引) 或 None。"""
        if not tsignals:
            return None
        return self._paste_as_group(name, tsignals, None)

    # ---------------------------------------------------------------- 命令：標注
    def add_anchor(self, sid, period, edge):
        m = self._model
        if sid not in {s.get("sid") for s in m.signals}:
            return None
        before = self._before()
        nid = m.add_node(sid, period, edge)
        self._mutated("annotations", before)
        return nid

    def remove_anchor(self, nid):
        m = self._model
        if nid not in m.nodes:
            return False
        before = self._before()
        m.remove_node(nid)
        self._mutated("annotations", before)
        return True

    def add_edge(self, frm, to, label="", style="double"):
        before = self._before()
        e = self._model.add_edge(frm, to, label, style)
        if e is None:
            return None
        self._mutated("annotations", before)
        return e

    def set_edge_label(self, i, label):
        m = self._model
        if not (0 <= i < len(m.edges)):
            return False
        before = self._before()
        m.edges[i]["label"] = label
        self._mutated("annotations", before)
        return True

    def set_edge_style(self, i, style):
        m = self._model
        if not (0 <= i < len(m.edges)):
            return False
        before = self._before()
        m.edges[i]["style"] = style
        self._mutated("annotations", before)
        return True

    def remove_edge(self, i):
        m = self._model
        if not (0 <= i < len(m.edges)):
            return False
        before = self._before()
        del m.edges[i]
        self._mutated("annotations", before)
        return True

    # ---------------------------------------------------------------- 命令：文件
    def new_document(self):
        before = self._before()
        self._model = Model()
        self._mutated("document", before)
        return True

    def load_document(self, d):
        """載入 dict（壞資料拋例外且文件不變）。回傳 (清除錨點數, 清除關係線數)。"""
        before = self._snapshot()
        try:
            cleared = self._model.load_dict(copy.deepcopy(d))
        except Exception:
            self._load_snapshot(before)        # 原子：壞檔不留半套
            raise
        if self._txn is None:
            self._push_undo(before)
        self._emit("document")
        return cleared
