from __future__ import annotations

import hashlib
import random


MAX_DICE = 8


def roll_d12(seed: int, roll_index: int, count: int, threshold: int, critical_min: int = 12) -> dict[str, object]:
    material = f"{seed}:{roll_index}".encode("utf-8")
    deterministic_seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    rng = random.Random(deterministic_seed)
    values = [rng.randint(1, 12) for _ in range(min(MAX_DICE, max(0, count)))]
    threshold = min(12, max(2, threshold))
    critical_min = min(12, max(threshold, critical_min))
    criticals = sum(value >= critical_min for value in values)
    return {
        "values": values,
        "threshold": threshold,
        "successes": sum(value >= threshold for value in values) + criticals,
        "criticals": criticals,
    }
