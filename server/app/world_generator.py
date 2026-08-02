from __future__ import annotations

import random
from typing import Any

from .content import EnemyCatalog


CAMPAIGN_COUNTRY_COUNTS = {"expedition": 6, "fieldzug": 9, "saga": 13}

# Hand-built countries stay recognizable while the seed changes order, routes,
# scenario modules, weather, enemy lineups and rewards.
COUNTRIES = [
    ("nebelmark", "Nebelmark", "moor", ["Moorpfad", "Grauwald", "Krähenfurt"]),
    ("sonnenbruch", "Sonnenbruch", "desert", ["Salzstraße", "Goldene Senke", "Scherbenpass"]),
    ("frostreiche", "Frostreiche", "frost", ["Eisgrat", "Weißgrab", "Runental"]),
    ("splitterinseln", "Zersplitterte Inseln", "coast", ["Sturmkliff", "Wrackbucht", "Flutsteg"]),
    ("aschenlande", "Aschenlande", "ash", ["Glutebene", "Schwarztor", "Rauchhain"]),
    ("dornwall", "Dornwall", "thorn", ["Hexenstieg", "Rosenbruch", "Wolfsschlucht"]),
    ("glassteppe", "Glassteppe", "crystal", ["Spiegeldünen", "Singender Stein", "Sonnengrab"]),
    ("tiefenwald", "Tiefenwald", "forest", ["Wurzelgrund", "Hirschhain", "Alte Jagd"]),
    ("kupferkueste", "Kupferküste", "coast", ["Leuchtturmriff", "Schmugglerweg", "Erzhafen"]),
    ("knochental", "Knochental", "bone", ["Riesengrab", "Bleicher Fluss", "Totenfeld"]),
    ("nachtkrone", "Nachtkrone", "night", ["Sternwarte", "Mondpass", "Rabenturm"]),
    ("sturmmarsch", "Sturmmarsch", "storm", ["Donnerheide", "Windbruch", "Himmelsgrat"]),
    ("versunkener_bund", "Versunkener Bund", "sunken", ["Algenhof", "Glockentiefe", "Nebelsteg"]),
    ("weltennaht", "Weltennaht", "rift", ["Eidtor", "Zerrissene Bastion", "Namenloser Thron"]),
]

SCENARIOS = [
    ("ambush", "Hinterhalt am {area}", "Gegner beginnen und erhalten im ersten Angriff +1 W12."),
    ("raid", "Überfall im {area}", "Drei Gegnerwellen mit steigendem Druck."),
    ("village", "Befreiung von {area}", "Schützt Dorfbewohner während des Kampfes."),
    ("caravan", "Karawane durch {area}", "Die Karawane muss bis zum letzten Zug bestehen."),
    ("hunt", "Monsterjagd: {area}", "Vorbereitungskarten erhalten in Runde eins einen Bonus."),
    ("ruin", "Die verfluchte Ruine von {area}", "Bessere Beute, aber zusätzliche Fluchgefahr."),
]

WEATHER = {
    "moor": ("Nebel", "Säureregen"), "desert": ("Sandsturm", "Flimmerhitze"),
    "frost": ("Schneefall", "Eiswind"), "coast": ("Sturmflut", "Salznebel"),
    "ash": ("Ascheregen", "Glutwind"), "thorn": ("Rankenwuchs", "Giftpollen"),
    "crystal": ("Prismenlicht", "Scherbenwind"), "forest": ("Dämmerregen", "Wurzelbeben"),
    "bone": ("Bleicher Wind", "Seelenfrost"), "night": ("Mondfinsternis", "Sternenfall"),
    "storm": ("Gewitter", "Orkan"), "sunken": ("Schwarze Flut", "Glockennebel"),
    "rift": ("Nahtbruch", "Zeitsturm"),
}

SCENARIO_PROPS = {
    "ambush": ("barricade", "campfire"),
    "raid": ("watchtower", "barrel"),
    "village": ("market_stall", "barrel"),
    "caravan": ("caravan", "bridge"),
    "hunt": ("tree", "shrine"),
    "ruin": ("ruin_arch", "chest"),
    "country_boss": ("shrine", "oath_stone"),
    "final_boss": ("oath_stone", "ruin_arch"),
}


