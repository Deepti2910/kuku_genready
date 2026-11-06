"""GenReady CLI: check a folder (or zip) of episode scripts before AI generation.

    python run_qa.py demo_show                 # bundled synthetic show
    python run_qa.py path/to/scripts.zip -o out --dub Spanish
"""
import argparse
from collections import Counter
from pathlib import Path

from genready.checks import DUB_EXPANSION, Settings
from genready.parse import load_show, load_zip
from genready.report import run_qa, write_outputs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scripts", help="folder of episode .txt files, or a .zip of them")
    ap.add_argument("-o", "--out", default="genready_out")
    ap.add_argument("--dub", default="Hindi", choices=list(DUB_EXPANSION))
    ap.add_argument("--max-clip", type=float, default=8.0)
    ap.add_argument("--max-episode", type=float, default=120.0)
    ap.add_argument("--no-script", action="store_true",
                    help="don't write normalized_script.json or loglines (for confidential scripts)")
    a = ap.parse_args()

    src = Path(a.scripts)
    if src.suffix.lower() == ".zip":
        with open(src, "rb") as f:
            episodes = load_zip(f)
    else:
        episodes = load_show(src)
    if not episodes:
        raise SystemExit(f"No episode scripts found in {src}")

    s = Settings(dub_language=a.dub, max_clip=a.max_clip, max_episode=a.max_episode)
    rep = run_qa(episodes, s)
    write_outputs(rep, episodes, a.out, include_script=not a.no_script)

    status = Counter(e["status"] for e in rep.episodes)
    print(f"{len(episodes)} episodes, {sum(len(e.lines) for e in episodes)} lines, "
          f"{len({l.speaker for e in episodes for l in e.lines})} speaker labels -> {len(set(rep.cmap.values()))} characters")
    print("Episodes:", ", ".join(f"{k} {v}" for k, v in status.most_common()))
    print("Issues by check:")
    for (check, sev), n in Counter((i.check, i.severity) for i in rep.issues).most_common():
        print(f"  {n:4}  {sev:4}  {check}")
    print(f"Wrote {a.out}/: issues.csv, episodes.csv, cast_proposal.json, cast_sheet.json"
          + ("" if a.no_script else ", normalized_script.json"))


if __name__ == "__main__":
    main()
