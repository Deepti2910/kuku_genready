# Design notes

## Scope: one person, one step, one checkable output
- **Person:** the AI production operator who turns a locked script into generated video.
- **Step:** after the script is locked, before any generation.
- **Output:** a list of issues with fixes, and a confirmed cast map. Both can be checked by eye against the script.

## Why rules and not an LLM
Every check here is arithmetic on timestamps or a pattern in text. Rules are free, instant, give the same answer
every time, and explain themselves ("16 words in 2.4 s"). Identity is the one judgement call, so the rules only
*propose* there, with evidence, and a person confirms. An LLM could be added for the *unresolved* labels: give it
the label's lines, its shots and the loglines, and ask who it is. It would still only propose. The person in the
cast sheet stays the decision maker.

## Identity rules (cast.py)
1. **Title stripping:** LADY MIRA → MIRA, but only when MIRA is itself a speaker label. LORD ASHBY and LADY ASHBY
   share a surname but are two people. (My first version merged a pair like that.)
2. **Names vs descriptions:** a word is a *name* if the stage directions capitalise it and never write it in lower
   case ("Mira" yes; "maid" no).
3. **Descriptor siblings:** descriptor labels that share a describing word (VEILED, BEARDED) and never speak in the same
   scene are proposed as one person.
4. **Who is behind a descriptor:**
   - Hard rules: they never speak in the same scene; the gender words in the label don't clash.
   - Evidence: a *stand-in* (the logline names the character in at least 2 of the label's episodes, but the
     character never speaks by name there). This only counts for characters who are often "named but silent",
     because main characters are named in every logline. My first version suggested MAID → the heroine because of that.
   - Evidence: *co-description* (the describing word appears right next to the name, as in "Kael, still veiled").
5. Once a label is assigned, its scenes count as that character's. That stops two labels in one scene both
   becoming the same character.

**Spot check:** I compared 10 random non-identity findings with the scripts. All 10 measurements were right, and
the holes, missing shots and over-length episode were real defects. But "Stay back. I'll open it." in 1.4 s (3.6 words/s)
is fine when barked, while a *whispered* line at that speed is not. So the limits now move with the script's own tone tags.

**Result on the 50-episode input pack** (not in this repo; it is confidential): 11 merges or suggestions, all
correct, covering 19% of lines. One character with three unrelated labels (a title, a relation, a surname) was
missed. That is the reason a person confirms.

## Assumptions (where the brief was silent)
| Assumption | Value | How to make it real |
|---|---|---|
| Clear speech rate for a TTS or voice model | warn > 3.5, fail > 4.0 words/s (natural speech is ~2.5–3); −0.4 for whispered/sobbing/solemn tone tags, +0.4 for shouted/urgent ones | time 200 lines from the voice tool actually used |
| Dub expansion vs English | Hindi 1.20, Spanish/Portuguese 1.25, French 1.20, German 1.30, Indonesian 1.15 | rules of thumb; measure on Kuku's past dubs |
| Longest clip per generation | 8 s (many tools make 5–10 s) | set it to the model in use |
| Episode length | ≤ 120 s ("1 to 2-minute episodes" in the brief) | platform rule |
| Line timestamps = speaking time | yes | the scripts appear to be written that way |

## Severity
- **FAIL** (episode BLOCKED): a line above the fail rate; the same character overlapping themself; a bad timestamp.
  Generating these wastes credits for sure.
- **WARN**: likely to cost a retake (other overlaps, holes, long shots, dub fit, identity, appearance, length).
- **INFO**: auto-fixed or minor (gaps under 0.25 s are closed in the export; short episodes).

## Scale and cost
About 0.5 s for 50 episodes on a laptop, with no API cost. It runs once per script revision, so at any number of
shows a week the cost is people's time spent on the cast sheet: minutes per show, and only once (the cast map
carries over to later episodes).

## Known limits
- Speech rate counts words, not syllables, and ignores pauses written inside a line ("...").
- Appearance covers only colours of eyes, hair and beard, and only with clear phrasing. Clothes, scars and age
  aren't tracked.
- Identity can't link people whose labels share no words and whose names never appear in a logline (a title, a
  relation and a surname for one person).
- It trusts the script's own timestamps. It can't know if a scene *should* be longer.
