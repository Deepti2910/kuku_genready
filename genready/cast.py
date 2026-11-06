"""Who is who: turn raw speaker labels into a cast sheet a person can confirm.

AI video and voice tools generate per character: one face reference, one voice. A script that calls the
same person "LADY MIRA" in one episode and "MIRA" in the next, or "THE VEILED STRANGER" until the
reveal and "KAEL" after it, gets two faces and two voices unless someone maps the labels first.

Rules here only *propose* a mapping. A person confirms it in the app (or edits cast_map.json).
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

HONORIFICS = {"LADY", "LORD", "SIR", "DAME", "MISS", "MR", "MRS", "MS", "DR", "MADAM", "MASTER",
              "DUKE", "DUCHESS", "KING", "QUEEN", "PRINCE", "PRINCESS", "COUNT", "COUNTESS",
              "CAPTAIN", "FATHER", "SISTER", "BROTHER", "NOBLE", "THE", "OLD", "YOUNG", "DOWAGER"}
FEMALE = {"LADY", "WOMAN", "MOTHER", "MATRIARCH", "DUCHESS", "NOBLEWOMAN", "MAID", "HOUSEKEEPER", "GOWN",
          "QUEEN", "PRINCESS", "SISTER", "WIFE", "BRIDE", "WIDOW", "GIRL", "MISS", "MRS", "DAUGHTER",
          "COUNTESS", "AUNT", "DAME", "MADAM", "STEPMOTHER", "GRANDMOTHER", "NUN"}
MALE = {"MAN", "LORD", "NOBLEMAN", "GROOM", "FATHER", "DUKE", "KING", "PRINCE", "SIR", "MR", "BROTHER",
        "HUSBAND", "SON", "BOY", "BUTLER", "FOOTMAN", "COUNT", "UNCLE", "PRIEST", "MONK", "GENTLEMAN",
        "STEPFATHER", "GRANDFATHER", "TOWNSMAN", "BRIDEGROOM"}
# Words that describe a role or look, not who the person is. Ignored when matching descriptors to names.
GENERIC = {"THE", "A", "AN", "IN", "WITH", "OF", "MAN", "WOMAN", "LADY", "LORD", "NOBLE", "MYSTERIOUS",
           "FORMER", "OLD", "YOUNG", "ELDER", "TALL", "THIRD", "STRANGER", "VOICE", "OFF-SCREEN",
           "ROYAL", "CROWN", "HIGH", "POLICE", "LOYALIST", "ARISTOCRATIC", "PEASANT", "FIRST", "SECOND",
           # job nouns: many different people share them
           "THUG", "GUARD", "SENTRY", "CONSTABLE", "OFFICIAL", "FIGHTER", "SCOUT", "DRIVER", "VILLAGER",
           "JUDGE", "INFORMANT", "SERVANT", "SOLDIER", "OFFICER", "CART", "WITH"}
FEMALE_PRON = re.compile(r"\b(she|her|hers|herself)\b", re.I)
MALE_PRON = re.compile(r"\b(he|him|his|himself)\b", re.I)


@dataclass
class Label:
    label: str
    lines: int = 0
    episodes: list = field(default_factory=list)
    kind: str = ""              # named | descriptor | role
    core: str = ""              # label without honorifics, e.g. LADY MIRA -> MIRA
    char: str = ""              # character id: core if that is itself a speaker label, else the label
    gender: str = ""            # f | m | "" from the label's own words


@dataclass
class CastRow:
    label: str
    character: str              # proposed (later: confirmed) character id
    kind: str
    lines: int
    episodes: str
    reason: str
    confidence: str             # auto | suggested | unresolved | self
    alternatives: str = ""


def _words(label):
    return re.findall(r"[A-Z][A-Z'\-]*", label.upper())


def _label_gender(words):
    f, m = len(set(words) & FEMALE), len(set(words) & MALE)
    return "f" if f > m else "m" if m > f else ""


def _narrative(episodes):
    """All non-dialogue text: what a generation prompt is built from."""
    for ep in episodes:
        yield ep.number, ep.logline
        yield ep.number, ep.continuity
        for e in ep.events:
            if e.kind != "dialogue":
                yield ep.number, e.text


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?;])\s+", text or "") if s]


def proper_names(episodes):
    """Single words that are used as names: capitalised in narrative text and never written in lower case.
    'Mira' qualifies; 'maid' ('the maid') and 'nobleman' do not."""
    caps, lower = Counter(), Counter()
    for _, text in _narrative(episodes):
        for w in re.findall(r"\b[A-Za-z][a-z]+\b", text):
            (caps if w[0].isupper() else lower)[w.upper()] += 1
    return {w for w, n in caps.items() if n >= 2 and lower[w] == 0}


def collect_labels(episodes):
    labels = {}
    for ep in episodes:
        for ln in ep.lines:
            lab = labels.setdefault(ln.speaker, Label(ln.speaker))
            lab.lines += 1
            if ep.number not in lab.episodes:
                lab.episodes.append(ep.number)
    names = proper_names(episodes)
    for lab in labels.values():
        words = _words(lab.label)
        core_words = [w for w in words if w not in HONORIFICS] or words
        lab.core = " ".join(core_words)
        lab.gender = _label_gender(words)
        if "'S" in lab.label.upper() or "’S" in lab.label.upper():
            lab.kind = "descriptor"          # KAEL'S MOTHER: relation, not a name
        elif len(core_words) == 1 and core_words[0] in names:
            lab.kind = "named"
        elif len(words) >= 2 and all(w in HONORIFICS or w in names for w in words) and core_words[0] in names \
                and core_words[0] not in HONORIFICS:
            lab.kind = "named"               # LORD ASHBY
        elif len(words) == 1:
            lab.kind = "role"                # MAID, JUDGE, LORD
        else:
            lab.kind = "descriptor"          # THE VEILED STRANGER, LADY IN RED GOWN
    for lab in labels.values():
        lab.char = lab.core if lab.core in labels else lab.label
    return labels


def character_genders(episodes, char_names):
    """Guess each named character's gender from sentences that mention only them plus a pronoun."""
    score = defaultdict(lambda: [0, 0])
    pats = {c: re.compile(rf"\b{re.escape(c)}\b", re.I) for c in char_names}
    for _, text in _narrative(episodes):
        for s in _sentences(text):
            hit = [c for c, p in pats.items() if p.search(s)]
            if len(hit) == 1:
                score[hit[0]][0] += len(FEMALE_PRON.findall(s))
                score[hit[0]][1] += len(MALE_PRON.findall(s))
    out = {}
    for c, (f, m) in score.items():
        if f + m >= 3 and max(f, m) >= 2 * min(f, m):
            out[c] = "f" if f > m else "m"
    return out


