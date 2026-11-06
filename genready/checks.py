"""Timing and production checks: will each line and shot survive AI generation as written?

Every check returns Issue rows. Thresholds live in Settings so an operator can tune them per tool.
"""
from dataclasses import asdict, dataclass

from .parse import fmt

# Text-length expansion when dubbing from English. Rough industry rules of thumb, NOT measured here:
# treat them as starting assumptions to calibrate against real dubs.
DUB_EXPANSION = {"None": 1.0, "Hindi": 1.20, "Spanish": 1.25, "Portuguese": 1.25, "French": 1.20,
                 "German": 1.30, "Indonesian": 1.15}
FAIL, WARN, INFO = "FAIL", "WARN", "INFO"
# The script's own tone tags change how fast a line can be said: shouted lines run fast, whispered or
# sobbing lines run slow. The speech-rate limits move by TONE_SHIFT words/s for these.
FAST_TONES = {"urgent", "shouting", "screaming", "furious", "frantic", "panicked", "rapid", "explosive",
              "hurried", "yelling", "rushed", "excited"}
SLOW_TONES = {"whispering", "whisper", "solemn", "grave", "trembling", "weeping", "sobbing", "tearful",
              "hesitant", "low", "soft", "gentle", "tender", "heartbroken", "gasping", "faltering", "weak"}
TONE_SHIFT = 0.4


@dataclass
class Settings:
    wps_warn: float = 3.5          # words per second a voice model can say clearly (natural speech ~2.5-3)
    wps_fail: float = 4.0          # above this the line is rushed or clipped
    min_words: int = 4             # short exclamations ("Stop!") are exempt from rate checks
    dub_language: str = "Hindi"
    max_clip: float = 8.0          # longest single clip the video model makes (many tools: 5-10 s)
    max_episode: float = 120.0     # platform episode length
    min_episode: float = 60.0
    tolerance: float = 0.05        # timing slack, seconds


@dataclass
class Issue:
    episode: int
    time: str
    scene: int
    check: str
    severity: str
    who: str
    message: str
    fix: str
    event: int = -1

    def row(self):
        return asdict(self)


def _words(text):
    return len(text.split())


def speech_rate(ep, s, cmap):
    out = []
    factor = DUB_EXPANSION.get(s.dub_language, 1.0)
    for ln in ep.lines:
        n, dur = _words(ln.text), ln.end - ln.start
        if n < s.min_words or dur <= 0:
            continue
        wps = n / dur
        who = cmap.get(ln.speaker, ln.speaker)
        tones = set(ln.tones)
        shift = TONE_SHIFT * (bool(tones & FAST_TONES) - bool(tones & SLOW_TONES))
        warn, fail = s.wps_warn + shift, s.wps_fail + shift
        need = n / 3.0
        quote = ln.text if len(ln.text) < 70 else ln.text[:67] + "..."
        tone_note = f" [{', '.join(ln.tones)}: limit {warn:.1f}]" if shift else ""
        if wps > warn:
            sev = FAIL if wps > fail else WARN
            out.append(Issue(ep.number, fmt(ln.start), ln.scene, "speech rate", sev, who,
                             f'{n} words in {dur:.1f}s = {wps:.1f} words/s{tone_note}: "{quote}"',
                             f"give it {need:.1f}s (+{need - dur:.1f}s) or cut to {int(dur * 3.0)} words",
                             ln.idx))
        elif factor > 1 and wps * factor > fail:
            out.append(Issue(ep.number, fmt(ln.start), ln.scene, "dub fit", WARN, who,
                             f"fits in English ({wps:.1f} w/s) but a {s.dub_language} dub needs ~{factor:.2f}x "
                             f"the text: {wps * factor:.1f} w/s", f"leave {need * factor - dur:.1f}s of air after it, "
                             "or plan a shorter translation", ln.idx))
    return out


def overlaps(ep, s, cmap):
    """Two voices at once. Lip-sync models animate one speaking face per clip."""
    out = []
    lines = ep.lines
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if b.start >= a.end - s.tolerance:
                break
            ov = min(a.end, b.end) - b.start
            if ov <= s.tolerance:
                continue
            wa, wb = cmap.get(a.speaker, a.speaker), cmap.get(b.speaker, b.speaker)
            same = wa == wb
            out.append(Issue(ep.number, fmt(b.start), b.scene, "overlapping lines", FAIL if same else WARN,
                             wa if same else f"{wa} + {wb}",
                             f"{'the same character speaks twice' if same else 'two characters speak'} "
                             f"at once for {ov:.1f}s",
                             "shift the second line to start after the first ends" if same
                             else "stagger the lines, or plan it as one shot with a single speaking face",
                             b.idx))
    return out


