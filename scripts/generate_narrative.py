#!/usr/bin/env python3
"""Generate the complete German narrative, subtitle and cinematic manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared" / "narrative"
ASSETS = ROOT / "client" / "assets"
CLIENT_NARRATIVE = ASSETS / "narrative"

COUNTRIES = [
    ("nebelmark", "Nebelmark", "Im Moor tragen selbst die Toten noch ihre Eide."),
    ("sonnenbruch", "Sonnenbruch", "Unter dem weißen Himmel wird jedes Versprechen zu Salz."),
    ("frostreiche", "Frostreiche", "Das Eis bewahrt Namen, die kein Lebender mehr aussprechen darf."),
    ("splitterinseln", "Zersplitterte Inseln", "Die Flut gibt heute zurück, was sie gestern verschlang."),
    ("aschenlande", "Aschenlande", "Unter der Asche glimmt ein Krieg, der nie endete."),
    ("dornwall", "Dornwall", "Jede Blüte hier kennt den Geschmack von Blut."),
    ("glassteppe", "Glassteppe", "Die Steppe zeigt dir nicht dein Gesicht, sondern deine Schuld."),
    ("tiefenwald", "Tiefenwald", "Die ältesten Wurzeln erinnern sich an die erste Krone."),
    ("kupferkueste", "Kupferküste", "Zwischen Erz und Gischt wird jeder Handel mit einem Eid besiegelt."),
    ("knochental", "Knochental", "Die Riesen liegen still, doch ihre Träume wandern."),
    ("nachtkrone", "Nachtkrone", "Hier wird das Sternenlicht von einem bleichen Hof bewacht."),
    ("sturmmarsch", "Sturmmarsch", "Der Donner spricht schneller als jedes Urteil."),
    ("versunkener_bund", "Versunkener Bund", "Unter schwarzem Wasser läuten Glocken für Namenlose."),
    ("weltennaht", "Weltennaht", "Alle Wege enden dort, wo die Welt zusammengenäht wurde."),
]

SCENARIOS = [
    ("ambush", "Hinterhalt", "Der Weg ist zu still. Sie warten bereits zwischen den Steinen."),
    ("raid", "Überfall", "Mehrere Wellen rücken nach. Haltet eure stärksten Karten zurück."),
    ("village", "Dorfbefreiung", "Die Bewohner sind eingeschlossen. Unser Sieg zählt nur, wenn sie leben."),
    ("caravan", "Karawanenschutz", "Die Wagen dürfen nicht fallen. Wir kämpfen in Bewegung."),
    ("hunt", "Monsterjagd", "Lest die Spuren, bereitet Fallen vor und gebt der Bestie keinen zweiten Angriff."),
    ("ruin", "Verfluchte Ruine", "Die Beute ist echt. Der Fluch leider auch."),
]

ROLES = ("skirmisher", "brute", "defender", "hexer", "marksman", "assassin", "beast", "controller", "elite", "boss")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_lines() -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    plot_texts = [
        "Vardra wurde nicht erschaffen. Es wurde zusammengebunden.",
        "Sieben Herrscher gaben ihre Namen, damit die Länder nicht im Nichts versanken.",
        "Aus ihren Straßen wurden Eidpfade, aus ihren Erinnerungen Wegsteine.",
        "Doch jeder gebrochene Eid lockert eine Naht der Welt.",
        "Unser Auftrag klang einfach: einen Kartografen und seine Reliquie über die Grenze bringen.",
        "Dann kam der Hinterhalt, und mit ihm das Ende des Grauen Eids, wie wir ihn kannten.",
        "Die Reliquie zerbrach und brannte ihr Zeichen in die Hand ihres letzten Trägers.",
        "Seit dieser Nacht öffnet sich jeder Eidpfad nur noch für dieses Zeichen.",
        "Hier marschieren keine Erwählten, sondern Söldner mit einem unbezahlten Auftrag.",
        "Solange der Graue Eid steht, bleibt der Weg offen.",
        "Solange sein Träger zurückkehrt, ist kein Scheitern endgültig.",
        "Also gehen wir weiter, Land für Land, bis zur Krone ohne Namen.",
        "Die letzte Wache fällt. Die Weltennaht liegt offen.",
        "Vor uns wartet kein König, sondern der Hunger aller vergessenen Namen.",
        "Jeder gerettete Ort steht nun an unserer Seite. Jeder verlorene Ort gegen uns.",
        "Dies ist der Auftrag, den niemand bezahlen kann.",
        "Der erste Eidanker bricht. Die Festung verliert ihre Form.",
        "Der zweite Eidanker bricht. Fremde Länder stürzen in die Arena.",
        "Der dritte Eidanker bricht. Die Krone zeigt ihr wahres Gesicht.",
        "Sammelt die Kraft. Werft die Würfel. Sprecht den letzten Eid.",
        "Die Krone ist gebrochen, doch die Pfade schweigen nicht.",
        "Hinter der Naht wartet eine andere Möglichkeit derselben Welt.",
        "Wir können sie versiegeln, zerstören, binden oder beherrschen.",
        "Keine Wahl macht uns unschuldig. Aber jede Wahl gehört endlich uns.",
        "Das Weltenecho nimmt unsere Narben, unsere Namen und unsere stärksten Relikte an.",
        "Seine Länder liegen anders. Seine Feinde haben aus unserer Reise gelernt.",
        "Was wir nicht fanden, kann dort auf uns warten.",
        "Was wir nicht retteten, kann dort noch eine zweite Chance erhalten.",
        "Der Graue Eid endet nicht mit einem Sieg.",
        "Er beginnt erneut, sobald sein Zeichen den nächsten Weg wählt.",
        "Der Wegstein antwortet auf das Zeichen.",
        "Eine neue Karte zeichnet sich aus Licht und Erinnerung.",
        "Die Grenzen verschieben sich. Der Seed der Welt steht fest.",
        "Die Vorräte sind knapp, doch der Eid ist vollständig.",
        "Händler, Fraktionen und Bosse werden sich an unsere Entscheidungen erinnern.",
        "Die stärksten Relikte verändern Regeln, nicht nur Zahlen.",
        "Ein Rückschlag führt zum letzten sicheren Wegstein zurück.",
        "Der Tod beendet den Auftrag nicht. Er verlangt nur einen besseren Versuch.",
        "Atem holen. Karten ordnen. Der Pfad wartet.",
        "Der Graue Eid. Ein Auftrag. Unzählige Welten.",
    ]
    for index, text in enumerate(plot_texts):
        speaker = "narrator" if index not in {8, 9, 11, 15, 19, 23, 29, 33, 38} else ("pathfinder" if index % 2 == 0 else "vanguard")
        lines.append({"id": f"plot_{index + 1:02d}", "speaker": speaker, "text": text, "category": "plot"})

    for country_id, country_name, hook in COUNTRIES:
        country_lines = [
            f"{country_name}. {hook}",
            f"Der Wegstein von {country_name} ist instabil. Wir sichern erst den Pfad und stellen uns dann seinem Hüter.",
            "Was hier jagt, hat gelernt, unvorsichtige Reisende zu verschlucken.",
        ]
        for index, text in enumerate(country_lines):
            lines.append({"id": f"country_{country_id}_{index + 1}", "speaker": "narrator" if index == 0 else ("pathfinder" if index == 1 else "vanguard"), "text": text, "category": "country"})

    for kind, title, hook in SCENARIOS:
        texts = [f"{title}. {hook}", "Ausrüstung, Position und Aktionspunkte müssen vor dem ersten Zug stimmen.", "Schwächen lassen sich mit der richtigen Kartenfolge ausgleichen."]
        for index, text in enumerate(texts):
            lines.append({"id": f"scenario_{kind}_{index + 1}", "speaker": "pathfinder" if index != 1 else "vanguard", "text": text, "category": "scenario"})

    for country_id, country_name, _hook in COUNTRIES:
        texts = [
            f"Der Hüter von {country_name} betritt den Eidkreis.",
            "Seine erste Verteidigung bricht. Erwartet ein verändertes Angriffsmuster.",
            "Der Hüter gibt seine wahre Macht frei. Spart nichts mehr auf.",
            "Der Eidkreis ist still. Der Wegstein erkennt euren Sieg an.",
        ]
        for index, text in enumerate(texts):
            lines.append({"id": f"boss_{country_id}_{index + 1}", "speaker": f"boss_{country_id}" if index < 3 else "narrator", "text": text, "category": "boss"})

    final_texts = [
        "Ich bin die Krone, der ihr eure Namen schuldet.",
        "Jede gerettete Welt ist nur eine weitere Kette.",
        "Brecht meinen Körper. Die Naht selbst wird für mich kämpfen.",
        "Dann sprecht euren letzten Eid, und seht, welcher Name bestehen bleibt.",
    ]
    for index, text in enumerate(final_texts):
        lines.append({"id": f"final_{index + 1}", "speaker": "boss_weltennaht", "text": text, "category": "final"})

    hero_templates = {
        "pathfinder": [
            "Ich habe freie Sicht.", "Ziel markiert.", "Der Wind steht gut.", "Ich decke dich.", "Falle liegt.", "Ein Schritt nach links.",
            "Rüstung gebrochen.", "Der nächste Pfeil sitzt.", "Deckung halten.", "Ich brauche einen Augenblick.", "Magie sammelt sich.", "Der Pfad antwortet.",
            "Noch eine Welle.", "Der Boss wechselt sein Muster.", "Jetzt zählt jeder Treffer.", "Ich bin getroffen.", "Es geht noch.", "Danke. Weiter.",
            "Beute gesichert.", "Das ist selten.", "Dieser Weg ist neu.", "Ich kenne diese Spuren.", "Nicht stehen bleiben.", "Für den Grauen Eid.",
        ],
        "vanguard": [
            "Hinter meinen Schild.", "Ich halte die Linie.", "Jetzt kommt die Axt.", "Seine Deckung bricht.", "Ich ziehe den Angriff.", "Bleib an meiner Seite.",
            "Noch stehe ich.", "Der Schlag war nichts.", "Runen, jetzt.", "Ich brauche Heilung.", "Der Eid trägt uns.", "Keine Gnade für Eidbrecher.",
            "Die nächste Welle gehört mir.", "Der Boss wird wütend.", "Jetzt zuschlagen.", "Das hat gesessen.", "Nur ein Kratzer.", "Gut abgefangen.",
            "Wähle mit Bedacht.", "Eine starke Klinge.", "Der Wegstein erwacht.", "Hier stimmt etwas nicht.", "Vorwärts.", "Auftrag zu Ende bringen.",
        ],
        "duelist": [
            "Die linke Klinge zuerst.", "Zu langsam.", "Ich bin schon hinter ihm.", "Deckung ist nur eine Einladung.", "Wir schneiden einen Weg.", "Halte ihn einen Herzschlag.",
            "Meine Klingen antworten.", "Der nächste Schnitt entscheidet.", "Ich lenke sie ab.", "Ein kurzer Atemzug.", "Das Blutzeichen glüht.", "Der Pfad kennt meinen Schritt.",
            "Noch mehr Ziele.", "Sein Rhythmus bricht.", "Doppelschlag, jetzt.", "Nur gestreift.", "Ich tanze noch.", "Sauber aufgefangen.",
            "Nimm, was zu deinem Stil passt.", "Diese Schneide hat Geschichte.", "Eine Abzweigung.", "Spuren auf Augenhöhe.", "Bleib in Bewegung.", "Unser Eid, unser Tempo.",
        ],
        "arbalist": [
            "Bolzen geladen.", "Ziel im Visier.", "Windkorrektur steht.", "Ich sichere die Flanke.", "Der Mechanismus hält.", "Nicht in meine Schusslinie.",
            "Panzerplatte gesprengt.", "Der nächste Bolzen durchschlägt.", "Ich halte Abstand.", "Nachladen.", "Runenladung bereit.", "Die Sehne antwortet.",
            "Welle bestätigt.", "Neue Bossfrequenz.", "Auf mein Signal.", "Treffer eingesteckt.", "System bleibt stabil.", "Gute Deckung.",
            "Prüf die Mechanik.", "Seltene Fertigung.", "Neue Route vermessen.", "Ich sehe den Hinterhalt.", "Position wechseln.", "Der Auftrag trifft ins Schwarze.",
        ],
        "swordmaster": [
            "Die Klinge steht bereit.", "Gerade Linie.", "Halbschwertgriff.", "Die Hut hält.", "Der Ort ist gewählt.", "Kein Schritt zu viel.",
            "Die Rüstung gibt nach.", "Der nächste Hieb entscheidet.", "Parade gesetzt.", "Ein Atemzug.", "Der Stahl trägt Runen.", "Der Pfad kennt diese Klinge.",
            "Noch eine Welle.", "Das Muster ist erkannt.", "Jetzt fällt das Urteil.", "Der Treffer war flach.", "Der Stand bleibt fest.", "Saubere Parade.",
            "Wähle nach Balance.", "Dieser Stahl erinnert sich.", "Ein neuer Pfad.", "Die Spur kreuzt sich.", "Im Maß bleiben.", "Für den ersten Eid.",
        ],
    }
    for speaker, texts in hero_templates.items():
        for index, text in enumerate(texts):
            lines.append({"id": f"bark_{speaker}_{index + 1:02d}", "speaker": speaker, "text": text, "category": "hero_bark"})

    role_words = {
        "skirmisher": ("Schneller!", "Umkreisen!"), "brute": ("Zerbrechen!", "Knochen zu Staub!"),
        "defender": ("Kein Durchgang!", "Haltet die Linie!"), "hexer": ("Eure Namen vergehen!", "Der Fluch findet euch!"),
        "marksman": ("Ziel erfasst!", "Kein Entkommen!"), "assassin": ("Zu spät.", "Ein Atemzug genügt."),
        "beast": ("Rrraah!", "Grrrrauw!"), "controller": ("Beugt euch!", "Der Kreis schließt sich!"),
        "elite": ("Ihr endet hier!", "Prüft euren Eid!"), "boss": ("Kniet vor dem Hüter!", "Dieses Land gehört mir!"),
    }
    for role in ROLES:
        first, second = role_words[role]
        texts = [first, second, "Vorwärts!", "Jetzt!", "Ihr fallt!", "Der Wegstein wird schweigen!"]
        for index, text in enumerate(texts):
            lines.append({"id": f"enemy_{role}_{index + 1}", "speaker": f"enemy_{role}", "text": text, "category": "enemy_bark"})

    tutorial = [
        "Jede Runde besitzt Angriff, Verteidigung, Magie und Vorbereitung.",
        "Die fünf Aktionspunkte gelten übergreifend für alle vier Phasen.",
        "Ein Wurf von zwölf zählt als kritischer Doppelerfolg.",
        "Blockwürfel entfernen Treffer, Bannwürfel entfernen Magieerfolge.",
        "Ausrüstung kann Werte erhöhen und neue Karten freischalten.",
        "Jeder Kampagnencharakter muss seine Beute wählen, bevor die Reise weitergeht.",
        "Nach einem Szenario werden Leben und Aktionspunkte vollständig erneuert.",
        "Fällt ein Söldner, kehrt die Kampagne zum letzten sicheren Wegstein zurück.",
        "Untertitel, Stimmen und Dynamikbereich lassen sich getrennt einstellen.",
        "Cinematics können übersprungen werden; wichtige Hinweise bleiben im Log erhalten.",
    ]
    for index, text in enumerate(tutorial):
        lines.append({"id": f"tutorial_{index + 1:02d}", "speaker": "mentor", "text": text, "category": "tutorial"})

    ending_texts = {
        "seal": ("Wir versiegeln die Naht. Kein Name soll sie wieder öffnen.", "Die Pfade werden still, aber ihre Welt bleibt frei."),
        "destroy": ("Wir zerstören die Krone und jeden Weg, der zu ihr führt.", "Ein Teil der Welt vergeht, damit der Rest ohne Ketten leben kann."),
        "bind": ("Wir binden die Krone an den Grauen Eid.", "Ihre Macht bleibt, doch sie gehorcht fortan seinem Zeichen."),
        "dominate": ("Wir nehmen den namenlosen Thron für uns.", "Die Pfade knien – und jede kommende Welt wird unser Urteil kennen."),
    }
    for choice, texts in ending_texts.items():
        for index, text in enumerate(texts):
            lines.append({"id": f"ending_{choice}_{index + 1}", "speaker": "duelist" if index == 0 else "narrator", "text": text, "category": "ending"})
    lines.extend([
        {"id": "legacy_1", "speaker": "arbalist", "text": "Das stärkste Relikt jedes Söldners übersteht das Weltenecho.", "category": "legacy"},
        {"id": "legacy_2", "speaker": "narrator", "text": "Die Vermächtnisse werden in die Karte der nächsten Welt geschrieben.", "category": "legacy"},
    ])

    assert len(lines) == 360, len(lines)
    assert len({line["id"] for line in lines}) == len(lines)
    return lines


def shot(plate: str, duration: float, lines: list[str], motion: str = "push_in") -> dict[str, Any]:
    return {"plate": plate, "duration": duration, "motion": motion, "lines": lines, "fade_in": 0.65, "fade_out": 0.65}


def make_cinematics() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {"id": "prologue", "trigger": "campaign_started", "scope": "campaign_once", "skippable": True, "shots": [shot("res://assets/cinematics/prologue.png", 18.0, [f"plot_{index:02d}" for index in range(1, 9)])]},
        {"id": "departure", "trigger": "first_scenario", "scope": "campaign_once", "skippable": True, "shots": [shot("res://assets/cinematics/journey.png", 11.0, [f"plot_{index:02d}" for index in range(9, 13)], "pan_right")]},
    ]
    for country_id, _name, _hook in COUNTRIES:
        biome = {"nebelmark":"moor","sonnenbruch":"desert","frostreiche":"frost","splitterinseln":"coast","aschenlande":"ash","dornwall":"thorn","glassteppe":"crystal","tiefenwald":"forest","kupferkueste":"coast","knochental":"bone","nachtkrone":"night","sturmmarsch":"storm","versunkener_bund":"sunken","weltennaht":"rift"}[country_id]
        entries.append({"id": f"country_{country_id}", "trigger": "country_entered", "context": country_id, "scope": "country_once", "skippable": True, "shots": [shot(f"res://assets/backgrounds/{biome}.png", 8.5, [f"country_{country_id}_{index}" for index in range(1, 4)], "pan_left")]})
    for kind, _title, _hook in SCENARIOS:
        entries.append({"id": f"briefing_{kind}", "trigger": "scenario_started", "context": kind, "scope": "repeatable", "skippable": True, "shots": [shot("$scenario_background", 6.5, [f"scenario_{kind}_{index}" for index in range(1, 4)])]})
    for country_id, _name, _hook in COUNTRIES:
        plate = "res://assets/cinematics/finale.png" if country_id == "weltennaht" else "$scenario_background"
        entries.append({"id": f"boss_{country_id}", "trigger": "boss_started", "context": country_id, "scope": "scenario_once", "skippable": True, "shots": [shot(plate, 9.5, [f"boss_{country_id}_{index}" for index in range(1, 5)], "push_in")]})
    entries.extend([
        {"id": "final_phase_2", "trigger": "boss_phase", "context": 2, "scope": "scenario_once", "skippable": True, "shots": [shot("res://assets/cinematics/finale.png", 4.0, ["final_1"])]},
        {"id": "final_phase_3", "trigger": "boss_phase", "context": 3, "scope": "scenario_once", "skippable": True, "shots": [shot("res://assets/cinematics/finale.png", 4.0, ["final_2"])]},
        {"id": "final_phase_4", "trigger": "boss_phase", "context": 4, "scope": "scenario_once", "skippable": True, "shots": [shot("res://assets/cinematics/finale.png", 6.0, ["final_3", "final_4"])]},
        {"id": "final_death", "trigger": "final_boss_defeated", "scope": "campaign_once", "skippable": True, "shots": [shot("res://assets/cinematics/finale.png", 10.0, [f"plot_{index:02d}" for index in range(13, 21)], "pull_out")]},
        {"id": "epilogue", "trigger": "campaign_completed", "scope": "campaign_once", "skippable": True, "shots": [shot("res://assets/cinematics/world_echo.png", 20.0, [f"plot_{index:02d}" for index in range(21, 41)], "pan_right")]},
        {"id": "rollback", "trigger": "rollback", "scope": "repeatable", "skippable": True, "shots": [shot("res://assets/backgrounds/rift.png", 4.0, ["plot_37", "plot_38"], "shake")]},
        {"id": "tutorial", "trigger": "manual_tutorial", "scope": "repeatable", "skippable": True, "shots": [shot("res://assets/backgrounds/character_select.png", 24.0, [f"tutorial_{index:02d}" for index in range(1, 11)], "pan_right")]},
    ])
    for choice in ("seal", "destroy", "bind", "dominate"):
        entries.append({"id": f"ending_{choice}", "trigger": "ending_resolved", "context": choice, "scope": "campaign_once", "skippable": True, "shots": [shot("res://assets/cinematics/ending_crossroads.png", 9.0, [f"ending_{choice}_1", f"ending_{choice}_2"], "pan_left")]})
    entries.append({"id": "legacy_transfer", "trigger": "legacy_transfer_ready", "scope": "campaign_once", "skippable": True, "shots": [shot("res://assets/cinematics/world_echo.png", 8.0, ["legacy_1", "legacy_2"], "push_in")]})
    assert len(entries) == 48, len(entries)
    for entry in entries:
        entry["required_lines"] = [line for item in entry["shots"] for line in item["lines"]]
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cinematics-only", action="store_true")
    args = parser.parse_args()
    cinematics = {"version": 1, "cinematics": make_cinematics()}
    if args.cinematics_only:
        write_json(SHARED / "cinematics.json", cinematics)
        write_json(CLIENT_NARRATIVE / "cinematics.json", cinematics)
        print("Generated 48 cinematics")
        return
    lines = make_lines()
    profiles = {
        "narrator": {"voice": "de+m3", "speed": 150, "pitch": 38},
        "pathfinder": {"voice": "de+f3", "speed": 172, "pitch": 56},
        "vanguard": {"voice": "de+m4", "speed": 158, "pitch": 32},
        "duelist": {"voice": "de+f4", "speed": 181, "pitch": 61},
        "arbalist": {"voice": "de+m2", "speed": 148, "pitch": 27},
        "swordmaster": {"voice": "de+m5", "speed": 154, "pitch": 34},
        "mentor": {"voice": "de+f2", "speed": 162, "pitch": 48},
    }
    for country_id, _name, _hook in COUNTRIES:
        profiles[f"boss_{country_id}"] = {"voice": f"de+m{2 + (len(country_id) % 6)}", "speed": 128 + len(country_id) % 18, "pitch": 20 + len(country_id) % 22}
    for index, role in enumerate(ROLES):
        profiles[f"enemy_{role}"] = {"voice": f"de+m{1 + index % 7}", "speed": 138 + index * 4, "pitch": 24 + index * 3}
    manifest = {
        "version": 1,
        "locale": "de-DE",
        "generator": "offline-espeak-ng",
        "production_note": "Austauschbare Offline-Produktionsstimmen; IDs, Untertitel und Timings bleiben bei Studioersatz stabil.",
        "profiles": profiles,
        "lines": [{**line, "asset": f"res://assets/voice/de-DE/{line['speaker']}/{line['id']}.wav", "duration_ms": 0} for line in lines],
    }
    locale = {"locale": "de-DE", "strings": {line["id"]: line["text"] for line in lines}}
    write_json(SHARED / "voice_manifest.de-DE.json", manifest)
    write_json(SHARED / "locales" / "de-DE.json", locale)
    write_json(SHARED / "cinematics.json", cinematics)
    write_json(CLIENT_NARRATIVE / "voice_manifest.de-DE.json", manifest)
    write_json(CLIENT_NARRATIVE / "de-DE.json", locale)
    write_json(CLIENT_NARRATIVE / "cinematics.json", cinematics)
    print("Generated 48 cinematics and 360 German voice/subtitle lines")


if __name__ == "__main__":
    main()
