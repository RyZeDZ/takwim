"""Building groups from headcounts, and knowing which groups overlap.

A section is split into TD groups, and the TD group also does the TP. If the department
splits TD groups for TP (rule split_tp_groups), each TD group gets TP subgroups.
A lecture for a section blocks all its groups; a TD/TP for G1 blocks G1, its section and its
subgroups, but not G2. `related()` returns that set.
"""
import math

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DB

from ..models import Group, Level
from ..rules import Rules, get_rules


class GroupTree:
    def __init__(self, groups: list):
        self.by_id = {g.id: g for g in groups}
        self.children: dict[int, list[int]] = {g.id: [] for g in groups}
        for g in groups:
            if g.parent_id in self.children:
                self.children[g.parent_id].append(g.id)

    @classmethod
    def load(cls, db: DB) -> "GroupTree":
        return cls(list(db.scalars(select(Group))))

    def ancestors(self, gid: int) -> list[int]:
        out, cur = [], self.by_id.get(gid)
        while cur is not None and cur.parent_id is not None:
            out.append(cur.parent_id)
            cur = self.by_id.get(cur.parent_id)
        return out

    def descendants(self, gid: int) -> list[int]:
        out, stack = [], list(self.children.get(gid, []))
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(self.children.get(c, []))
        return out

    def related(self, gid: int) -> set[int]:
        return {gid, *self.ancestors(gid), *self.descendants(gid)}

    def leaves(self) -> list[int]:
        return [gid for gid, kids in self.children.items() if not kids]


def split(total: int, parts: int) -> list[int]:
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def signature(level: Level, rules: Rules) -> str:
    tp = rules.tp_group_size if rules.split_tp_groups else 0
    return f"{level.headcount}|{rules.section_max_size}|{rules.td_group_size}|{tp}"


def _build_level(db: DB, level: Level, rules: Rules) -> dict:
    db.execute(delete(Group).where(Group.level_id == level.id))  # cascades to its sessions
    db.flush()
    n_sections = max(1, math.ceil(level.headcount / rules.section_max_size))
    td_counter = 0
    info = {"level": level.name, "headcount": level.headcount, "sections": []}
    for s_idx, s_size in enumerate(split(level.headcount, n_sections), start=1):
        section = Group(level_id=level.id, name=f"{level.name} - S{s_idx}", kind="section",
                        size=s_size)
        db.add(section)
        db.flush()
        sec_info = {"id": section.id, "name": section.name, "size": s_size, "td": []}
        n_td = max(1, math.ceil(s_size / rules.td_group_size))
        for td_size in split(s_size, n_td):
            td_counter += 1
            td = Group(level_id=level.id, name=f"{level.name} - G{td_counter}", kind="td",
                       size=td_size, parent_id=section.id)
            db.add(td)
            db.flush()
            td_info = {"id": td.id, "name": td.name, "size": td_size, "tp": []}
            n_tp = math.ceil(td_size / rules.tp_group_size) if rules.split_tp_groups else 1
            if n_tp > 1:  # otherwise the TD group itself does the TP
                for t_idx, tp_size in enumerate(split(td_size, n_tp)):
                    tp = Group(level_id=level.id, name=f"{td.name}{chr(97 + t_idx)}", kind="tp",
                               size=tp_size, parent_id=td.id)
                    db.add(tp)
                    db.flush()
                    td_info["tp"].append({"id": tp.id, "name": tp.name, "size": tp_size})
            sec_info["td"].append(td_info)
        info["sections"].append(sec_info)
    level.groups_signature = signature(level, rules)
    return info


def build_groups(db: DB, only_changed: bool = False) -> list[dict]:
    """Build the groups of every level (or only of levels whose headcount or the group-size
    rules changed since last time). Rebuilding a level removes that level's sessions."""
    rules = get_rules(db)
    summary = []
    for level in db.scalars(select(Level).order_by(Level.name)):
        if only_changed and level.groups_signature == signature(level, rules):
            continue
        summary.append(_build_level(db, level, rules))
    db.commit()
    return summary


def existing_structure(db: DB) -> list[dict]:
    tree = GroupTree.load(db)
    out = []
    for level in db.scalars(select(Level).order_by(Level.name)):
        sections = [g for g in tree.by_id.values() if g.level_id == level.id and g.kind == "section"]
        out.append({"level": level.name, "headcount": level.headcount, "sections": [
            {"id": s.id, "name": s.name, "size": s.size, "td": [
                {"id": t, "name": tree.by_id[t].name, "size": tree.by_id[t].size, "tp": [
                    {"id": p, "name": tree.by_id[p].name, "size": tree.by_id[p].size}
                    for p in sorted(tree.children[t])]}
                for t in sorted(tree.children[s.id])]}
            for s in sorted(sections, key=lambda g: g.name)]})
    return out
