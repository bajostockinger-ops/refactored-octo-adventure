# CI — Command Interface

Eine Shell-Oberfläche für das Terminal: alles über Tasten, immer sichtbar wo du
bist und welche Befehle gerade zur Verfügung stehen. Eine einzige Python-Datei,
keine Abhängigkeiten, läuft überall wo Python und ein Terminal sind.

```
╭─ CI ── ⌂ Haupt › Git ─ Repository im aktuellen Verzeichnis ─────────────────────────── 21:14:07 ─╮
│ /home/user/refactored-octo-adventure  ·  ⎇ claude/cool-bell-jhvb26  ·  ●2             15 Befehle │
├────────────────────────────────────────────────────────────────┬─────────────────────────────────┤
│   ANSEHEN ──────────────────────────────────────────────────── │ ●  Status                       │
│   [s]   ● Status                                         lesen │ Befehl   ·   Taste [s]          │
│   [d]   ± Diff (nicht gestaged)                          lesen │                                 │
│   [i]   ± Diff (gestaged)                                lesen │ Kurzer Status inklusive Branch  │
│   [l]   ≣ Log (Graph)                                    lesen │ und Tracking.                   │
│   [v]   ≣ Letzter Commit im Detail                       lesen │                                 │
│   [m]   ▤ Datei-Historie                                 lesen │ Befehl                          │
│   AENDERN ──────────────────────────────────────────────────── │ $ git -c color.ui=always        │
│   [A]   + Alles stagen                                         │   status -sb                    │
│   [P]   + Interaktiv stagen                                    │                                 │
│   [C]   ✓ Commit                                               │                                 │
│   [N]   ✓ Commit nachbessern                                   │                                 │
│   [u]   - Letzten Commit zuruecknehmen                         │                                 │
│   [X]   ✗ Alle Aenderungen verwerfen               gefaehrlich │                                 │
│   MEHR ─────────────────────────────────────────────────────── │                                 │
│   [b]   ⎇ Branches                                           → │                                 │
│   [r]   ⇅ Remote                                             → │                                 │
│   [t]   ⧉ Stash                                              → │                                 │
│                                                                │                                 │
│                                                                │                                 │
├────────────────────────────────────────────────────────────────┴─────────────────────────────────┤
│ ↑↓ Bewegen   ⏎ Ausfuehren   ⌫ Zurueck   / Filter   * Favorit   ^P Alle Befehle   ! Shell         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯```

## Installieren

```bash
./install.sh
```

Danach neue Shell öffnen und `ci` tippen. Der Installer legt
`~/.local/bin/ci` an, schreibt die Standard-Konfiguration nach
`~/.config/ci-shell/menu.toml` und bindet auf Wunsch eine Shell-Funktion ein —
damit bleibt deine Shell nach dem Beenden in dem Verzeichnis, in dem CI
gerade stand.

Ohne Installation geht es genauso:

```bash
./ci.py
```

Gebraucht wird Python 3.11 oder neuer (für `tomllib`). Auf älteren Versionen
reicht `python3 -m pip install --user tomli`.

## Die Oberfläche

| Bereich | Was dort steht |
|---|---|
| Titelzeile | Breadcrumb — wo du gerade bist (`⌂ Haupt › Git › Branches`), plus Uhr |
| Kontextzeile | Arbeitsverzeichnis, Git-Branch, Anzahl geänderter Dateien, ahead/behind, Stashes |
| Liste | alle Befehle dieser Ebene, mit Hotkey, Symbol und Markierungen |
| Detail-Panel | Beschreibung, der echte Shell-Befehl, Eingabefelder, Warnhinweise, Statistik |
| Fußzeile | genau die Tasten, die *jetzt* etwas tun — je nach Situation andere |

Einträge, deren Programm fehlt, sind grau und zeigen `docker fehlt` — sie lassen
sich nicht versehentlich starten.

## Tasten

**Bewegen**

| Taste | Wirkung |
|---|---|
| `↑` `↓` oder `j` `k` | Eintrag wechseln |
| `Bild ↑` `Bild ↓` | seitenweise |
| `Pos1` `Ende` | erster / letzter Eintrag |
| `1` … `9` | direkt zum n-ten Eintrag |
| Buchstabe | Eintrag mit diesem Hotkey sofort starten |

**Benutzen**

| Taste | Wirkung |
|---|---|
| `⏎` / `→` | öffnen bzw. ausführen |
| `⌫` / `←` / `Esc` | eine Ebene zurück |
| `/` | Filter tippen (fuzzy), `Esc` leert ihn |
| `*` | Eintrag als Favorit an- oder abwählen |
| `Strg-P` | Suche über *alle* Befehle aller Menüs |
| `!` | freien Shell-Einzeiler eingeben |
| `?` | Hilfe mit der ganzen Tastenbelegung |
| `Strg-O` | letzte Ausgabe nochmal ansehen |
| `Strg-T` | Farbschema durchschalten |
| `Strg-R` | `menu.toml` neu laden |
| `q` | beenden |

**Im Ausgabe-Fenster**