def generate_world(
    seed: int,
    campaign_length: str = "fieldzug",
    world_tier: int = 1,
    enemies: EnemyCatalog | None = None,
) -> dict[str, Any]:
    if campaign_length not in CAMPAIGN_COUNTRY_COUNTS:
        raise ValueError(f"Unknown campaign length: {campaign_length}")
    if world_tier < 1:
        raise ValueError("world_tier must be positive")

    enemy_catalog = enemies or EnemyCatalog()
    rng = random.Random(f"eidpfad-world:{seed}:{world_tier}")
    country_count = CAMPAIGN_COUNTRY_COUNTS[campaign_length]
    ordinary = list(COUNTRIES[:-1])
    rng.shuffle(ordinary)
    selected = ordinary[: country_count - 1] + [COUNTRIES[-1]]

    countries: list[dict[str, Any]] = []
    route: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    previous_kind = ""

    for country_index, (country_id, country_name, biome, areas) in enumerate(selected):
        shuffled_areas = list(areas)
        rng.shuffle(shuffled_areas)
        regional = enemy_catalog.for_country(country_id, bosses=False)
        bosses = enemy_catalog.for_country(country_id, bosses=True)
        rng.shuffle(regional)
        rng.shuffle(bosses)
        elite = next((enemy for enemy in regional if enemy.get("elite")), regional[-1])
        ordinary_enemies = [enemy for enemy in regional if enemy["id"] != elite["id"]]
        encounter_sets = [
            [entry["id"] for entry in ordinary_enemies[0:2]],
            [entry["id"] for entry in ordinary_enemies[2:5]],
            [elite["id"], bosses[0]["id"]],
        ]
        nodes: list[dict[str, Any]] = []

        for local_index in range(3):
            is_final = country_id == "weltennaht" and local_index == 2
            is_boss = local_index == 2
            if is_final:
                kind, title, special_rule = "final_boss", "Die Krone ohne Namen", "Vier Bossphasen an der Weltennaht."
            elif country_id == "weltennaht" and local_index == 0:
                kind, title, special_rule = "raid", "Das Eidtor", "Durchbrecht das Tor und seine beiden definierten Waechter."
            elif country_id == "weltennaht" and local_index == 1:
                kind, title, special_rule = "country_boss", "Die zerrissene Bastion", "Zerstoert drei Eidanker, bevor die Naht kollabiert."
            elif is_boss:
                kind, title, special_rule = "country_boss", f"{bosses[0]['name']} von {country_name}", "Elite und Länderboss ohne Erholung dazwischen."
            else:
                choices = [entry for entry in SCENARIOS if entry[0] != previous_kind]
                kind, title_template, special_rule = rng.choice(choices)
                title = title_template.format(area=shuffled_areas[local_index])
            previous_kind = kind
            route_index = len(route)
            node = {
                "id": f"{country_id}-{local_index + 1}", "index": route_index,
                "country_id": country_id, "country": country_name, "area": shuffled_areas[local_index],
                "biome": biome, "weather": rng.choice(WEATHER[biome]), "kind": kind, "title": title,
                "special_rule": special_rule, "difficulty": country_index + world_tier,
                "is_boss": is_boss, "is_final": is_final, "encounters": encounter_sets[local_index],
                "art": f"res://assets/countries/{country_id}.svg",
                "background": f"res://assets/backgrounds/{biome}.png",
                "landmark_model": f"res://assets/models/countries/{country_id}.glb",
                "prop_models": [f"res://assets/models/props/{name}.glb" for name in SCENARIO_PROPS[kind]],
            }
            if not is_boss and country_id != "weltennaht":
                alternate_choices = [entry for entry in SCENARIOS if entry[0] not in {kind, previous_kind}]
                alternate_kind, alternate_title, alternate_rule = rng.choice(alternate_choices)
                alternate = {
                    **node,
                    "id": f"{country_id}-{local_index + 1}-alternative",
                    "kind": alternate_kind,
                    "title": alternate_title.format(area=shuffled_areas[(local_index + 1) % len(shuffled_areas)]),
                    "special_rule": alternate_rule,
                    "prop_models": [
                        f"res://assets/models/props/{name}.glb"
                        for name in SCENARIO_PROPS[alternate_kind]
                    ],
                }
                node["alternatives"] = [alternate]
            else:
                node["alternatives"] = []
            nodes.append(node)
            route.append(node)

        countries.append({
            "id": country_id, "name": country_name, "biome": biome, "weather": list(WEATHER[biome]),
            "art": f"res://assets/countries/{country_id}.svg", "nodes": nodes,
            "landmark_model": f"res://assets/models/countries/{country_id}.glb",
        })

    for index, node in enumerate(route[:-1]):
        destinations = [route[index + 1], *route[index + 1].get("alternatives", [])]
        for source in [node, *node.get("alternatives", [])]:
            edges.extend({"from": source["id"], "to": destination["id"]} for destination in destinations)

    return {
        "seed": seed, "campaign_length": campaign_length, "world_tier": world_tier,
        "countries": countries, "route": route, "edges": edges,
    }