def _distinct(label):
    """Words that describe *this* person (BEARDED, BLOND, GOWN), not a generic role or title."""
    return [w for w in _words(label)
            if w not in GENERIC and w not in FEMALE and w not in MALE and len(w) > 2 and "'" not in w]


def _speaking_scenes(episodes, labels):
    """character core -> set of (episode, scene) where it speaks under any of its labels."""
    out = defaultdict(set)
    for ep in episodes:
        for ln in ep.lines:
            out[labels[ln.speaker].char].add((ep.number, ln.scene))
    return out


def silent_rates(episodes, candidates, scenes):
    """Share of the episodes whose logline names a character in which that character never speaks by name.
    A high rate is the signature of an alias: the story is about them, but the script calls them something else."""
    out = {}
    for c in candidates:
        pat = re.compile(rf"\b{re.escape(c)}\b", re.I)
        named = [e.number for e in episodes if pat.search(f"{e.logline} {e.continuity}")]
        spoke = {n for n, _ in scenes.get(c, ())}
        if named:
            out[c] = sum(n not in spoke for n in named) / len(named)
    return out


def suggest(lab, episodes, candidates, genders, labels, scenes, silent_rate):
    """Rank characters who could be the person behind a descriptor label.

    Hard rules (a candidate is dropped):
      * they speak in the same scene as the label: two voices in one scene are two people;
      * their gender contradicts the label's words (LADY IN RED GOWN cannot be Kael).
    Evidence (summed):
      * stand-in: in at least 2, and at least half, of the episodes where the label speaks, the logline or
        continuity note names the candidate, yet the candidate never speaks by name there (+3 per episode);
      * co-description: a distinctive word of the label (BEARDED, BLOND, GOWN...) is used right next to
        the candidate's name ("Kael, still veiled"), anywhere in the show (+1 each, max 6).
    """
    eps = {e.number: e for e in episodes}
    pats = {c: re.compile(rf"\b{re.escape(c)}\b", re.I) for c in candidates}
    distinct = _distinct(lab.label)
    mine = scenes[lab.char]
    score, why = Counter(), defaultdict(list)

    for c in candidates:
        if c == lab.char or mine & scenes.get(c, set()):
            continue
        if lab.gender and genders.get(c) and genders[c] != lab.gender:
            continue
        hits = [n for n in lab.episodes
                if not any(e == n for e, _ in scenes.get(c, ()))
                and pats[c].search(f"{eps[n].logline} {eps[n].continuity}")]
        if (len(hits) >= 2 and len(hits) >= 0.5 * len(lab.episodes)
                and silent_rate.get(c, 0) >= 0.5):
            score[c] += 3 * len(hits)
            why[c].append(f"named in the logline of ep{', ep'.join(map(str, hits[:4]))} "
                          f"({len(hits)}/{len(lab.episodes)} of its episodes) but never speaks by name there")
        co = 0
        if distinct:
            near = re.compile(rf"\b{re.escape(c)}\b(?:\W+\w+){{0,6}}?\W+(?:{'|'.join(distinct)})\b"
                              rf"|\b(?:{'|'.join(distinct)})\W+(?:\w+\W+){{0,2}}{re.escape(c)}\b", re.I)
            co = sum(len(near.findall(text or "")) for _, text in _narrative(episodes))
        if co >= 3:
            score[c] += min(co, 6)
            why[c].append(f"{co} sentence(s) describe {c.title()} as {'/'.join(w.lower() for w in distinct)}")
    return [(c, sc, why[c]) for c, sc in score.most_common()]


