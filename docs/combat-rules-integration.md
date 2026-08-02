# Integration der Szenario- und Kampfregeln

Die neuen Module `server/app/scenario_rules.py`, `server/app/combat_actions.py` und
`server/app/combat_protocol.py` enthalten die Regeln vollständig, verändern aber
bewusst weder `game_engine.py` noch `game_state.py`. Alle zusätzlichen Laufzeitdaten
liegen serialisierbar unter `state.world.scenario_runtime` beziehungsweise
`state.world.combat_runtime` und überleben daher Export, Checkpoint und Reconnect.

## 1. Szenariostart und Clientansicht

In `_start_scenario_encounter()`:

1. `ScenarioRules.initialize(self.state)` aufrufen.
2. Für normale Szenarien alle gleichzeitig aktiven Definitionen über
   `_enemy_from_catalog()` erstellen und an `TargetRules.initialize()` übergeben.
   Länder- und Endboss-Verträge dürfen weiter bewusst sequenziell bleiben.
3. `IntentRules.announce(self.state)` aufrufen. Dasselbe nach jedem sauberen
   Runden- und Wellenstart tun.

In `client_view()` ergänzen:

```python
state["scenario_objective"] = ScenarioRules.client_view(self.state)
state["combat"] = combat_client_view(self.state)
```

Damit sind Ziel-LP, Scheitern, alle Gegnerziele, angekündigte Absicht sowie offene
Reaktions- und Koop-Zustände nach Reconnect sichtbar.

## 2. Kartenspiel, Zielwahl und mehrere Gegner

`play_card()` muss `target_ids` als Liste annehmen; ein altes `target_id` wird durch
`PlayCardMessage` kompatibel normalisiert. Vor AP-Abzug:

1. Reaktionskarten außerhalb eines offenen Reaktionsfensters ablehnen.
2. Bei `kind == "cooperation"` nur `CooperationRules.propose()` ausführen und noch
   keine AP oder Karte verbrauchen.
3. Sonst `TargetRules.select(state, actor_id, card, target_ids)` aufrufen.
4. Ausgewählte Ziele an jeden Zieleffekt weiterreichen. Physischer/magischer Schaden
   und `armor_break` laufen über `TargetRules.damage()` beziehungsweise
   `TargetRules.armor_break()`.
5. `ScenarioRules.record_card()` mit denselben Ziel-IDs aufrufen.

`AREA_CARD_IDS` definiert die vorhandenen Flächenkarten mit bis zu drei Zielen. Sobald
alle Karten ein explizites `targeting`-Feld besitzen, kann die Übergangsliste entfallen.

## 3. Bestätigte Kooperation

Die WebSocket-Nachricht `confirm_cooperation` wird an
`CooperationRules.respond()` geleitet. Nur bei `cooperation_confirmed` darf
`CooperationRules.consume()` ausgeführt und die reservierte Karte über den normalen
Effektpfad bezahlt/abgelegt werden. Bei Ablehnung `clear_rejected()` aufrufen; Hand und
AP bleiben unverändert. Während eine Kooperation offen ist, werden weitere normale
Aktionen blockiert.

## 4. Intent und echtes Reaktionsfenster

Die Absicht wird am Rundenanfang mit `IntentRules.announce()` festgeschrieben und im HUD
angezeigt; `_enemy_phase()` darf sie nicht neu bestimmen. Am Ende der Utility-Phase:

1. `ReactionRules.open()` aufrufen und die Gegnerauflösung pausieren.
2. Jede `react`-Nachricht an `ReactionRules.respond()` leiten. `card_id = null` bedeutet
   explizites Passen.
3. Erst nach `reaction_window_ready` `ReactionRules.consume()` ausführen, die
   enthaltenen Karten bezahlen/ablegen und ihre Verteidigungseffekte anwenden.
4. Danach `IntentRules.consume()` und erst dann Angriffswürfel und Schaden auflösen.

So kann weder ein einzelner Client noch ein Reconnect das Fenster überspringen.

## 5. Szenariofortschritt und Scheitern

- Nach jedem Gegnerangriff `ScenarioRules.record_enemy_attack(unblocked_hits)` aufrufen.
- Beim Rundenstart `ScenarioRules.record_round_started()` aufrufen.
- Bei Spielerfall `ScenarioRules.record_player_fallen()` aufrufen.
- Bei Gegnerfall `ScenarioRules.record_enemy_defeated(remaining_enemies)` aufrufen.
- Vor `_complete_scenario()` muss `ScenarioRules.assert_completion_allowed()` bestehen.

