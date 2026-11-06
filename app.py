"""GenReady: script QA before AI generation of a microdrama.  Run: streamlit run app.py"""
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from genready import cast as C
from genready.checks import DUB_EXPANSION, Settings
from genready.parse import load_show, load_zip, to_sec
from genready.report import cast_sheet, normalized_script, run_qa

HERE = Path(__file__).parent
DEMO = HERE / "demo_show"
STATUS_ICON = {"READY": "🟢 READY", "REVIEW": "🟡 REVIEW", "BLOCKED": "🔴 BLOCKED"}
SEV_ICON = {"FAIL": "🔴 FAIL", "WARN": "🟡 WARN", "INFO": "⚪ INFO"}

st.set_page_config(page_title="GenReady: script QA for AI microdramas", page_icon="🎬", layout="wide")


@st.cache_data(show_spinner=False)
def parse_zip(data: bytes):
    return load_zip(io.BytesIO(data))


@st.cache_data(show_spinner=False)
def parse_demo():
    return load_show(DEMO)


@st.cache_data(show_spinner=False)
def propose_cast(key, _episodes):
    return [r.__dict__ for r in C.build_cast(_episodes)]


def md(text):
    """Streamlit renders $...$ as LaTeX; scripts don't mean that."""
    return text.replace("$", "\\$")


# ---------------- sidebar: input + settings ----------------
st.sidebar.title("🎬 GenReady")
st.sidebar.caption("Catch script problems **before** you spend credits generating video.")
page = st.sidebar.radio("Page", ["📋 Overview", "🧑‍🤝‍🧑 Cast sheet", "⚠️ Issues", "🎞️ Episode inspector",
                                 "📦 Export", "ℹ️ How it works"], label_visibility="collapsed")

st.sidebar.divider()
source = st.sidebar.radio("Scripts", ["Demo show (synthetic)", "Upload a .zip of episode scripts"])
episodes, key, name = [], "", ""
if source.startswith("Demo"):
    episodes, key, name = parse_demo(), "demo", "The Salt Heiress (synthetic demo)"
else:
    up = st.sidebar.file_uploader("Zip of episode .txt files", type=["zip"])
    if up is not None:
        data = up.getvalue()
        key, name = hashlib.sha1(data).hexdigest()[:12], up.name
        try:
            episodes = parse_zip(data)
        except zipfile.BadZipFile:
            st.sidebar.error("That file is not a valid zip.")

with st.sidebar.expander("Settings", expanded=False):
    s = Settings()
    s.wps_warn = st.slider("Speech rate: warn above (words/s)", 2.5, 5.0, s.wps_warn, 0.1)
    s.wps_fail = st.slider("Speech rate: fail above (words/s)", 3.0, 6.0, s.wps_fail, 0.1)
    s.dub_language = st.selectbox("Dub language to plan for", list(DUB_EXPANSION),
                                  index=list(DUB_EXPANSION).index(s.dub_language))
    s.max_clip = st.slider("Longest clip your video model makes (s)", 3.0, 20.0, s.max_clip, 0.5)
    s.max_episode = st.slider("Max episode length (s)", 60.0, 240.0, s.max_episode, 5.0)
    st.caption(f"Dub expansion for {s.dub_language}: ×{DUB_EXPANSION[s.dub_language]:.2f} "
               "(rule of thumb, to calibrate on real dubs).")

if not episodes:
    st.title("GenReady")
    st.info("Upload a zip of episode scripts in the sidebar, or switch to the demo show.")
    st.stop()

# ---------------- cast state (the human-in-the-loop part) ----------------
if st.session_state.get("cast_key") != key:
    st.session_state.cast_key = key
    st.session_state.cast_rows = propose_cast(key, episodes)
    st.session_state.confirmed = False
rows = st.session_state.cast_rows
rep = run_qa(episodes, s, [C.CastRow(**r) for r in rows], confirmed=st.session_state.confirmed)
issues = pd.DataFrame([i.row() for i in rep.issues])
if issues.empty:
    issues = pd.DataFrame(columns=["episode", "time", "scene", "check", "severity", "who", "message", "fix", "event"])
summary = pd.DataFrame(rep.episodes)