def _sibling_groups(labels, scenes):
    """Descriptor labels that share a describing word and never speak in the same scene are probably one
    person seen before the reveal: THE VEILED STRANGER / VEILED RIDER / SCARRED VEILED MAN."""
    desc = [l for l in labels.values() if l.kind == "descriptor" and l.char == l.label]
    parent = {l.label: l.label for l in desc}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for i, a in enumerate(desc):
        for b in desc[i + 1:]:
            shared = set(_distinct(a.label)) & set(_distinct(b.label))
            if shared and not (scenes[a.char] & scenes[b.char]) and (not a.gender or not b.gender or a.gender == b.gender):
                parent[find(b.label)] = find(a.label)
    groups = defaultdict(list)
    for l in desc:
        groups[find(l.label)].append(l)
    return {l.label: g for g in groups.values() for l in g}


def build_cast(episodes):
    """Return proposed cast rows, one per speaker label, most lines first."""
    labels = collect_labels(episodes)
    candidates = sorted({l.char for l in labels.values() if l.kind == "named"})
    genders = character_genders(episodes, candidates)
    scenes = _speaking_scenes(episodes, labels)
    siblings = _sibling_groups(labels, scenes)
    silent = silent_rates(episodes, candidates, scenes)
    ranked_by = {}
    rows = []
    for lab in sorted(labels.values(), key=lambda l: -l.lines):
        eps = _ep_range(lab.episodes)
        if lab.kind == "named":
            # LADY MIRA -> MIRA only when MIRA is itself a speaker label; LORD and LADY ASHBY
            # share a surname but are two people, so they keep their full labels.
            if lab.core != lab.label and lab.core in labels:
                rows.append(CastRow(lab.label, lab.core, lab.kind, lab.lines, eps,
                                    f"same name with a title ({lab.label} = {lab.core})", "auto"))
            else:
                rows.append(CastRow(lab.label, lab.label, lab.kind, lab.lines, eps, "name", "self"))
            continue
        if lab.char != lab.label:
            rows.append(CastRow(lab.label, lab.char, lab.kind, lab.lines, eps,
                                f"same role with a title ({lab.label} = {lab.core})", "auto"))
            continue
        group = siblings.get(lab.label, [lab]) if lab.kind == "descriptor" else []
        # pool evidence across the group so the reveal name found for one alias applies to all
        pooled, why = Counter(), defaultdict(list)
        for g in group:
            if g.label not in ranked_by:
                ranked_by[g.label] = suggest(g, episodes, candidates, genders, labels, scenes, silent)
            for c, sc, w in ranked_by[g.label]:
                pooled[c] += sc
                why[c] += w
        ranked = pooled.most_common()
        others = [g.label for g in group if g.label != lab.label]
        same = f"same person as {', '.join(others)} (shared description, never in a scene together)" if others else ""
        top = ranked[0] if ranked else None
        alts = ", ".join(c for c, _ in ranked[1:3])
        if top and top[1] >= 3 and (len(ranked) == 1 or top[1] >= 1.5 * ranked[1][1]):
            reason = f"probably {top[0].title()}: " + "; ".join(dict.fromkeys(why[top[0]]))
            scenes[top[0]] |= scenes[lab.char]     # now they speak there: a later label can't also be them
            rows.append(CastRow(lab.label, top[0], lab.kind, lab.lines, eps,
                                reason + (f"; {same}" if same else ""), "suggested", alts))
        elif others:
            lead = max(group, key=lambda g: g.lines).label
            rows.append(CastRow(lab.label, lead, lab.kind, lab.lines, eps, f"probably {same}", "suggested", alts))
        elif top and top[1] >= 6:
            rows.append(CastRow(lab.label, lab.label, lab.kind, lab.lines, eps,
                                "unresolved: could be " + " or ".join(c.title() for c, _ in ranked[:2]),
                                "unresolved", alts))
        elif lab.lines >= 10:
            rows.append(CastRow(lab.label, lab.label, lab.kind, lab.lines, eps,
                                f"unnamed {'role' if lab.kind == 'role' else 'label'} with {lab.lines} lines: "
                                "one recurring person, or several?", "unresolved"))
        else:
            rows.append(CastRow(lab.label, lab.label, lab.kind, lab.lines, eps, "minor role", "self"))
    return rows