def shots(ep, s, cmap):
    out = []
    cams = sorted(ep.shots, key=lambda e: e.start)
    for c in cams:
        if c.end - c.start > s.max_clip + s.tolerance:
            out.append(Issue(ep.number, fmt(c.start), c.scene, "shot too long", WARN, "",
                             f"{c.end - c.start:.1f}s shot; the video model makes at most {s.max_clip:.0f}s per clip",
                             "split into two shots (e.g. add a reaction cut) or plan an extend step", c.idx))
    for a, b in zip(cams, cams[1:]):
        gap = b.start - a.end
        if gap > s.tolerance:
            # a few frames of black is fixed automatically on export; a longer hole needs a decision
            out.append(Issue(ep.number, fmt(a.end), b.scene, "shot gap", INFO if gap < 0.25 else WARN, "",
                             f"{gap:.2f}s with no shot between {fmt(a.end)} and {fmt(b.start)} (black frames)",
                             f"extend the previous shot to {fmt(b.start)} (the export does this automatically)",
                             b.idx))
        elif gap < -s.tolerance:
            out.append(Issue(ep.number, fmt(b.start), b.scene, "shot overlap", WARN, "",
                             f"two shots run at once for {-gap:.2f}s", f"start the next shot at {fmt(a.end)}", b.idx))
    for ln in ep.lines:
        mid = (ln.start + ln.end) / 2
        if not any(c.start - s.tolerance <= mid <= c.end + s.tolerance for c in cams):
            out.append(Issue(ep.number, fmt(ln.start), ln.scene, "line without a shot", WARN,
                             cmap.get(ln.speaker, ln.speaker), f'no camera shot covers "{ln.text[:50]}"',
                             "add a shot (who is on screen when this is said?)", ln.idx))
    return out


def structure(ep, s, cmap):
    out = []
    for e in ep.events:
        if e.end <= e.start:
            out.append(Issue(ep.number, fmt(e.start), e.scene, "bad timestamp", FAIL, e.speaker,
                             f"ends at {fmt(e.end)}, not after it starts", "fix the timestamp", e.idx))
    bounds = {sc.number: sc for sc in ep.scenes}
    for e in ep.events:
        sc = bounds.get(e.scene)
        if sc and sc.end > sc.start and (e.start < sc.start - s.tolerance or e.end > sc.end + s.tolerance):
            out.append(Issue(ep.number, fmt(e.start), e.scene, "outside its scene", WARN,
                             cmap.get(e.speaker, e.speaker) if e.speaker else "",
                             f"{e.kind} {fmt(e.start)}-{fmt(e.end)} but scene {e.scene} is "
                             f"{fmt(sc.start)}-{fmt(sc.end)}", "fix the scene end or the event time", e.idx))
    d = ep.duration
    if d > s.max_episode:
        out.append(Issue(ep.number, fmt(d), 0, "episode length", WARN, "",
                         f"{d:.0f}s long (limit {s.max_episode:.0f}s)",
                         f"trim {d - s.max_episode:.0f}s, or split the episode", -1))
    elif d < s.min_episode:
        out.append(Issue(ep.number, fmt(d), 0, "episode length", INFO, "",
                         f"only {d:.0f}s long (expected at least {s.min_episode:.0f}s)", "check nothing is missing", -1))
    return out


def close_shot_gaps(ep, max_gap=2.0):
    """Mechanical fix for the export: stretch a shot to meet the next one. Returns how many gaps it closed."""
    cams = sorted(ep.shots, key=lambda e: e.start)
    n = 0
    for a, b in zip(cams, cams[1:]):
        if 0 < b.start - a.end <= max_gap:
            a.end = b.start
            n += 1
    return n


CHECKS = [speech_rate, overlaps, shots, structure]


def run_checks(episodes, settings, cmap):
    issues = []
    for ep in episodes:
        for check in CHECKS:
            issues += check(ep, settings, cmap)
    return issues