st.sidebar.divider()
st.sidebar.caption(f"**{name}**  \n{len(episodes)} episodes · {sum(len(e.lines) for e in episodes)} lines")
if st.session_state.confirmed:
    st.sidebar.success("Cast confirmed ✔")
else:
    st.sidebar.warning("Cast not confirmed yet")


# ---------------- pages ----------------
def overview():
    st.title("📋 Is this show ready to generate?")
    st.caption(md(f"{name} · checked against your settings: ≤ {s.wps_warn:g}/{s.wps_fail:g} words/s, "
                  f"{s.dub_language} dub, clips ≤ {s.max_clip:g}s, episodes ≤ {s.max_episode:g}s"))
    st_count = Counter(summary.status)
    chars = len(set(rep.cmap.values()))
    labels = len(rep.cmap)
    c = st.columns(5)
    c[0].metric("Episodes", len(episodes))
    c[1].metric("🟢 Ready", st_count.get("READY", 0))
    c[2].metric("🟡 Review", st_count.get("REVIEW", 0))
    c[3].metric("🔴 Blocked", st_count.get("BLOCKED", 0))
    c[4].metric("Characters", chars, f"from {labels} speaker labels", delta_color="off")

    st.markdown("**🔴 Blocked** = at least one problem that breaks generation (a line too fast to voice, one "
                "character speaking twice at once). **🟡 Review** = worth a look. Fix, re-upload, re-check.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Episodes")
        view = summary.assign(status=summary.status.map(STATUS_ICON))[
            ["episode", "status", "fail", "warn", "length_s", "lines", "shots", "speakers", "logline"]]
        st.dataframe(view, hide_index=True, width="stretch", height=min(420, 40 + 35 * len(view)),
                     column_config={"logline": st.column_config.TextColumn(width="large"),
                                    "length_s": st.column_config.NumberColumn("length (s)")})
    with right:
        st.subheader("Problems by check")
        if issues.empty:
            st.success("No problems found.")
        else:
            by = issues.groupby(["check", "severity"]).size().reset_index(name="count")
            chart = alt.Chart(by).mark_bar().encode(
                y=alt.Y("check:N", sort="-x", title=None), x=alt.X("count:Q", title="issues"),
                color=alt.Color("severity:N", scale=alt.Scale(domain=["FAIL", "WARN", "INFO"],
                                                              range=["#d64545", "#e0a526", "#9aa5b1"])),
                tooltip=["check", "severity", "count"]).properties(height=320)
            st.altair_chart(chart, width="stretch")
    if not st.session_state.confirmed:
        n = int((issues.check == "identity").sum())
        if n:
            st.info(f"👉 {n} speaker label(s) need a decision about who they are. Open **Cast sheet**.")


def cast_page():
    st.title("🧑‍🤝‍🧑 Cast sheet: who is who?")
    st.markdown("AI tools cast **one face and one voice per character**. If the script calls the same person by "
                "several names, they get several faces. Check the proposal below, **edit the `character` "
                "column** where it's wrong (type the character it should map to), then confirm.")
    df = pd.DataFrame(rows)[["label", "character", "confidence", "lines", "episodes", "reason", "alternatives", "kind"]]
    order = {"unresolved": 0, "suggested": 1, "auto": 2, "self": 3}
    df = df.sort_values(["confidence", "lines"], key=lambda col: col.map(order) if col.name == "confidence"
                        else -col).reset_index(drop=True)
    only = st.toggle("Show only labels that need a decision", value=True)
    show = df[df.confidence.isin(["unresolved", "suggested", "auto"])] if only else df
    edited = st.data_editor(
        show, hide_index=True, width="stretch", key=f"editor_{key}", disabled=[c for c in show.columns if c != "character"],
        column_config={
            "character": st.column_config.TextColumn("character ✏️", help="Character this label really is"),
            "confidence": st.column_config.TextColumn(help="auto = title stripped; suggested = evidence below; "
                                                           "unresolved = rules can't tell; self = its own character"),
            "reason": st.column_config.TextColumn(width="large")})
    c1, c2 = st.columns([1, 3])
    if c1.button("✅ Confirm cast", type="primary"):
        changed = dict(zip(edited.label, edited.character))
        for r in rows:
            if r["label"] in changed:
                r["character"] = (changed[r["label"]] or r["label"]).strip().upper()
        st.session_state.cast_rows = rows
        st.session_state.confirmed = True
        st.rerun()
    if c2.button("↺ Reset to proposal"):
        st.session_state.cast_rows = propose_cast(key, episodes)
        st.session_state.confirmed = False
        st.rerun()

    st.subheader("Resulting characters")
    sheet = cast_sheet(rep)
    st.dataframe(pd.DataFrame([{"character": ch, "lines": v["lines"], "labels": ", ".join(v["labels"]),
                                "look (from stage directions)": "; ".join(f"{f}: {a['use']}" for f, a in v["appearance"].items())}
                               for ch, v in sheet.items()]), hide_index=True, width="stretch")

    st.subheader("Appearance continuity")
    if rep.conflicts:
        for cf in rep.conflicts:
            vals = ", ".join(f"**{v}** (ep {', '.join(map(str, e))})" for v, e in cf["values"].items())
            st.warning(f"{cf['character'].title()}'s {cf['feature']}: {vals}")
            for ev in cf["evidence"]:
                st.caption(f"› {ev}")
    else:
        st.success("No conflicting eye / hair / beard colours found.")