Ein Event `scenario_objective_failed` löst den vorhandenen Szenario-Rollback aus. Die
persistierte Konsequenz markiert den gescheiterten Versuch als ungelöst. Erfolgreicher
Dorf-/Karawanenschutz schreibt zusätzlich Fraktionsruf; ein erfolgreicher Ruinenlauf
liefert über `ruin_loot_rarity_bonus()` eine Seltenheitsstufe Bonus.

Die sechs normalen Szenariotypen besitzen damit reale Regeln:

| Typ | Sieg-/Fehlbedingung |
|---|---|
| Hinterhalt | Eröffnungsangriff überleben; Fall in Runde 1 scheitert |
| Überfall | alle Wellen vor Bedrohung 6 besiegen |
| Dorf | Dorfbewohner-LP bis zum Sieg erhalten |
| Karawane | Karawanen-LP bis zum Sieg erhalten |
| Jagd | Utility-Vorbereitung in Runde 1, sonst Flucht |
| Ruine | alle Gegner vor Fluch 6 besiegen; Cleanse senkt Fluch |

## 6. DoT-/Fallentod beim Wellenwechsel

In `_finish_round()` den Spieler-DoT-/Regenerationsblock in einen gemeinsamen
End-of-round-Upkeep-Helper extrahieren. Stirbt der Gegner in `_enemy_phase()` durch
Burning, Bleeding oder Falle:

1. `_resolve_enemy_defeat()` ausführen.
2. Bei Folgewelle den Spieler-Upkeep genau einmal ausführen.
3. `WaveTransitionRules.after_round_resolution()` aufrufen.
4. Intent der neuen Welle ankündigen und zurückkehren.

Bei einem Kill durch eine Karte darf dieser Hook nicht laufen; Phase, AP und aktive
Figur bleiben dann absichtlich erhalten. Der Regressionstest prüft, dass der
end-of-round-Fall immer in einer frischen Attack-Phase, mit leerer Passliste, neuer
Rundennummer und 5 AP beginnt.

## 7. Tote Status- und Effektpfade

- `StatusRules.consume_player_roll_penalty()` in `_roll_check()` einrechnen; dadurch
  reduziert Spieler-`bound` den nächsten Treffer-, Magie- oder Bannpool.
- Nach ungeblockten Treffern `StatusRules.apply_enemy_hit()` aufrufen. Assassinen
  erzeugen Bleeding, Controller bei Hex/Pressure Poisoned; bestehende regionale
  Burning/Bound/Weakened-Pfade werden vereinheitlicht.
- Gegnerische magische/Hex-Erfolge vor Schaden über
  `EffectRules.resolve_player_ward()` auflösen; damit wirken Item-`ward_dice`.
- Teamheilung über `EffectRules.heal()` ausführen. Der Heilbonus stammt vom Heiler,
  nicht vom Ziel. `runenheilung` nutzt jetzt `heal_all`.
- `riss_im_panzer` nutzt jetzt den eigenständigen `armor_break`-Effekt.
- `StatusRules.weapon_combo_bonus()` in bestätigte Koop-Angriffe einrechnen; dadurch
  ist `played_weapon_this_round` keine tote Variable mehr.
- Talentbelohnungen über `TalentRules.unlock()` vergeben; Doppelfreischaltung wird
  autoritativ abgelehnt.

## 8. Protokollverdrahtung

`combat_protocol.py` stellt strikte, diskriminierte Modelle bereit:

- `play_card`: `card_id`, optional `target_ids` (maximal drei; altes `target_id` bleibt
  kompatibel)
- `react`: `card_id` oder `null`, optional `target_ids`
- `confirm_cooperation`: verpflichtendes `accepted`

Diese Modelle in die WebSocket-Union in `schemas.py` aufnehmen und dieselben Zweige in
`shared/protocol.schema.json` ergänzen. `main.py` leitet sie an die oben genannten
Regeln weiter. Das bleibt Protokollversion 2, da alle bisherigen Nachrichten gültig
bleiben und nur neue diskriminierte Nachrichtentypen hinzukommen.

## 9. Verifikation

```bash
PYTHONPATH=server python3 -m unittest -v \
  server.tests.test_scenario_rules \
  server.tests.test_combat_actions \
  server.tests.test_combat_protocol
```

Der isolierte Lauf umfasst 32 Regressionstests.