| Taste | Wirkung |
|---|---|
| `j` `k`, `Bild ↑/↓`, `g` `G` | scrollen |
| `h` `l` | waagerecht scrollen (bei ausgeschaltetem Umbruch) |
| `u` | Zeilenumbruch an / aus |
| `f` | Ausgabe mitlaufen lassen (wie `tail -f`) |
| `/`, `n`, `N` | in der Ausgabe suchen und springen |
| `s` | Ausgabe als Datei speichern |
| `r` | Befehl erneut starten |
| `Strg-C`, nochmal `Strg-C` | abbrechen, dann hart beenden |
| `q` / `Esc` / `⏎` | schließen |

## Eigene Befehle eintragen

Alles steckt in `~/.config/ci-shell/menu.toml`. Nach dem Speichern `Strg-R`
drücken — oder im Hauptmenü `c` für *Konfiguration bearbeiten*, dann lädt CI
automatisch neu.

```toml
[[menu]]
id = "meins"
title = "Meine Sachen"
subtitle = "steht oben in der Titelzeile"

[[menu.items]]
heading = "Server"                 # nur eine Trennzeile

[[menu.items]]
key   = "d"                        # Hotkey
icon  = "▲"
label = "Deploy"
desc  = "Baut und schiebt auf Produktion."
run   = "make build && make deploy"
confirm = "Wirklich auf Produktion?"
requires = ["make"]                # grau, wenn make fehlt
tags  = ["gefaehrlich"]            # rot markiert, Enter bestätigt nicht

[[menu.items]]
key   = "L"
label = "Logs ansehen"
run   = "journalctl -u {dienst} -f"
interactive = true                 # bekommt das ganze Terminal
[[menu.items.prompts]]
name  = "dienst"                   # Platzhalter {dienst}
label = "Welcher Dienst?"
default = "nginx"
```

Felder eines Eintrags:

| Feld | Bedeutung |
|---|---|
| `label` | Anzeigename (Pflicht) |
| `key` | Hotkey, ein Zeichen. Nicht benutzen: `q` `/` `?` `!` `*` |
| `icon`, `desc` | Symbol und Beschreibung |
| `run` | Shell-Befehl, auch mehrzeilig mit `"""…"""` |
| `goto` | `id` eines anderen `[[menu]]` → Untermenü |
| `builtin` | `favorites`, `history`, `browse`, `shell`, `palette`, `help`, `theme`, `reload`, `edit_config`, `quit` |
| `chdir` | Verzeichnis wechseln |
| `cwd` | Arbeitsverzeichnis nur für diesen Befehl |
| `interactive` | `true` für Programme, die das Terminal brauchen (`vim`, `top`, `ssh`, `docker exec -it`) |
| `confirm` | `true` oder eigener Text → Rückfrage |
| `requires` | Liste von Programmen, die da sein müssen |
| `tags` | kleine Badges; `gefaehrlich` macht den Eintrag rot |
| `prompts` | Eingabefelder; `{name}` im Befehl wird ersetzt |
| `heading` | Trennzeile statt Eintrag |

Zwei Regeln für `run`:

* Eingegebene Werte werden automatisch shell-sicher gequotet. Wer das nicht
  will (Zahlen, Teile eines Wortes), setzt im Prompt `quote = false`.
* Geschweifte Klammern, die stehen bleiben sollen, doppelt schreiben:
  `docker ps --format '{{{{.Names}}}}'`.

Prüfen lässt sich eine Konfiguration ohne Start:

```bash
ci --check        # Menüs, Anzahl Einträge, doppelte oder belegte Hotkeys
```

## Mitgelieferte Menüs

Git (Status, Diff, Log-Graph, Commit, Branches, Remote, Stash) · Docker
(Container, Logs, Shell hinein, Compose, Prune) · Entwicklung (Tests, Linter,
make, npm-Skripte, Versionen, venv) · System (Überblick, Platten, Speicher,
Dienste, Journal) · Netzwerk (Adressen, offene Ports, DNS, Ping, HTTP-Check) ·
Dateien (suchen, durchsuchen, Platzfresser, ansehen, bearbeiten) · Prozesse
(Top-Listen, suchen, beenden) — zusammen über 100 Befehle.

Dazu Favoriten (`*`), Historie (jeder Befehl wird mitgeschrieben und ist mit
`⏎` wieder startbar) und ein Ordner-Browser.

## Optionen

```
ci --ascii          nur ASCII-Zeichen (alte Konsolen, 8 Farben)
ci --unicode        Unicode erzwingen
ci --theme NAME     nord | violet | ember | matrix | mono
ci --no-detail      rechtes Panel aus
ci --config PFAD    andere menu.toml
ci --check          Konfiguration prüfen
ci --dump-config    Standard-Konfiguration ausgeben
```

## Wo liegt was

| Pfad | Inhalt |
|---|---|
| `~/.config/ci-shell/menu.toml` | deine Menüs |
| `~/.config/ci-shell/state.json` | Favoriten, Farbschema, Nutzungszähler |
| `~/.config/ci-shell/history.log` | ausgeführte Befehle mit Zeit, Verzeichnis, Exit-Code |
| `~/.config/ci-shell/output/` | mit `s` gespeicherte Ausgaben |
| `~/.config/ci-shell/shell-init.sh` | Shell-Funktion für den Verzeichniswechsel |

Mit `CI_SHELL_CONFIG=/pfad` lässt sich alles davon woandershin legen — praktisch
für ein zweites, projektbezogenes Setup.
