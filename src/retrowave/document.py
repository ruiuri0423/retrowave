# -*- coding: utf-8 -*-
"""Transfer layer: the only "write" channel between the UI and the document core (design spec §14).

Responsibilities
  - Named command methods (§14.3 catalog): all shell changes to the document go through here (R1);
    read paths (layout/engine/hit testing) pass through to `doc.model` read-only per CQRS.
  - Change events (§14.4): emit `changed(scopes)` after a successful change; the scheduler is **injected**
    (under tk, pass `after_idle` for coalesced dispatch; tests/headless pass None = synchronous), this module never touches tkinter.
  - Gesture transactions `begin()/commit()`: one brush/drag = one undo unit (R5);
    commands inside a transaction take effect and emit events immediately, undo is settled only at commit.
  - Snapshot-based Undo/Redo (§14.5): depth UNDO_DEPTH.

Error policy (made explicit; each command is implemented accordingly)
  1. Command succeeds -> return a meaningful value (gid, new index, count, True...) and emit a changed event.
  2. User-level invalid (moving into a descendant, empty selection, out of bounds, invalid handle...) -> return False/None/0/[],
     no event, document unchanged (atomic).
  3. Program-level error (bad file, broken invariant) -> raise, never swallow; load failure auto-restores.
  4. There is no "silent no-op" third state: the caller can always tell done/not-done from the return value.
"""
import copy

from .model import Model


def unique_name(name, existing):
    """Append a _2/_3... suffix on name collision."""
    if name not in existing:
        return name
    i = 2
    while f"{name}_{i}" in existing:
        i += 1
    return f"{name}_{i}"


class Document:
    """Command-layer facade. Holds the Model (the sole consistency boundary); the shell writes only through commands."""

    UNDO_DEPTH = 5
    SCOPES = ("cells", "structure", "annotations", "document")

    def __init__(self, scheduler=None):
        self._model = Model()
        self._scheduler = scheduler        # callable(fn); None = synchronous event dispatch
        self._subs = []
        self._pending = set()              # scopes pending dispatch
        self._flush_queued = False
        self._undo = []                    # [snapshot], snapshot = deep copy of to_dict
        self._redo = []
        self._txn = None                   # gesture transaction start snapshot

    # ---------------------------------------------------------------- read paths
    @property
    def model(self):
        """CQRS read path: render/layout/hit-testing pass through read-only. Writes always go through commands."""
        return self._model

    def container_children(self, gid):
        """Read: the children list of a container (None=top level) (for resolving drag drop targets)."""
        return self._model._container_children(gid)

    def locate(self, pred):
        """Read: locate a tree node by predicate, returning (parent_gid, children, index) or None."""
        return self._model._locate(pred)

    def is_self_or_descendant(self, gid, other):
        """Read: whether other is gid itself or one of its descendants (drag cycle prevention)."""
        return self._model._is_self_or_descendant(gid, other)

    def group_member_indices(self, gid):
        """Read: indices in the signal pool of all members of a group's entire subtree (leaf order). Returns [] if the group does not exist."""
        node = self._model._find_group_node(gid)
        if node is None:
            return []
        sid2idx = {s["sid"]: i for i, s in enumerate(self._model.signals)}
        return [sid2idx[l["sid"]] for l in self._model._dfs_leaves([node])
                if l["sid"] in sid2idx]

    # ---------------------------------------------------------------- events
    def subscribe(self, fn):
        """fn(scopes: set[str]); multiple commands within the same event-loop cycle are coalesced into one notification."""
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

    # ---------------------------------------------------------------- snapshot / transaction / undo
    def _snapshot(self):
        return copy.deepcopy(self._model.to_dict())

    def _load_snapshot(self, snap):
        m = Model()
        m.load_dict(copy.deepcopy(snap))   # deep copy: snapshots on the stack stay pristine
        self._model = m

    def _before(self):
        """Called at the start of a command: returns None during a transaction (undo settled at commit), otherwise returns a snapshot."""
        return None if self._txn is not None else self._snapshot()

    def _mutated(self, scope, before):
        """Unified wrap-up for a successful change: push undo (except during a transaction) + emit event."""
        if before is not None:
            self._push_undo(before)
        self._emit(scope)

    def _push_undo(self, snap):
        self._undo.append(snap)
        del self._undo[:-self.UNDO_DEPTH]
        self._redo.clear()

    def begin(self):
        """Begin a gesture transaction (nesting-safe: only the outermost is honored)."""
        if self._txn is None:
            self._txn = self._snapshot()

    def commit(self):
        """End the gesture transaction; if there were actual changes, the whole span becomes one undo unit."""
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
        """Read: (undoable steps, redoable steps), for the shell to display status."""
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
        self._undo.append(self._snapshot())     # push directly: don't clear the redo stack
        del self._undo[:-self.UNDO_DEPTH]
        self._load_snapshot(self._redo.pop())
        self._emit("document")
        return True

    # ---------------------------------------------------------------- commands: cells
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

    # ---------------------------------------------------------------- commands: signals
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
        """color=None clears the custom color."""
        m = self._model
        targets = [i for i in indices if 0 <= i < len(m.signals)]
        if not targets:
            return 0
        before = self._before()
        for i in targets:
            m.signals[i]["color"] = color
        self._mutated("structure", before)
        return len(targets)

    # ---------------------------------------------------------------- commands: groups
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

    def move_leaves_to(self, sids, index, container_gid=None):
        """Move one or several signals as one block (drag / multi-select drag);
        a single signal is a one-element set, container None = top level."""
        before = self._before()
        ok = self._model.move_leaves_to(sids, index, container_gid=container_gid)
        if not ok:
            return False
        self._mutated("structure", before)
        return True

    def move_group_to(self, gid, index, container_gid=None):
        before = self._before()
        ok = self._model.move_group_to(gid, index, container_gid=container_gid)
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

    # ---------------------------------------------------------------- commands: paste / templates
    def _adopt_signal(self, payload, names, gid=None):
        """Normalize a clipboard/template signal payload into a new entity (iron rule 2: assign a new sid)."""
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
        """Paste signal copies (ungrouped), inserted after the top-level position of the at_idx signal. Return the new indices."""
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
        """Shared core: establish payloads as a new group (appended at the top-level end). Return (gname, new indices)."""
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
        """Paste a copy of an entire group. payload = {name, color, signals}."""
        if not payload or not payload.get("signals"):
            return None
        return self._paste_as_group(payload.get("name", "Group"),
                                    payload["signals"], payload.get("color"))

    def insert_template(self, name, tsignals):
        """Insert a template: signals become a group of the same name. Return (group name, new indices) or None."""
        if not tsignals:
            return None
        return self._paste_as_group(name, tsignals, None)

    # ---------------------------------------------------------------- commands: annotations
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

    # ---------------------------------------------------------------- commands: document
    def new_document(self):
        before = self._before()
        self._model = Model()
        self._mutated("document", before)
        return True

    def load_document(self, d):
        """Load a dict (bad data raises and leaves the document unchanged). Return (anchors cleared, relation lines cleared)."""
        before = self._snapshot()
        try:
            cleared = self._model.load_dict(copy.deepcopy(d))
        except Exception:
            self._load_snapshot(before)        # atomic: a bad file leaves nothing half-applied
            raise
        if self._txn is None:
            self._push_undo(before)
        self._emit("document")
        return cleared
