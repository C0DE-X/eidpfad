#!/usr/bin/env python3
"""Generate compact original UI/combat cues, ambience and music beds."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "client" / "assets" / "audio"
RATE = 44_100


def render(name: str, duration: float, tones: list[tuple[float, float]], noise: float = 0.0, decay: float = 5.0) -> None:
    rng = random.Random(f"eidpfad:{name}")
    frames = bytearray()
    count = int(RATE * duration)
    for index in range(count):
        t = index / RATE
        envelope = math.exp(-decay * t / max(duration, 0.01))
        signal = sum(amplitude * math.sin(2 * math.pi * frequency * t) for frequency, amplitude in tones)
        signal += rng.uniform(-1, 1) * noise * (1 - t / duration)
        value = int(max(-1.0, min(1.0, signal * envelope)) * 20_000)
        frames.extend(struct.pack("<h", value))
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(frames)


def render_loop(name: str, duration: float, base: float, color: float, tension: float = 0.0) -> None:
    """Render a seamless stereo harmonic loop with independent spatial layers."""
    rng = random.Random(f"eidpfad-loop:{name}")
    count = int(RATE * duration)
    cycles = [max(1, round(base * duration * ratio)) for ratio in (1.0, 1.5, 2.0, 2.5)]
    phases = [rng.random() * math.tau for _ in cycles]
    noise_cycles = [rng.randint(3, 19) for _ in range(7)]
    frames = bytearray()
    for index in range(count):
        progress = index / count
        signal = sum(
            (0.14 / (tone_index + 1)) * math.sin(math.tau * cycle * progress + phases[tone_index])
            for tone_index, cycle in enumerate(cycles)
        )
        atmosphere = sum(
            math.sin(math.tau * cycle * progress + phases[cycle_index % len(phases)])
            for cycle_index, cycle in enumerate(noise_cycles)
        ) / len(noise_cycles)
        pulse = math.sin(math.tau * max(1, round((1.0 + tension * 2.0) * duration)) * progress)
        signal += atmosphere * color * 0.11 + pulse * tension * 0.08
        shimmer = math.sin(math.tau * cycles[-1] * progress + phases[-1]) * color * .035
        left = signal + shimmer
        right = signal - shimmer + math.sin(math.tau * noise_cycles[0] * progress) * .018
        frames.extend(struct.pack("<hh", int(max(-1.0, min(1.0, left)) * 19_000), int(max(-1.0, min(1.0, right)) * 19_000)))
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(frames)


def main() -> None:
    render("ui_click", 0.10, [(520, 0.40), (780, 0.18)], decay=9)
    render("card_play", 0.24, [(180, 0.30), (360, 0.18)], noise=0.16, decay=7)
    render("dice_roll", 0.42, [(95, 0.10), (145, 0.08)], noise=0.38, decay=5)
    render("hit", 0.28, [(74, 0.50), (148, 0.18)], noise=0.25, decay=8)
    render("block", 0.25, [(330, 0.38), (495, 0.20), (660, 0.10)], noise=0.08, decay=10)
    render("magic", 0.55, [(220, 0.20), (277, 0.18), (440, 0.12)], noise=0.05, decay=3)
    render("heal", 0.64, [(392, 0.18), (494, 0.16), (587, 0.15)], decay=2.5)
    render("loot", 0.42, [(523, 0.17), (659, 0.15), (784, 0.13)], decay=2)
    render("victory", 1.10, [(262, 0.14), (330, 0.13), (392, 0.12), (523, 0.09)], decay=1.2)
    render("defeat", 0.95, [(196, 0.17), (147, 0.14), (98, 0.12)], noise=0.04, decay=1.6)
    render("oath_gate", 0.82, [(82, 0.28), (164, 0.18), (328, 0.12)], noise=0.12, decay=2.0)
    render("anchor_break", 0.68, [(116, 0.34), (232, 0.20), (464, 0.10)], noise=0.24, decay=4.0)
    render("armor_break", 0.46, [(190, 0.26), (380, 0.22), (760, 0.12)], noise=0.22, decay=7.0)
    render("threat", 0.52, [(72, 0.24), (108, 0.18)], noise=0.10, decay=2.5)
    render("oath_power", 0.58, [(294, 0.14), (441, 0.14), (588, 0.12)], decay=2.1)
    render("ending", 1.20, [(220, 0.10), (330, 0.12), (440, 0.11), (660, 0.08)], decay=1.0)
    render("legacy", 0.84, [(392, 0.12), (523, 0.14), (784, 0.08)], decay=1.6)
    render("new_game_plus", 1.35, [(262, 0.11), (392, 0.13), (523, 0.12), (784, 0.07)], decay=0.9)
    ambience = {
        "ash": (44, .70, .28), "bone": (52, .50, .18), "coast": (58, .82, .12),
        "crystal": (74, .34, .10), "desert": (48, .64, .14), "forest": (55, .76, .08),
        "frost": (69, .30, .12), "moor": (46, .88, .16), "night": (62, .26, .10),
        "rift": (41, .54, .34), "storm": (50, .92, .32), "sunken": (43, .86, .20),
        "thorn": (57, .62, .18),
    }
    for biome, (base, color, tension) in ambience.items():
        render_loop(f"ambience_{biome}", 16.0, base, color, tension)
    render_loop("music_menu", 24.0, 55, .24, .08)
    render_loop("music_exploration", 32.0, 49, .32, .12)
    render_loop("music_combat", 24.0, 46, .38, .30)
    render_loop("music_boss", 32.0, 41, .46, .48)
    render_loop("music_finale", 36.0, 37, .52, .62)
    render_loop("music_world_echo", 28.0, 58, .30, .06)
    print(f"Generated 18 original cues, {len(ambience)} stereo ambience loops and 6 stereo music beds")


if __name__ == "__main__":
    main()
