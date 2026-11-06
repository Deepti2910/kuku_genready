"""Build the synthetic demo show "The Salt Heiress" (3 short episodes, original story).

It is written in the same script format as the real scripts and contains deliberate problems, so the
public app can show every check without using anyone's confidential scripts:

  * identity  - THE VEILED STRANGER (ep1-2) is KAEL, named only from ep3 ("Kael, still veiled");
                LADY MIRA and MIRA are the same person; THE MASKED ENVOY is a separate minor role
  * dub fit   - a line that fits in English but not in a longer dubbed language (ep2)
  * appearance - Mira's eyes are green in ep1 and hazel in ep2
  * speech rate - a 15-word line squeezed into 2.4 s (ep1), a borderline one (ep2)
  * overlap   - two characters talk over each other (ep2)
  * shots     - a 1.2 s hole with no shot (ep1), an 11 s shot (ep2), a line with no shot (ep3)
  * length    - ep2 runs past 120 s

Run:  python demo_show/make_demo.py   (rewrites the .txt files next to this script)
"""
from pathlib import Path


def fmt(t):
    m, s = divmod(round(t, 2), 60)
    return f"{int(m):02d}:{s:05.2f}"


def block(header, t0, t1, text):
    return f"**{header}:**\nStart: ({fmt(t0)}) | End: ({fmt(t1)})\n{text}\n"


def episode(num, logline, continuity, scenes):
    """scenes: list of (heading, shots); shot = (length, camera_text, [(offset, dur, header, text), ...]).
    A shot with camera_text None leaves a hole (no CAMERA block) on purpose."""
    out = [f"EPISODE NUMBER: Episode {num}", f"EPISODE LOGLINE: {logline}", f"CONTINUITY NOTES: {continuity}",
           "", "--- SCRIPT START ---", ""]
    t = 0.0
    for k, (heading, shots) in enumerate(scenes, 1):
        start = t
        body = []
        for length, cam, inner in shots:
            if cam is not None:
                body.append(block("CAMERA", t, t + length, cam))
            for off, dur, header, text in inner:
                if header in ("ACTION", "SOUND FX"):
                    body.append(block(header, t + off, t + off + dur, text))
                else:
                    body.append(block(header, t + off, t + off + dur, f'"{text}"'))
            t = round(t + length, 2)
        out += [f"SCENE {k:02d}", f"Scene heading: {heading}", f"Scene start: {fmt(start)}",
                f"Scene end: {fmt(t)}", "", "Actions and dialogue:", ""] + body
    return "\n".join(out) + "\n"


EP1 = episode(
    1,
    "On the night her father's will is read, Mira is stripped of the salt trade by a masked envoy speaking "
    "for her uncle Dorian, and a veiled stranger on the harbour wall offers her a way to take it back.",
    "Series opener.",
    [
        ("INT. HARBOUR HOUSE – COUNTING ROOM – NIGHT", [
            (4.0, "Wide shot of a candlelit counting room; ledgers stacked high, rain against the shutters.",
             [(0.5, 3.0, "ACTION", "Mira stands at her father's desk, one hand on the sealed will.")]),
            (3.5, "Close-up of Mira's green eyes reflecting the candle flame.",
             [(0.4, 2.8, "LADY MIRA (Quiet, Steady)", "Open it. I want to hear it from him.")]),
            (4.0, "Medium shot as the Masked Envoy steps out of the doorway shadow, a silver mask over his face.",
             [(0.6, 3.0, "THE MASKED ENVOY (Smooth, Cold)", "Your father is not here to read it, my lady.")]),
            (2.6, "Tight close-up on the envoy's gloved hand breaking the wax seal.",
             # deliberate: 15 words in 2.4 s
             [(0.1, 2.4, "THE MASKED ENVOY (Rapid, Mocking)",
               "By his own hand the house, the ships and every grain of salt pass to Dorian.")]),
            (3.0, "Close-up of Mira, the colour draining from her face.",
             [(0.3, 2.4, "MIRA (Stunned)", "That is not his hand.")]),
            # deliberate hole: 1.2 s with no CAMERA block
            (1.2, None, [(0.1, 0.9, "SOUND FX", "Thunder cracks over the harbour.")]),
            (4.0, "Medium two-shot: the envoy rolls the will and tucks it into his coat.",
             [(0.5, 3.0, "THE MASKED ENVOY (Final)", "Dorian expects you gone by the tide.")]),
        ]),
        ("EXT. HARBOUR WALL – NIGHT", [
            (4.5, "Wide shot of Mira walking the wet harbour wall, lanterns swinging on the masts.",
             [(1.0, 3.0, "ACTION", "A figure in a grey veil waits at the end of the wall.")]),
            (4.0, "Medium shot of the Veiled Stranger, only the eyes visible above the cloth.",
             [(0.5, 3.2, "THE VEILED STRANGER (Low, Certain)", "They forged the will. I can prove it.")]),
            (3.5, "Close-up on Mira, wary.",
             [(0.4, 2.6, "MIRA (Guarded)", "Why would a stranger help me?")]),
            (4.0, "Close-up of the stranger lowering the veil just enough to show a scarred jaw.",
             [(0.6, 3.0, "THE VEILED STRANGER (Grim)", "Because Dorian took my name too.")]),
            (3.0, "Extreme close-up of Mira's eyes narrowing.",
             [(0.3, 2.4, "MIRA (Resolved)", "Then we take it back together.")]),
            (4.0, "Wide shot as a bell rings out across the dark water.",
             [(0.5, 3.0, "SOUND FX", "The harbour bell tolls twice.")]),
        ]),
    ])

