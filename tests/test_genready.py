"""Run: python -m pytest -q   (or python tests/test_genready.py)"""
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genready import cast as C                                  # noqa: E402
from genready.checks import Settings                            # noqa: E402
from genready.parse import load_show, load_zip, parse_text      # noqa: E402
from genready.report import normalized_script, run_qa           # noqa: E402

DEMO = ROOT / "demo_show"


def demo():
    return load_show(DEMO)


def by_check(rep, check, episode=None):
    return [i for i in rep.issues if i.check == check and (episode is None or i.episode == episode)]


def test_demo_parses():
    eps = demo()
    assert [e.number for e in eps] == [1, 2, 3]
    assert all(e.lines and e.shots for e in eps)


def test_cast_proposal():
    rows = {r.label: r for r in C.build_cast(demo())}
    assert rows["LADY MIRA"].character == "MIRA" and rows["LADY MIRA"].confidence == "auto"
    assert rows["THE VEILED STRANGER"].character == "KAEL" and rows["THE VEILED STRANGER"].confidence == "suggested"
    assert rows["THE MASKED ENVOY"].character == "THE MASKED ENVOY"


def test_same_surname_is_not_merged():
    script = """EPISODE NUMBER: Episode 1
EPISODE LOGLINE: Lord Ashby and Lady Ashby argue.

SCENE 01
Scene heading: INT. HALL – DAY
Scene start: 00:00.00
Scene end: 00:10.00

**CAMERA:**
Start: (00:00.00) | End: (00:10.00)
Wide shot of Lord Ashby and Lady Ashby. Ashby paces. Ashby sits.

**LORD ASHBY (Angry):**
Start: (00:01.00) | End: (00:03.00)
"You spent it all."

**LADY ASHBY (Cold):**
Start: (00:04.00) | End: (00:06.00)
"On your debts."
"""
    rows = {r.label: r.character for r in C.build_cast([parse_text(script, "episode-001.txt")])}
    assert rows["LORD ASHBY"] != rows["LADY ASHBY"]


def test_appearance_conflict():
    rep = run_qa(demo())
    assert any(c["character"] == "MIRA" and c["feature"] == "eyes" and set(c["values"]) == {"green", "hazel"}
               for c in rep.conflicts)


def test_timing_checks_find_the_planted_problems():
    rep = run_qa(demo(), Settings(dub_language="Hindi"))
    assert [i.severity for i in by_check(rep, "speech rate", 1)] == ["FAIL"]
    assert by_check(rep, "dub fit", 2)
    assert by_check(rep, "overlapping lines", 2)
    assert by_check(rep, "shot gap", 1)
    assert by_check(rep, "shot too long", 2)
    assert by_check(rep, "line without a shot", 3)
    assert by_check(rep, "episode length", 2)[0].severity == "WARN"
    status = {e["episode"]: e["status"] for e in rep.episodes}
    assert status[1] == "BLOCKED" and status[2] == "REVIEW"


def test_speech_rate_uses_the_tone_tag():
    def ep(tone):
        return parse_text(f"""EPISODE NUMBER: Episode 1

SCENE 01
Scene heading: INT. ROOM – DAY
Scene start: 00:00.00
Scene end: 00:05.00

**CAMERA:**
Start: (00:00.00) | End: (00:05.00)
Close-up of Ana.

**ANA ({tone}):**
Start: (00:01.00) | End: (00:03.20)
"I told you never to come back here."
""", "episode-001.txt")                     # 8 words in 2.2 s = 3.6 words/s
    s = Settings(dub_language="None")
    assert by_check(run_qa([ep("Whispering")], s), "speech rate")      # slow delivery: too fast
    assert not by_check(run_qa([ep("Shouting")], s), "speech rate")    # shouted: fine


def test_no_dub_language_means_no_dub_warnings():
    assert not by_check(run_qa(demo(), Settings(dub_language="None")), "dub fit")


def test_confirming_cast_clears_identity_questions():
    eps = demo()
    rows = C.build_cast(eps)
    assert by_check(run_qa(eps, rows=rows), "identity")
    assert not by_check(run_qa(eps, rows=rows, confirmed=True), "identity")


def test_human_edit_changes_mapping():
    eps = demo()
    rows = [r.__dict__ for r in C.build_cast(eps)]
    for r in rows:
        if r["label"] == "THE MASKED ENVOY":
            r["character"] = "dorian"
    rep = run_qa(eps, rows=[C.CastRow(**r) for r in rows], confirmed=True)
    assert rep.cmap["THE MASKED ENVOY"] == "DORIAN"


def test_export_closes_small_gaps_without_touching_input():
    eps = demo()
    before = [s.end for s in eps[0].shots]
    out = normalized_script(eps, run_qa(eps).cmap)
    assert out[0]["auto_fixes"]["shot_gaps_closed"] >= 1
    assert [s.end for s in eps[0].shots] == before
    spoken = [e for e in out[0]["events"] if e["kind"] == "dialogue"]
    assert {e["character"] for e in spoken} >= {"MIRA", "KAEL"}


def test_zip_upload_reads_only_scripts():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in DEMO.glob("*.txt"):
            z.writestr(f"show/{p.name}", p.read_text())
        z.writestr("show/notes.py", "print('not a script')")
        z.writestr("__MACOSX/show/._episode-001.txt", "junk")
    buf.seek(0)
    assert [e.number for e in load_zip(buf)] == [1, 2, 3]


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in inspect.getmembers(sys.modules[__name__], inspect.isfunction) if n.startswith("test_")]
    for f in fns:
        f()
    print(f"{len(fns)} tests passed")
