"""Put the checks together: issues, per-episode readiness, and the files handed to the generation step."""
import copy
import json
from collections import Counter, defaultdict
from dataclasses import dataclass

from . import cast as C
from .checks import FAIL, INFO, WARN, Issue, Settings, close_shot_gaps, run_checks
from .parse import fmt


@dataclass
class Report:
    issues: list
    episodes: list           # per-episode summary dicts
    cast_rows: list
    cmap: dict
    appearance: list         # raw appearance mentions
    conflicts: list


def identity_issues(episodes, rows):
    """Labels whose identity a person has not confirmed yet."""
    first = {}
    for ep in episodes:
        for ln in ep.lines:
            first.setdefault(ln.speaker, (ep.number, ln))
    out = []
    for r in rows:
        if r.confidence not in ("suggested", "unresolved") or r.label not in first:
            continue
        n, ln = first[r.label]
        if r.confidence == "suggested":
            msg = f'"{r.label}" ({r.lines} lines) looks like {r.character}: {r.reason}'
            fix = f"confirm in the cast sheet, so {r.label} gets {r.character.title()}'s face and voice"
        else:
            msg = f'"{r.label}" ({r.lines} lines, eps {r.episodes}): {r.reason}'
            fix = "decide who this is in the cast sheet before casting a face and voice"
        out.append(Issue(n, fmt(ln.start), ln.scene, "identity", WARN, r.label, msg, fix, ln.idx))
    return out


def appearance_issues(conflicts):
    out = []
    for c in conflicts:
        vals = "; ".join(f"{v} (ep {', '.join(map(str, eps))})" for v, eps in c["values"].items())
        first_ep = min(min(eps) for eps in c["values"].values())
        out.append(Issue(first_ep, "", 0, "appearance", WARN, c["character"],
                         f"{c['character'].title()}'s {c['feature']}: {vals}",
                         f"pick one {c['feature']} description for the character sheet and use it in every prompt"))
    return out


def run_qa(episodes, settings=None, rows=None, confirmed=False):
    """rows: cast rows (proposed or edited by a person). confirmed=True drops the identity questions."""
    settings = settings or Settings()
    rows = rows if rows is not None else C.build_cast(episodes)
    cmap = C.cast_map(rows)
    found = C.appearance(episodes, cmap)
    conflicts = C.appearance_conflicts(found)
    issues = run_checks(episodes, settings, cmap)
    if not confirmed:
        issues += identity_issues(episodes, rows)
    issues += appearance_issues(conflicts)
    issues.sort(key=lambda i: (i.episode, i.time))

    per = defaultdict(Counter)
    for i in issues:
        per[i.episode][i.severity] += 1
    summary = []
    for ep in episodes:
        c = per[ep.number]
        status = "BLOCKED" if c[FAIL] else "REVIEW" if c[WARN] else "READY"
        summary.append({"episode": ep.number, "status": status, "fail": c[FAIL], "warn": c[WARN],
                        "info": c[INFO], "length_s": round(ep.duration, 1), "lines": len(ep.lines),
                        "shots": len(ep.shots), "speakers": len({cmap.get(l.speaker, l.speaker) for l in ep.lines}),
                        "logline": ep.logline})
    return Report(issues, summary, rows, cmap, found, conflicts)


def cast_sheet(report):
    """Character bible seed: one entry per character with all its labels and its agreed look."""
    chars = defaultdict(lambda: {"labels": [], "lines": 0, "appearance": {}})
    for r in report.cast_rows:
        d = r if isinstance(r, dict) else r.__dict__
        ch = report.cmap[d["label"]]
        chars[ch]["labels"].append(d["label"])
        chars[ch]["lines"] += d["lines"]
    looks = defaultdict(Counter)
    for f in report.appearance:
        looks[(f["character"], f["feature"])][f["value"]] += 1
    for (ch, feat), cnt in looks.items():
        if ch in chars:
            value, n = cnt.most_common(1)[0]
            chars[ch]["appearance"][feat] = {"use": value, "seen": dict(cnt)}
    return dict(sorted(chars.items(), key=lambda kv: -kv[1]["lines"]))


def normalized_script(episodes, cmap):
    """The script with every speaker label replaced by its character: what the voice/face step consumes.
    Small shot gaps are closed (the previous shot is stretched); nothing else is changed."""
    out = []
    for ep in copy.deepcopy(episodes):
        closed = close_shot_gaps(ep)
        out.append({"episode": ep.number, "logline": ep.logline, "duration": round(ep.duration, 2),
                    "auto_fixes": {"shot_gaps_closed": closed},
                    "events": [{"t0": round(e.start, 2), "t1": round(e.end, 2), "kind": e.kind, "scene": e.scene,
                                **({"character": cmap.get(e.speaker, e.speaker), "label": e.speaker,
                                    "tones": e.tones} if e.kind == "dialogue" else {}),
                                "text": e.text} for e in ep.events]})
    return out


def write_outputs(report, episodes, folder, include_script=True):
    """Write issues.csv, episodes.csv, cast_proposal.json, cast_sheet.json and normalized_script.json.
    include_script=False leaves out the full script and the loglines (for confidential inputs)."""
    import csv
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "issues.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(Issue.__dataclass_fields__))
        w.writeheader()
        w.writerows(i.row() for i in report.issues)
    with open(folder / "episodes.csv", "w", newline="", encoding="utf-8") as f:
        rows = [r if include_script else {k: v for k, v in r.items() if k != "logline"} for r in report.episodes]
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (folder / "cast_proposal.json").write_text(json.dumps(
        [r if isinstance(r, dict) else r.__dict__ for r in report.cast_rows], indent=2), encoding="utf-8")
    (folder / "cast_sheet.json").write_text(json.dumps(cast_sheet(report), indent=2), encoding="utf-8")
    if include_script:
        (folder / "normalized_script.json").write_text(
            json.dumps(normalized_script(episodes, report.cmap), indent=1, ensure_ascii=False), encoding="utf-8")