def issues_page():
    st.title("⚠️ Issues")
    if issues.empty:
        st.success("Nothing to fix.")
        return
    c = st.columns(3)
    sev = c[0].multiselect("Severity", ["FAIL", "WARN", "INFO"], default=["FAIL", "WARN"])
    checks = c[1].multiselect("Check", sorted(issues.check.unique()))
    eps = c[2].multiselect("Episode", sorted(issues.episode.unique()))
    f = issues[issues.severity.isin(sev)]
    if checks:
        f = f[f.check.isin(checks)]
    if eps:
        f = f[f.episode.isin(eps)]
    st.caption(f"{len(f)} of {len(issues)} issues")
    st.dataframe(f.assign(severity=f.severity.map(SEV_ICON)).drop(columns=["event"]), hide_index=True,
                 width="stretch", height=560,
                 column_config={"message": st.column_config.TextColumn(width="large"),
                                "fix": st.column_config.TextColumn(width="medium")})


def inspector():
    st.title("🎞️ Episode inspector")
    nums = [e.number for e in episodes]
    worst = summary.sort_values(["fail", "warn"], ascending=False).episode.iloc[0]
    n = st.selectbox("Episode", nums, index=nums.index(worst),
                     format_func=lambda x: f"Episode {x} · {STATUS_ICON[summary.set_index('episode').status[x]]}")
    ep = next(e for e in episodes if e.number == n)
    st.caption(md(ep.logline))
    bars = []
    for e in ep.events:
        if e.kind == "camera":
            bars.append({"lane": "📷 shots", "t0": e.start, "t1": e.end, "kind": "shot", "text": e.text})
        elif e.kind == "dialogue":
            who = rep.cmap.get(e.speaker, e.speaker)
            rate = len(e.text.split()) / max(e.end - e.start, 0.01)
            bars.append({"lane": f"🗣 {who}", "t0": e.start, "t1": e.end, "kind": "line",
                         "text": f"{e.speaker}: {e.text} ({rate:.1f} w/s)"})
    bars = pd.DataFrame(bars)
    ep_issues = issues[issues.episode == n].copy()
    marks = ep_issues[ep_issues.time != ""].copy()
    marks["t"] = [to_sec(*t.split(":")) for t in marks.time]
    base = alt.Chart(bars).mark_bar(cornerRadius=2, opacity=0.85).encode(
        x=alt.X("t0:Q", title="seconds"), x2="t1:Q", y=alt.Y("lane:N", title=None, sort=None, axis=alt.Axis(labelOverlap=False, labelLimit=240)),
        color=alt.Color("kind:N", scale=alt.Scale(domain=["shot", "line"], range=["#8fa9c7", "#4c78a8"]), legend=None),
        tooltip=["lane", alt.Tooltip("t0:Q", format=".2f"), alt.Tooltip("t1:Q", format=".2f"), "text"])
    layers = [base]
    if not marks.empty:
        layers.append(alt.Chart(marks).mark_rule(strokeWidth=2).encode(
            x="t:Q", color=alt.Color("severity:N", scale=alt.Scale(domain=["FAIL", "WARN", "INFO"],
                                                                  range=["#d64545", "#e0a526", "#9aa5b1"])),
            tooltip=["check", "severity", "message"]))
    lanes = bars.lane.nunique() if not bars.empty else 1
    st.altair_chart(alt.layer(*layers).properties(height=max(160, 60 + 36 * lanes)), width="stretch")
    st.caption("Blue bars: shots and spoken lines. Vertical lines: issues (hover for details).")
    st.dataframe(ep_issues.assign(severity=ep_issues.severity.map(SEV_ICON)).drop(columns=["episode", "event"]),
                 hide_index=True, width="stretch", column_config={"message": st.column_config.TextColumn(width="large")})