def _ep_range(nums):
    nums = sorted(nums)
    if not nums:
        return ""
    if len(nums) <= 3:
        return ", ".join(map(str, nums))
    return f"{nums[0]}–{nums[-1]} ({len(nums)} eps)"


def cast_map(rows):
    """label -> character, from (possibly edited) rows or dicts."""
    out = {}
    for r in rows:
        d = r if isinstance(r, dict) else r.__dict__
        out[d["label"]] = (d.get("character") or d["label"]).strip().upper()
    return out


# ---------- appearance continuity ----------

COLOURS = {"blue", "green", "grey", "gray", "brown", "hazel", "amber", "black", "dark", "blonde", "blond",
           "golden", "auburn", "red", "silver", "white", "chestnut", "raven", "copper", "honey", "ginger",
           "fair", "light", "pale", "violet", "emerald", "sapphire", "ice-blue", "steel", "jet", "ash",
           "platinum", "strawberry", "sandy", "greying", "graying", "crimson", "ebony"}
FEATURES = {"eyes": "eyes", "eye": "eyes", "hair": "hair", "beard": "beard", "curls": "hair",
            "locks": "hair", "braid": "hair", "braids": "hair"}


def _colour_of(phrase):
    words = re.findall(r"[a-z]+(?:-[a-z]+)?", phrase.lower())
    keep = []
    for w in words:
        parts = w.split("-")
        if all(p in COLOURS for p in parts):
            keep.append(w.replace("gray", "grey"))
    return " ".join(keep)


