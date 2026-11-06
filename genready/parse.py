"""Parse timestamped microdrama screenplays (Kuku format) timestamped screenplays into a flat list of timed events."""
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

TIME_RE = re.compile(r"Start: \((\d+):(\d+(?:\.\d+)?)\) \| End: \((\d+):(\d+(?:\.\d+)?)\)")
HEADER_RE = re.compile(r"^\*\*(.+?):\*\*\s*$")
NON_TONE = {"o.s.", "v.o.", "cont'd", "o.s", "v.o", "continuing", "o.s. / continues"}


def to_sec(m, s):
    return int(m) * 60 + float(s)


def fmt(t):
    """Seconds -> 'MM:SS.cc', the same format the scripts use."""
    m, s = divmod(round(t, 2), 60)
    return f"{int(m):02d}:{s:05.2f}"


@dataclass
class Event:
    idx: int
    kind: str           # dialogue | action | camera | sfx
    start: float
    end: float
    text: str
    speaker: str = ""
    tones: list = field(default_factory=list)
    scene: int = 0

    def label(self):
        if self.kind == "dialogue":
            return f'{self.speaker}: "{self.text}"'
        return f"[{self.kind.upper()}] {self.text}"


@dataclass
class Scene:
    number: int
    heading: str
    start: float
    end: float


@dataclass
class Episode:
    number: int
    logline: str
    continuity: str
    scenes: list
    events: list
    source: str

    @property
    def duration(self):
        return max(e.end for e in self.events)

    @property
    def shots(self):
        return [e for e in self.events if e.kind == "camera"]

    @property
    def lines(self):
        return [e for e in self.events if e.kind == "dialogue"]


def _split_header(h):
    """'LADY MIRA (O.S.) (Trembling, Pleading)' -> ('LADY MIRA', ['trembling', 'pleading'])."""
    name = re.split(r"\s*\(", h, 1)[0].strip()
    tones = []
    for group in re.findall(r"\(([^)]*)\)", h):
        for t in group.split(","):
            t = t.strip().lower()
            if t and t not in NON_TONE:
                tones.append(t)
    return name, tones


def parse_episode(path):
    return parse_text(Path(path).read_text(encoding="utf-8", errors="replace"), str(path))


def parse_text(text, source=""):
    lines = text.splitlines()
    meta = {}
    for ln in lines[:10]:
        for key in ("EPISODE NUMBER", "EPISODE LOGLINE", "CONTINUITY NOTES"):
            if ln.startswith(key + ":"):
                meta[key] = ln.split(":", 1)[1].strip()
    num_match = re.search(r"(\d+)", meta.get("EPISODE NUMBER", "")) or re.search(r"episode-(\d+)", Path(source).name)
    number = int(num_match.group(1)) if num_match else 0

    scenes, events = [], []
    cur_scene = None
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if re.match(r"^SCENE \d+", ln):
            cur_scene = Scene(int(re.findall(r"\d+", ln)[0]), "", 0.0, 0.0)
            scenes.append(cur_scene)
        elif ln.startswith("Scene heading:") and cur_scene:
            cur_scene.heading = ln.split(":", 1)[1].strip()
        elif ln.startswith("Scene start:") and cur_scene:
            cur_scene.start = to_sec(*ln.split(":", 1)[1].strip().split(":"))
        elif ln.startswith("Scene end:") and cur_scene:
            cur_scene.end = to_sec(*ln.split(":", 1)[1].strip().split(":"))
        else:
            hm = HEADER_RE.match(ln)
            tm = TIME_RE.match(lines[i + 1].strip()) if hm and i + 1 < len(lines) else None
            if hm and tm:
                header = hm.group(1).strip()
                body = []
                j = i + 2
                while j < len(lines) and lines[j].strip() and not HEADER_RE.match(lines[j].strip()):
                    body.append(lines[j].strip())
                    j += 1
                content = " ".join(body).strip()
                up = header.upper()
                if up == "CAMERA":
                    kind, speaker, tones = "camera", "", []
                elif up == "ACTION":
                    kind, speaker, tones = "action", "", []
                elif up.startswith("SOUND"):
                    kind, speaker, tones = "sfx", "", []
                else:
                    kind = "dialogue"
                    speaker, tones = _split_header(header)
                    content = content.strip().strip('"').strip("“”")
                events.append(Event(
                    idx=len(events), kind=kind,
                    start=to_sec(tm.group(1), tm.group(2)), end=to_sec(tm.group(3), tm.group(4)),
                    text=content, speaker=speaker, tones=tones,
                    scene=cur_scene.number if cur_scene else 0,
                ))
                i = j
                continue
        i += 1

    events.sort(key=lambda e: (e.start, e.end))
    for k, e in enumerate(events):
        e.idx = k
    return Episode(number, meta.get("EPISODE LOGLINE", ""), meta.get("CONTINUITY NOTES", ""),
                   scenes, events, source)


def load_show(folder):
    """Load every episode-*.txt (or any .txt) under a folder, ordered by episode number."""
    paths = sorted(Path(folder).rglob("*.txt"))
    eps = [parse_episode(p) for p in paths]
    eps = [e for e in eps if e.events]
    return sorted(eps, key=lambda e: e.number)


def load_zip(fileobj):
    """Load episodes from an uploaded zip. Only .txt members are read, in memory; nothing is extracted to disk."""
    eps = []
    with zipfile.ZipFile(fileobj) as z:
        for info in z.infolist():
            name = info.filename
            if info.is_dir() or not name.lower().endswith(".txt") or "__MACOSX" in name:
                continue
            if info.file_size > 2_000_000:     # a script is ~20 KB; skip anything absurd
                continue
            ep = parse_text(z.read(info).decode("utf-8", errors="replace"), name)
            if ep.events:
                eps.append(ep)
    return sorted(eps, key=lambda e: e.number)