EP2 = episode(
    2,
    "Mira and the veiled stranger break into the shipping office to find the real will, but the masked envoy "
    "returns early and her uncle's men close the harbour.",
    "Picks up from Episode 1 on the harbour wall.",
    [
        ("INT. SHIPPING OFFICE – NIGHT", [
            # deliberate: 11 s shot, longer than the video model's clip limit
            (11.0, "Slow push-in across the dark shipping office as two silhouettes slip through the window.",
             [(1.0, 4.0, "ACTION", "Mira lights a shielded lantern."),
              (6.0, 3.5, "THE VEILED STRANGER (Whisper)", "The strongbox is under the map table.")]),
            (4.0, "Close-up of Mira's hazel eyes scanning the shelves.",
             [(0.5, 3.0, "MIRA (Focused)", "Hold the light lower. There.")]),
            (4.5, "Medium shot as the stranger pries the strongbox lid open.",
             [(0.4, 3.6, "THE VEILED STRANGER (Tense)", "Two wills. One with your father's true seal.")]),
            (3.5, "Insert of the two documents side by side.",
             # 3.4 words/s: fine in English, too tight once translated (dub fit)
             [(0.2, 2.9, "MIRA (Breathless)", "He kept both, the fool, he kept the real one.")]),
            (4.0, "Wide shot as the door bursts open; lantern light floods in.",
             [(0.3, 2.8, "THE MASKED ENVOY (Furious)", "Step away from that box!")]),
            (4.0, "Medium two-shot of Mira and the envoy facing each other across the table.",
             # deliberate overlap: both talk at once
             [(0.3, 2.6, "MIRA (Defiant)", "This belongs to my father."),
              (1.9, 2.0, "THE MASKED ENVOY (Shouting)", "It belongs to Dorian now!")]),
            (5.0, "Close-up of the stranger stepping between them, hand on a knife.",
             [(0.5, 3.5, "THE VEILED STRANGER (Dangerous)", "Say his name once more and I will end this here.")]),
        ]),
        ("EXT. HARBOUR – DAWN", [
            (6.0, "Wide shot of chains rising across the harbour mouth; guards on every pier.",
             [(0.5, 4.0, "ACTION", "Dorian's men close the harbour.")]),
            (5.0, "Medium shot of Mira clutching the true will to her chest.",
             [(0.8, 3.4, "MIRA (Determined)", "Then we leave by the old salt road.")]),
            (5.0, "Close-up of the stranger looking back at the burning office.",
             [(1.0, 3.0, "THE VEILED STRANGER (Quiet)", "He will follow.")]),
        ]),
        ("EXT. SALT ROAD – MORNING", [
            (8.0, "Drone shot over white salt flats, two riders small against the glare.",
             [(1.0, 5.0, "ACTION", "Mira and the stranger ride hard toward the hills.")]),
            (6.0, "Medium tracking shot of the riders side by side.",
             [(0.5, 3.5, "MIRA (Curious)", "You never told me your name.")]),
            (6.0, "Close-up of the stranger, eyes on the horizon.",
             [(1.0, 3.0, "THE VEILED STRANGER (Guarded)", "When we reach the hills.")]),
            (8.0, "Wide shot of the horizon; a dust cloud rises behind them.",
             [(1.0, 4.0, "SOUND FX", "Distant hoofbeats, many of them.")]),
            (7.0, "Close-up of Mira glancing back over her shoulder.",
             [(1.0, 3.0, "MIRA (Alarmed)", "Riders. Dozens of them.")]),
            (8.0, "Wide shot of the riders spurring their horses up a rocky slope.",
             [(1.0, 5.0, "ACTION", "They race for the narrow pass.")]),
            (8.0, "Medium shot at the mouth of the pass, the stranger reining in.",
             [(1.0, 3.5, "THE VEILED STRANGER (Commanding)", "Go through. I will hold them.")]),
            (8.0, "Close-up of Mira refusing to move.",
             [(1.0, 3.0, "MIRA (Fierce)", "No. Not without you.")]),
            (8.0, "Wide shot as arrows strike the rocks around them.",
             [(0.5, 4.0, "SOUND FX", "Arrows clatter on stone.")]),
            (7.0, "Extreme close-up of the veil torn away by the wind.",
             [(1.0, 4.0, "ACTION", "The stranger's face is hidden from us by the glare.")]),
        ]),
    ])