RELATION = re.compile(r"\b(mother|father|sister|brother|son|daughter|wife|husband|maid|guard|men|man|woman)\b", re.I)
FEATURE_RE = re.compile(rf"((?:[\w\-]+[\s,]+){{0,3}})({'|'.join(FEATURES)})\b", re.I)


def appearance(episodes, cmap):
    """Colour descriptions of eyes / hair / beard, tied to a character, per episode.

    Who it belongs to, in order: a possessive right before it ("Mira's green eyes"); else the only
    character named in that sentence ("Mira ... with braided auburn hair"); else, for "his/her ...",
    the only character named in the previous stage direction (the shot before). Ambiguous ones are skipped.
    Returns list of dicts: character, feature, value, episode, evidence.
    """
    forms = {}
    for label, char in cmap.items():
        words = [w for w in _words(label) if w not in {"THE", "A", "AN"}]
        for f in {" ".join(words), char}:
            if f:
                forms[f] = char
    alt = "|".join(sorted((re.escape(f) for f in forms), key=len, reverse=True))
    who_re = re.compile(rf"\b({alt})\b(['’]s)?", re.I)
    found = []
    for ep in episodes:
        last = None
        for e in ep.events:
            if e.kind == "dialogue":
                continue
            for snt in _sentences(e.text):
                chars = {forms[m.group(1).upper()] for m in who_re.finditer(snt)}
                for fm in FEATURE_RE.finditer(snt):
                    col = _colour_of(fm.group(1))
                    if not col:
                        continue
                    before = snt[:fm.start(2)]
                    poss = [m for m in who_re.finditer(before) if m.group(2)]
                    if poss and not RELATION.search(before[poss[-1].end():]):
                        owner = forms[poss[-1].group(1).upper()]
                    elif poss:
                        continue                       # "Kael's mother ... silver hair"
                    elif len(chars) == 1:
                        owner = next(iter(chars))
                    elif not chars and last and re.search(r"\b(his|her)\b", before, re.I):
                        owner = last
                    else:
                        continue
                    found.append({"character": owner, "feature": FEATURES[fm.group(2).lower()],
                                  "value": col, "episode": ep.number, "evidence": snt.strip()[:160]})
            named = {forms[m.group(1).upper()] for m in who_re.finditer(e.text)}
            last = next(iter(named)) if len(named) == 1 else (None if named else last)
    return found


def appearance_conflicts(found):
    """Same character + feature described with different colours in different places."""
    by = defaultdict(lambda: defaultdict(list))
    for f in found:
        by[(f["character"], f["feature"])][f["value"]].append(f)
    out = []
    for (char, feat), vals in by.items():
        # 'dark' alone is a lighting word as often as a colour; only compare real colour names
        real = {v: fs for v, fs in vals.items() if v not in {"dark", "light", "pale", "fair"}
                and not (feat == "eyes" and v == "red")}          # red eyes = crying, not a colour
        # 'blue' is compatible with 'blue-grey'; only clash when neither contains the other
        parts = {v: set(v.replace("-", " ").split()) for v in real}
        clash = [(a, b) for a in real for b in real if a < b and not (parts[a] <= parts[b] or parts[b] <= parts[a])]
        if clash:
            out.append({"character": char, "feature": feat,
                        "values": {v: sorted({f["episode"] for f in fs}) for v, fs in real.items()},
                        "evidence": [fs[0]["evidence"] for fs in real.values()]})
    return out
