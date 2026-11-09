# Realiser A16 Control

Home-Assistant-Integration und Protokoll-Bibliothek für den **Smyth Research Realiser A16**
(IP-Command-Server, ab Firmware 1.90). Bildet alle Funktionen der IR-Fernbedienung und der
Centro-Control-App ab und ist so aufgebaut, dass ein Standalone-ESP32 dieselbe
Protokoll-Definition nutzen kann.

## Am A16 einstellen

Settings → Network:

- feste IP-Adresse und Port (Standard 4101)
- **TCP command server**: an
- **TCP slave response**: an (der A16 meldet Änderungen dann von selbst, auch bei Bedienung per IR)

## Installation

`custom_components/realiser_a16` nach `<config>/custom_components/` kopieren (oder das Repo
in HACS als benutzerdefiniertes Repository vom Typ „Integration" eintragen), Home Assistant
neu starten, dann *Einstellungen → Geräte & Dienste → Integration hinzufügen → Smyth Realiser A16*.

## Entities

| Plattform | Inhalt |
|---|---|
| `media_player` | Benutzer A und B: Lautstärke, Mute, Quelle, Preset (als Sound-Modus), An/Standby |
| `remote` | alle 50 IR-Tasten und alle übrigen Befehle per `remote.send_command` |
| `select` | Quelle, Preset A, Preset B, Tippmodus der Lautsprecher (Solo/Stumm) |
| `switch` | Power, Mute A/B, Testsignal, Head-Tracker; optional ein Schalter je Lautsprecher |
| `button` | Kopfhörermodus (SVS), Lautsprechermodus (AV/MIX/SVS), Pegel zurücksetzen, Aktualisieren |
| `sensor` | Raum, Layout, Kopfhörer, HPEQ-Daten je Benutzer; Decoder, Format, Upmixer, Modi; Firmware |
| `binary_sensor` | Verbindung, Tactile-Ausgang A/B |

Befehlsnamen für `remote.send_command` und den Service `realiser_a16.send_command`:

- IR-Tasten: `power menu back enter cancel adj_plus adj_minus up down left right 0–9 star hash
  cal spk hp c l r lw rw ls rs lb rb lfe oh all headphone speaker vol_a_up vol_a_down vol_b_up
  vol_b_down mute_a mute_b test ht pa pb`
- `source_earc`, `source_hdmi1` … `source_optical`
- `preset_a_1` … `preset_a_16`, `preset_b_1` … `preset_b_16`
- `speaker_1` … `speaker_50` (IDs siehe `protocol/a16_protocol.json`)
- `power_on`, `power_standby`, `reset_levels`
- Rohcode: `0x43`

```yaml
action: remote.send_command
target: { entity_id: remote.realiser_a16 }
data: { command: [menu, down, down, enter] }
```

## Karte

Die Karte wird von der Integration mitgeliefert und automatisch geladen:

```yaml
type: custom:realiser-a16-card
# optional:
# title: Kino
# tabs: [control, speakers, remote]     # control, speakers, meters, tracker, remote, about
# default_tab: control
# entry_id: …                           # nur bei mehreren A16
```

Pegelanzeigen und Head-Tracker-Winkel werden nur vom A16 abgefragt, solange der jeweilige
Reiter offen ist; sie werden bewusst nicht als Entities geführt.

## Was man wissen sollte

- Der A16 verarbeitet nur etwa zwei Befehle pro Sekunde; schnellere gehen kommentarlos
  verloren. Die Bibliothek sendet deshalb mit mindestens 0,5 s Abstand, wartet auf die
  Antwort und wiederholt einen unbeantworteten Befehl einmal. Eine absolute
  Lautstärkeänderung um 8 Schritte dauert so rund 4 Sekunden (es gibt keinen Befehl für
  absolute Lautstärke).
- Mute und Head-Tracker-Status meldet der A16 erst, nachdem die Taste einmal benutzt wurde.
- Details und Messwerte: [protocol/PROTOCOL.md](protocol/PROTOCOL.md).

## Aufbau

```
protocol/a16_protocol.json            einzige Quelle für Codes, Quellen, Lautsprecher
tools/gen_protocol.py                 erzeugt daraus:
  custom_components/realiser_a16/a16/protocol_gen.py
  custom_components/realiser_a16/frontend/protocol_gen.js
  esp32/include/a16_protocol.h
custom_components/realiser_a16/a16/   asyncio-Bibliothek ohne Home-Assistant-Abhängigkeit
custom_components/realiser_a16/       Integration + Karte
tools/a16cli.py                       Kommandozeile: status | watch | send | volume
tools/probe.py                        Rohmitschnitt vom Gerät
tests/                                Parser (mit echtem Mitschnitt), Client, Integration
```

## ESP32-Port

`esp32/include/a16_protocol.h` enthält alle Codes, Quellen und die Lautsprechertabelle samt
Rasterposition. Für die Firmware sind `a16/parser.py` (Tokenizer + Zuordnung) und
`a16/client.py` (Sendeabstand, Nachfragen nach Preset-/Lautsprecherwechsel) die Vorlage;
[protocol/PROTOCOL.md](protocol/PROTOCOL.md) beschreibt Framing und Timing.

## Entwicklung

```bash
uv sync
uv run pytest
python3 tools/gen_protocol.py            # nach Änderungen an a16_protocol.json
python3 tools/a16cli.py 192.168.1.53 status
```

## Lizenz

MIT – siehe [LICENSE](LICENSE). Kein offizielles Produkt von Smyth Research; Nutzung auf
eigene Gefahr.