def export_page():
    st.title("📦 Export for the generation step")
    if not st.session_state.confirmed:
        st.warning("The cast isn't confirmed yet. The files below use the *proposed* mapping. Confirm it on the "
                   "**Cast sheet** page first.")
    files = {
        "issues.csv": issues.drop(columns=["event"]).to_csv(index=False),
        "episodes.csv": summary.to_csv(index=False),
        "cast_map.json": json.dumps(rep.cmap, indent=2),
        "cast_sheet.json": json.dumps(cast_sheet(rep), indent=2),
        "normalized_script.json": json.dumps(normalized_script(episodes, rep.cmap), indent=1, ensure_ascii=False),
    }
    what = {
        "issues.csv": "every problem, with time, who, and a suggested fix: the writer's to-do list",
        "episodes.csv": "per-episode status (READY / REVIEW / BLOCKED)",
        "cast_map.json": "speaker label → character: one face and one voice per character",
        "cast_sheet.json": "per character: all its labels, line count, agreed eye/hair colour for prompts",
        "normalized_script.json": "the script with labels replaced by characters and small shot gaps closed",
    }
    for fn, body in files.items():
        c1, c2 = st.columns([1, 3])
        c1.download_button(f"⬇ {fn}", body, file_name=fn, width="stretch")
        c2.caption(what[fn])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, body in files.items():
            z.writestr(fn, body)
    st.download_button("⬇ Download all (zip)", buf.getvalue(), file_name="genready_outputs.zip", type="primary")


def how_page():
    st.title("ℹ️ How it works")
    st.markdown(f"""
**Who it's for:** the person who turns a finished script into AI video: they generate faces, voices and
shots per line. **When:** after the script is written, *before* any credits are spent.

**Why:** generation is the expensive step, and the cheapest bugs to fix are the ones still in text. A line
that's too fast gets rushed or cut by the voice model; a character with two names gets two faces;
"green eyes" in one episode and "hazel" in another gives two different-looking leads.

| Check | What it catches | Default |
|---|---|---|
| **Identity** | One character under several labels (titles, "THE VEILED STRANGER" before the reveal) | person confirms |
| **Appearance** | Same character, different eye / hair / beard colour across episodes | any clash |
| **Speech rate** | Words per second in the line's slot; whispered/sobbing lines get a lower limit, shouted ones a higher one | warn > {Settings.wps_warn}, fail > {Settings.wps_fail} (±0.4 by tone) |
| **Dub fit** | Lines that fit in English but not after translation | ×1.15–1.30 by language |
| **Overlapping lines** | Two voices at once (fail if it's the same character) | > 0.05 s |
| **Shots** | Holes with no shot, overlapping shots, lines with no shot, shots longer than one AI clip | clip ≤ {Settings.max_clip:g} s |
| **Structure** | Events outside their scene, bad timestamps, episode length | ≤ {Settings.max_episode:g} s |

**Rules, not a model.** Every finding is reproducible and explains itself. Identity is the one place
where rules only *propose* (from titles, loglines that name a character who never speaks by name, and
describing words next to a name), and a **person confirms** in the cast sheet.

**Privacy:** an uploaded zip is read in memory for this session only; nothing is stored.
""")


{"📋 Overview": overview, "🧑‍🤝‍🧑 Cast sheet": cast_page, "⚠️ Issues": issues_page,
 "🎞️ Episode inspector": inspector, "📦 Export": export_page, "ℹ️ How it works": how_page}[page]()
