# -*- coding: utf-8 -*-
"""Document core (logic unit): signal pool + group tree + annotations + persistence.
Fully headless (must not import tkinter). Design spec §2/§5/§10;
the executable version of the invariants in §2.6 lives in tests/conftest.py::assert_invariants."""
from collections import namedtuple

# Visible row: kind='group'|'sig'; ref=gid or signal index; depth=nesting depth; gcol=inherited group color
Row = namedtuple("Row", "kind ref depth gcol")

DEFAULT_PERIODS = 12


class Model:
    def __init__(self):
        self.n_periods = DEFAULT_PERIODS; self.signals = []
        self.groups = {}              # gid -> group node (rebuilt from the group tree, lets existing code fetch meta by gid)
        self.group_tree = []          # structural truth: nested group tree (nodes below), leaves reference signal entities by sid
        self.nodes = {}               # nid -> {sid, period, edge}  (annotation anchors)
        self.edges = []               # [{frm, to, label, style}]   (relation lines)
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
        self.group_tree.append({"type": "sig", "sid": sid})   # new signal lands at top level (leaf order == signals order)

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

    # ---- groups (the group tree is the structural truth; signals stay consistent with DFS leaf order; signal['group']=cache of direct parent gid) ----
    def layout(self):
        """Recursively expand the group tree and return visible rows Row(kind, ref, depth, gcol).
        Group rows: ref=gid, gcol=the group's own color; signal rows: ref=signal index, gcol=inherited from the nearest ancestor group's color.
        Collapsed groups do not expand their children."""
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

    # ---- low-level group tree operations ----
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
        """Return (children_list, index) pointing to the leaf node for this sid, or None if not found."""
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
        """Return (parent_gid, children_list, index); parent_gid=None means top level."""
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
        """Whether other is gid itself or one of its descendant groups."""
        if gid == other:
            return True
        node = self._find_group_node(gid)
        if node is None:
            return False
        return self._find_group_node(other, node.get("children", [])) is not None

    def move_leaves_to(self, sids, index, container_gid=None):
        """Move one or several signal leaves into the target container at index
        (container None = top level; a single signal is a one-element set), as
        one contiguous block preserving their current DFS leaf order. Marker
        method: one placeholder is inserted, every sid detached, then the
        marker is replaced by the whole block — so indices auto-correct and a
        downward move within the same container lands without an off-by-one."""
        order = {nd["sid"]: k for k, nd in enumerate(self._dfs_leaves())}
        sids = sorted({s for s in sids if s in order}, key=lambda s: order[s])
        if not sids:
            return False
        cont = self._container_children(container_gid)
        if cont is None:
            return False
        index = max(0, min(len(cont), index))
        marker = {"type": "_marker"}
        cont.insert(index, marker)
        leaves = [n for n in (self._detach_sid(s) for s in sids) if n is not None]
        if not leaves:
            cont.remove(marker); self._after_tree_change(); return False
        at = cont.index(marker)
        cont[at:at + 1] = leaves                 # replace the marker with the block
        self._after_tree_change()
        return True

    def move_group_to(self, gid, index, container_gid=None):
        """Move a group to the given position in the target container (None=top level, nested if a group). Guard: cannot move into itself or its descendants."""
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
        for s in self.signals:                  # safety: signals missing from the tree are added back at top level
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
                        s["group"] = parent_gid       # cache of direct parent group gid
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
        """Combine the selected signals into a brand-new group (inserted at the top-level position of the first selected one). Return the gid."""
        sids = [self.signals[i]["sid"] for i in indices if 0 <= i < len(self.signals)]
        order = {nd["sid"]: k for k, nd in enumerate(self._dfs_leaves())}
        sids = sorted(set(sids), key=lambda s: order.get(s, 1 << 30))
        if not sids:
            return None
        marker = {"type": "_marker"}
        self.group_tree.insert(self._top_index_of_sid(sids[0]), marker)
        children = [c for c in (self._detach_sid(s) for s in sids) if c]
        gid = self.new_gid()
        node = {"type": "group", "gid": gid, "name": name or f"Group{self._gid_seq}",
                "collapsed": False, "color": None, "children": children}
        self.group_tree[self.group_tree.index(marker)] = node
        self._after_tree_change()
        return gid

    def merge_into_group(self, indices, target_gid):
        """Move the selected signals into the given group (appended to the end of its children)."""
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
        """Move the entire src group into the target group as a sub-group (nested)."""
        if src_gid == target_gid:
            return None
        tgt = self._find_group_node(target_gid)
        if tgt is None:
            return None
        # cannot move a group into its own descendants
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
        """Move the selected (grouped) signals to the top level (out of all groups); their color resets to default. Return the count."""
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
        """Dissolve groups: promote their children up one level in place (keeping nested sub-groups and members)."""
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
        """Delete a group along with all signals in its entire subtree. Return the number of signals deleted."""
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

    # ---- annotations (anchor node + relation edge; independent layer, anchored by sid so reordering doesn't affect it) ----
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
        return len(orphan_nodes), before_edges - len(self.edges)   # (anchors cleared, relation lines cleared)

    def to_dict(self):
        return {"version": "2.0", "n_periods": self.n_periods,
                "signals": self.signals, "group_tree": self.group_tree,
                "nodes": self.nodes, "edges": self.edges}

    def _migrate_flat_to_tree(self, gmeta):
        """Old format (signal['group']=gid + groups dict) -> single-level group tree."""
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
        if gt is not None:                      # new format: use the group tree directly
            self.group_tree = gt
        else:                                   # old format: flat groups -> tree (backward compatible)
            self._migrate_flat_to_tree(d.get("groups", {}))
        # restore the gid sequence number (avoid name collisions for newly created groups)
        self._gid_seq = 0
        for nd in self._all_group_nodes():
            try:
                self._gid_seq = max(self._gid_seq, int(str(nd["gid"]).lstrip("g") or 0))
            except ValueError:
                pass
        self._after_tree_change()
        return self.prune_annotations()        # (anchors cleared, relation lines cleared)

    def _all_group_nodes(self, nodes=None):
        if nodes is None:
            nodes = self.group_tree
        out = []
        for nd in nodes:
            if nd.get("type") == "group":
                out.append(nd); out += self._all_group_nodes(nd.get("children", []))
        return out