EP3 = episode(
    3,
    "In the hill fort, the stranger is revealed as Kael, the heir Dorian left for dead, and Dorian himself "
    "arrives to bargain for the true will.",
    "Picks up after the chase through the pass in Episode 2.",
    [
        ("INT. HILL FORT – DAY", [
            (4.0, "Wide shot of a ruined hill fort; sunlight through a broken roof.",
             [(0.5, 3.0, "ACTION", "Mira binds a cut on the stranger's arm.")]),
            (4.0, "Close-up of Kael, still veiled, as he finally pulls the cloth away.",
             [(0.5, 3.0, "KAEL (Steady)", "My name is Kael. Dorian is my brother.")]),
            (3.5, "Close-up of Mira, stunned.",
             [(0.3, 2.7, "MIRA (Shocked)", "The heir they buried at sea.")]),
            (4.0, "Medium shot of Kael nodding slowly, the veiled hood now around his shoulders.",
             [(0.5, 3.0, "KAEL (Bitter)", "He paid the sea to keep me.")]),
            (4.5, "Wide shot of the fort gate as a lone rider approaches under a white flag.",
             [(0.5, 3.5, "ACTION", "Dorian dismounts, unarmed.")]),
            (4.0, "Medium shot of Dorian at the gate, smiling.",
             [(0.5, 3.2, "DORIAN (Charming)", "Brother. You look well for a dead man.")]),
            (3.5, "Close-up of Kael's jaw tightening, the scar the veiled cloth used to hide now plain.",
             [(0.4, 2.8, "KAEL (Cold)", "Say what you came to say.")]),
        ]),
        ("INT. HILL FORT – CONTINUOUS", [
            (4.0, "Two-shot of Dorian and Mira across a stone table.",
             [(0.5, 3.0, "DORIAN (Smooth)", "Give me the will and you both live.")]),
            # deliberate: a line placed after the last shot ends (no shot covers it)
            (3.0, "Close-up of Mira sliding the will toward herself, not him.",
             [(3.3, 2.4, "MIRA (Defiant)", "I would rather burn it.")]),
        ]),
    ])

if __name__ == "__main__":
    here = Path(__file__).parent
    for n, text in ((1, EP1), (2, EP2), (3, EP3)):
        (here / f"episode-00{n}-The Salt Heiress.txt").write_text(text, encoding="utf-8")
    print("wrote 3 episodes to", here)
