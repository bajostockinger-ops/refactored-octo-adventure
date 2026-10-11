#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI  --  Command Interface.

Eine tastaturgesteuerte, menuebasierte Shell-Oberflaeche fuer das Terminal.
Keine Abhaengigkeiten ausser der Python-Standardbibliothek (curses, tomllib).

Start:   ./ci.py
Config:  ~/.config/ci-shell/menu.toml   (wird beim ersten Start angelegt)
"""

from __future__ import annotations

import curses
import json
import locale
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
try:
    import tomllib                      # Python 3.11+
except ModuleNotFoundError:             # aeltere Versionen: pip install tomli
    try:
        import tomli as tomllib         # type: ignore[no-redef]
    except ModuleNotFoundError:
        sys.stderr.write(
            "CI braucht Python 3.11+ oder das Paket 'tomli'.\n"
            "  python3 -m pip install --user tomli\n")
        raise SystemExit(2)
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "1.0.0"
APPNAME = "ci-shell"

# --------------------------------------------------------------------------- #
#  Pfade
# --------------------------------------------------------------------------- #

def _config_dir() -> Path:
    env = os.environ.get("CI_SHELL_CONFIG")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base).expanduser() / APPNAME


CONFIG_DIR = _config_dir()
MENU_FILE = CONFIG_DIR / "menu.toml"
STATE_FILE = CONFIG_DIR / "state.json"
HISTORY_FILE = CONFIG_DIR / "history.log"
OUTPUT_DIR = CONFIG_DIR / "output"

# --------------------------------------------------------------------------- #
#  Glyphen -- Unicode oder ASCII, je nach Terminal
# --------------------------------------------------------------------------- #

GLYPHS_UNICODE = {
    "tl": "╭", "tr": "╮", "bl": "╰", "br": "╯",
    "h": "─", "v": "│",
    "ltee": "├", "rtee": "┤", "ttee": "┬", "btee": "┴",
    "sel": "▸", "home": "⌂", "sep": "›", "branch": "⎇",
    "dot": "●", "ok": "✓", "err": "✗", "spin": "⟳",
    "star": "★", "nostar": "☆", "arrow": "→", "ell": "…",
    "up": "↑", "down": "↓", "enter": "⏎", "bs": "⌫",
    "lock": "◆", "bullet": "·", "block": "█", "shade": "▒",
    "folder": "▸", "cmd": "$", "tri": "▶", "clock": "◔",
}

GLYPHS_ASCII = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|",
    "ltee": "+", "rtee": "+", "ttee": "+", "btee": "+",
    "sel": ">", "home": "~", "sep": ">", "branch": "@",
    "dot": "*", "ok": "+", "err": "x", "spin": "*",
    "star": "*", "nostar": "-", "arrow": "->", "ell": "...",
    "up": "^", "down": "v", "enter": "RET", "bs": "BS",
    "lock": "!", "bullet": ".", "block": "#", "shade": ":",
    "folder": ">", "cmd": "$", "tri": ">", "clock": "o",
}


def pick_glyphs(mode: str = "auto") -> dict:
    if mode == "ascii":
        return dict(GLYPHS_ASCII)
    if mode == "unicode":
        return dict(GLYPHS_UNICODE)
    enc = (locale.getpreferredencoding(False) or "").lower()
    term = os.environ.get("TERM", "")
    if "utf" in enc and term not in ("linux", "dumb", "vt100", "vt102", ""):
        return dict(GLYPHS_UNICODE)
    return dict(GLYPHS_ASCII)


# --------------------------------------------------------------------------- #
#  Farben / Themes
#
#  Themes werden in 256-Farben-Indizes definiert und bei Terminals mit
#  weniger Farben automatisch heruntergerechnet.  bg = -1 bedeutet:
#  Hintergrund des Terminals durchlassen.
# --------------------------------------------------------------------------- #

THEMES: dict[str, dict] = {
    "nord": {
        "border":   (24,  -1),
        "border_hi":(110, -1),
        "title":    (159, -1),
        "accent":   (110, -1),
        "accent2":  (180, -1),
        "text":     (252, -1),
        "dim":      (243, -1),
        "faint":    (239, -1),
        "sel":      (235, 110),
        "sel_dim":  (24,  110),
        "ok":       (114, -1),
        "warn":     (179, -1),
        "err":      (203, -1),
        "badge":    (235, 180),
        "key":      (223, -1),
        "head":     (159, -1),
        "path":     (152, -1),
        "cmd":      (150, -1),
    },
    "mono": {
        "border":   (240, -1),
        "border_hi":(250, -1),
        "title":    (255, -1),
        "accent":   (255, -1),
        "accent2":  (250, -1),
        "text":     (252, -1),
        "dim":      (245, -1),
        "faint":    (240, -1),
        "sel":      (234, 250),
        "sel_dim":  (238, 250),
        "ok":       (255, -1),
        "warn":     (250, -1),
        "err":      (255, -1),
        "badge":    (234, 250),
        "key":      (255, -1),
        "head":     (255, -1),
        "path":     (250, -1),
        "cmd":      (250, -1),
    },
    "ember": {
        "border":   (52,  -1),
        "border_hi":(209, -1),
        "title":    (223, -1),
        "accent":   (209, -1),
        "accent2":  (173, -1),
        "text":     (252, -1),
        "dim":      (243, -1),
        "faint":    (238, -1),
        "sel":      (235, 209),
        "sel_dim":  (52,  209),
        "ok":       (108, -1),
        "warn":     (221, -1),
        "err":      (196, -1),
        "badge":    (235, 223),
        "key":      (229, -1),
        "head":     (216, -1),
        "path":     (180, -1),
        "cmd":      (151, -1),
    },
    "matrix": {
        "border":   (22,  -1),
        "border_hi":(77,  -1),
        "title":    (120, -1),
        "accent":   (77,  -1),
        "accent2":  (114, -1),
        "text":     (252, -1),
        "dim":      (65,  -1),
        "faint":    (238, -1),
        "sel":      (232, 77),
        "sel_dim":  (22,  77),
        "ok":       (82,  -1),
        "warn":     (184, -1),
        "err":      (203, -1),
        "badge":    (232, 120),
        "key":      (157, -1),
        "head":     (120, -1),
        "path":     (108, -1),
        "cmd":      (150, -1),
    },
    "violet": {
        "border":   (54,  -1),
        "border_hi":(141, -1),
        "title":    (189, -1),
        "accent":   (141, -1),
        "accent2":  (176, -1),
        "text":     (252, -1),
        "dim":      (244, -1),
        "faint":    (238, -1),
        "sel":      (234, 141),
        "sel_dim":  (54,  141),
        "ok":       (114, -1),
        "warn":     (221, -1),
        "err":      (204, -1),
        "badge":    (234, 189),
        "key":      (225, -1),
        "head":     (183, -1),
        "path":     (182, -1),
        "cmd":      (151, -1),
    },
}

THEME_ORDER = ["nord", "violet", "ember", "matrix", "mono"]

# Deckender Hintergrund je Theme. Ohne ihn laesst CI den Terminal-Hintergrund
# durch -- schoen bei einfarbigen Terminals, unruhig bei transparenten.
THEME_BG = {"nord": 235, "violet": 234, "ember": 233, "matrix": 232, "mono": 234}

# Standard-ANSI-Naeherung fuer 256-Farben, wenn das Terminal nur 8/16 kann.
_CUBE = [0, 95, 135, 175, 215, 255]


def _rgb256(c: int) -> tuple[int, int, int]:
    if c < 16:
        base = [(0, 0, 0), (170, 0, 0), (0, 170, 0), (170, 85, 0),
                (0, 0, 170), (170, 0, 170), (0, 170, 170), (170, 170, 170),
                (85, 85, 85), (255, 85, 85), (85, 255, 85), (255, 255, 85),
                (85, 85, 255), (255, 85, 255), (85, 255, 255), (255, 255, 255)]
        return base[c]
    if c < 232:
        c -= 16
        return (_CUBE[c // 36], _CUBE[(c % 36) // 6], _CUBE[c % 6])
    v = 8 + (c - 232) * 10
    return (v, v, v)


def _down(c: int, colors: int) -> tuple[int, bool]:
    """256-Farbe auf das vorhandene Spektrum abbilden -> (index, bold)."""
    if c < 0:
        return (-1, False)
    if colors >= 256:
        return (c, False)
    r, g, b = _rgb256(c)
    best, bestd = 0, 1 << 30
    for i in range(8):
        rr, gg, bb = _rgb256(i if i else 0) if False else _rgb256(i)
        d = (r - rr) ** 2 + (g - gg) ** 2 + (b - bb) ** 2
        if d < bestd:
            best, bestd = i, d
    bright = (r + g + b) > 420
    if colors >= 16 and bright:
        return (best + 8, False)
    return (best, bright)


class Palette:
    """Verwaltet curses-Farbpaare fuer die semantischen Rollen eines Themes."""

    def __init__(self, theme: str = "nord", opaque: bool = False):
        self.pairs: dict[str, int] = {}
        self.extra: dict[tuple[int, int], int] = {}
        self.next_pair = 1
        self.colors = 0
        self.ok = False
        self.opaque = opaque
        self.theme = theme if theme in THEMES else "nord"
        self.load(self.theme)

    @property
    def base_bg(self) -> int:
        return THEME_BG.get(self.theme, 235) if self.opaque else -1

    def load(self, theme: str) -> None:
        self.theme = theme if theme in THEMES else "nord"
        self.pairs.clear()
        self.extra.clear()
        self.next_pair = 1
        if not self.ok:
            return
        spec = THEMES[self.theme]
        fallback = self.base_bg
        for role, (fg, bg) in spec.items():
            f, bold = _down(fg, self.colors)
            b, _ = _down(bg if bg != -1 else fallback, self.colors)
            pid = self._alloc(f, b)
            self.pairs[role] = curses.color_pair(pid) | (curses.A_BOLD if bold else 0)

    def _alloc(self, fg: int, bg: int) -> int:
        key = (fg, bg)
        if key in self.extra:
            return self.extra[key]
        pid = self.next_pair
        self.next_pair += 1
        try:
            curses.init_pair(pid, fg, bg)
        except curses.error:
            return 0
        self.extra[key] = pid
        return pid

    def start(self) -> None:
        try:
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            self.colors = curses.COLORS
            self.ok = True
        except Exception:
            self.ok = False
            self.colors = 0
        self.load(self.theme)

    def __call__(self, role: str, *mods) -> int:
        attr = self.pairs.get(role, 0)
        for m in mods:
            attr |= m
        return attr

    def ansi(self, fg: int, bold: bool = False, dim: bool = False,
             under: bool = False, rev: bool = False) -> int:
        """Attribut fuer ANSI-Ausgabefarben im Pager."""
        if not self.ok or fg < 0:
            a = self.pairs.get("text", 0)
        else:
            f, b2 = _down(fg, self.colors)
            b, _ = _down(self.base_bg, self.colors)
            a = curses.color_pair(self._alloc(f, b)) | (curses.A_BOLD if b2 else 0)
        if bold:
            a |= curses.A_BOLD
        if dim:
            a |= curses.A_DIM
        if under:
            a |= curses.A_UNDERLINE
        if rev:
            a |= curses.A_REVERSE
        return a


# --------------------------------------------------------------------------- #
#  Text-Helfer
# --------------------------------------------------------------------------- #

_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_OTHER_ESC = re.compile(r"\x1b[@-Z\\-_]")


def strip_ansi(s: str) -> str:
    s = _OSC.sub("", s)
    s = _CSI.sub("", s)
    return _OTHER_ESC.sub("", s)


def sanitize(s: str) -> str:
    """Steuerzeichen entfernen, Tabs expandieren -- curses mag die nicht."""
    s = s.replace("\r", "").expandtabs(8)
    return "".join(ch if (ch >= " " or ch == " ") and ch != "\x7f" else "?" for ch in s)


def ell(s: str, width: int, g: dict) -> str:
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    e = g["ell"]
    if width <= len(e):
        return s[:width]
    return s[: width - len(e)] + e


def ell_left(s: str, width: int, g: dict) -> str:
    """Links kuerzen -- gut fuer Pfade."""
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    e = g["ell"]
    if width <= len(e):
        return s[-width:]
    return e + s[-(width - len(e)):]


def wrap(s: str, width: int) -> list[str]:
    if width <= 1:
        return []
    out: list[str] = []
    for para in s.split("\n"):
        if not para:
            out.append("")
            continue
        line = ""
        for word in para.split(" "):
            while len(word) > width:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:width])
                word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def short_path(p: str) -> str:
    home = str(Path.home())
    if p == home:
        return "~"
    if p.startswith(home + os.sep):
        return "~" + p[len(home):]
    return p


def human_ms(ms: float) -> str:
    if ms < 1000:
        return "%dms" % int(ms)
    if ms < 60_000:
        return "%.1fs" % (ms / 1000.0)
    m, s = divmod(int(ms / 1000), 60)
    return "%dm%02ds" % (m, s)


def fuzzy(needle: str, hay: str) -> int | None:
    """Subsequenz-Match mit Score (hoeher = besser) oder None."""
    if not needle:
        return 0
    n, h = needle.lower(), hay.lower()
    i = 0
    score = 0
    streak = 0
    for pos, ch in enumerate(h):
        if i < len(n) and ch == n[i]:
            i += 1
            streak += 1
            score += 10 + streak * 4
            if pos == 0 or h[pos - 1] in " /-_.:":
                score += 15
        else:
            streak = 0
    if i < len(n):
        return None
    return score - len(hay) // 4


_which_cache: dict[str, bool] = {}


def have(prog: str) -> bool:
    if prog not in _which_cache:
        _which_cache[prog] = shutil.which(prog) is not None
    return _which_cache[prog]


# --------------------------------------------------------------------------- #
#  Datenmodell
# --------------------------------------------------------------------------- #

@dataclass
class Prompt:
    name: str
    label: str = ""
    default: str = ""
    optional: bool = False
    quote: bool = True


@dataclass
class Item:
    label: str = ""
    key: str = ""
    icon: str = ""
    desc: str = ""
    heading: str = ""          # Gruppen-Trenner statt echtem Eintrag
    goto: str = ""             # Untermenue
    run: str = ""              # Shell-Befehl
    builtin: str = ""          # eingebaute Aktion
    chdir: str = ""            # Verzeichnis wechseln
    cwd: str = ""              # Arbeitsverzeichnis fuer run
    interactive: bool = False  # Terminal voll uebergeben (vim, top, ssh ...)
    confirm: str = ""          # Rueckfrage-Text ("true" -> Standardtext)
    requires: list[str] = field(default_factory=list)
    prompts: list[Prompt] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    menu_id: str = ""

    @property
    def is_heading(self) -> bool:
        return bool(self.heading)

    @property
    def uid(self) -> str:
        return "%s/%s" % (self.menu_id, self.key or self.label)

    @property
    def kind(self) -> str:
        if self.goto:
            return "menu"
        if self.builtin:
            return "builtin"
        if self.chdir:
            return "chdir"
        if self.run:
            return "cmd"
        return "noop"

    @property
    def missing(self) -> list[str]:
        return [r for r in self.requires if not have(r)]


@dataclass
class Menu:
    id: str
    title: str = ""
    subtitle: str = ""
    items: list[Item] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Default-Konfiguration (wird beim ersten Start nach ~/.config geschrieben)
# --------------------------------------------------------------------------- #

DEFAULT_MENU = r'''
# ===========================================================================
#  CI  --  Menue-Konfiguration
#
#  Aufbau:
#    [[menu]]            -> ein Bildschirm / eine Ebene
#    [[menu.items]]      -> ein Eintrag darin
#
#  Felder eines Eintrags:
#    label        Anzeigename                     (Pflicht)
#    key          Hotkey, ein Zeichen             ("s", "g", ...)
#    icon         ein Zeichen als Symbol
#    desc         Beschreibung fuer das rechte Panel
#    run          Shell-Befehl
#    goto         id eines anderen [[menu]]
#    chdir        Verzeichnis wechseln
#    builtin      eingebaute Aktion: favorites|history|browse|shell|help|
#                 palette|theme|reload|edit_config|quit
#    cwd          Arbeitsverzeichnis fuer run
#    interactive  true  -> Befehl bekommt das ganze Terminal (vim, top, ssh)
#    confirm      true oder Text -> Rueckfrage vor Ausfuehrung
#    requires     ["docker"] -> Eintrag ist grau, wenn Programm fehlt
#    tags         ["lesen"] -> kleine Badges
#    heading      Trennzeile (ohne label/run)
#    prompts      Eingabefelder, Platzhalter {name} im Befehl
#
#  Hotkeys bitte NICHT benutzen:  q  /  ?  !  *   (global belegt)
# ===========================================================================

[ui]
theme  = "nord"      # nord | violet | ember | matrix | mono
opaque = false       # true = eigener Hintergrund statt des Terminal-
                     # hintergrunds. Bei transparenten Terminals besser.
                     # Umschalten im Betrieb: Strg-B
glyphs = "auto"      # auto | unicode | ascii
clock  = true
detail = true        # rechtes Detail-Panel
banner = "CI"

# ---------------------------------------------------------------- Hauptmenue
[[menu]]
id = "root"
title = "Haupt"
subtitle = "Alles von hier aus"

[[menu.items]]
heading = "Werkzeuge"

[[menu.items]]
key = "g"
icon = "⎇"
label = "Git"
desc = "Status, Diff, Commit, Branches, Remotes, Stash."
goto = "git"
requires = ["git"]

[[menu.items]]
key = "d"
icon = "▣"
label = "Docker"
desc = "Container, Images, Compose, Logs, Aufraeumen."
goto = "docker"
requires = ["docker"]

[[menu.items]]
key = "e"
icon = "⚙"
label = "Entwicklung"
desc = "Tests, Linter, Build, Pakete, Projekt starten."
goto = "dev"

[[menu.items]]
key = "y"
icon = "☸"
label = "System"
desc = "Last, Speicher, Platten, Dienste, Kernel-Logs."
goto = "system"

[[menu.items]]
key = "n"
icon = "⌖"
label = "Netzwerk"
desc = "Adressen, offene Ports, DNS, Ping, HTTP-Checks."
goto = "net"

[[menu.items]]
key = "f"
icon = "▱"
label = "Dateien"
desc = "Auflisten, suchen, durchsuchen, Platzfresser finden."
goto = "files"

[[menu.items]]
key = "p"
icon = "⁂"
label = "Prozesse"
desc = "Laufende Prozesse ansehen, sortieren, beenden."
goto = "proc"

[[menu.items]]
key = "k"
icon = "❖"
label = "Pakete"
desc = "Suchen, installieren, aktualisieren, aufraeumen (apt)."
goto = "pakete"
requires = ["apt"]

[[menu.items]]
key = "v"
icon = "◉"
label = "Dienste"
desc = "systemd: starten, stoppen, Status, Journal, Bootzeit."
goto = "dienste"
requires = ["systemctl"]

[[menu.items]]
key = "s"
icon = "⟶"
label = "SSH und Fernzugriff"
desc = "Verbinden, Schluessel verwalten, Dateien uebertragen."
goto = "ssh"
requires = ["ssh"]

[[menu.items]]
key = "i"
icon = "≋"
label = "WLAN und Verbindungen"
desc = "Netze suchen, verbinden, Geraete und DNS pruefen."
goto = "wlan"
requires = ["nmcli"]

[[menu.items]]
key = "b"
icon = "☸"
label = "Hardware"
desc = "Platten, USB, PCI, CPU, Temperatur, Akku."
goto = "hardware"

[[menu.items]]
key = "t"
icon = "≡"
label = "Text und Daten"
desc = "Suchen, ersetzen, zaehlen, sortieren, JSON, CSV, vergleichen."
goto = "text"

[[menu.items]]
key = "z"
icon = "⧉"
label = "Archive"
desc = "Packen, entpacken, hineinschauen."
goto = "archive"

[[menu.items]]
key = "m"
icon = "▷"
label = "Medien"
desc = "Video, Audio und Bilder umwandeln und zuschneiden."
goto = "medien"

[[menu.items]]
heading = "Schnellzugriff"

[[menu.items]]
key = "a"
icon = "★"
label = "Favoriten"
desc = "Mit * markierte Befehle. Alles an einem Ort."
builtin = "favorites"

[[menu.items]]
key = "h"
icon = "◔"
label = "Historie"
desc = "Zuletzt ausgefuehrte Befehle, mit Enter nochmal starten."
builtin = "history"

[[menu.items]]
key = "w"
icon = "⌂"
label = "Verzeichnis wechseln"
desc = "Ordner-Browser. Alle folgenden Befehle laufen dort."
builtin = "browse"

[[menu.items]]
key = "x"
icon = "$"
label = "Freier Shell-Befehl"
desc = "Einzeiler eingeben und ausfuehren, Ausgabe im Pager."
builtin = "shell"

[[menu.items]]
key = "c"
icon = "✎"
label = "Konfiguration bearbeiten"
desc = "menu.toml im $EDITOR oeffnen. Danach laedt CI neu."
builtin = "edit_config"

# --------------------------------------------------------------------- Git
[[menu]]
id = "git"
title = "Git"
subtitle = "Repository im aktuellen Verzeichnis"

[[menu.items]]
heading = "Ansehen"

[[menu.items]]
key = "s"
icon = "●"
label = "Status"
desc = "Kurzer Status inklusive Branch und Tracking."
run = "git -c color.ui=always status -sb"
tags = ["lesen"]

[[menu.items]]
key = "d"
icon = "±"
label = "Diff (nicht gestaged)"
run = "git --no-pager diff --color=always --stat && echo && git --no-pager diff --color=always"
tags = ["lesen"]

[[menu.items]]
key = "i"
icon = "±"
label = "Diff (gestaged)"
run = "git --no-pager diff --cached --color=always --stat && echo && git --no-pager diff --cached --color=always"
tags = ["lesen"]

[[menu.items]]
key = "l"
icon = "≣"
label = "Log (Graph)"
desc = "Letzte 60 Commits als Graph."
run = "git --no-pager log --color=always --graph --abbrev-commit --decorate -n 60 --format=format:'%C(bold blue)%h%C(reset) %C(dim white)%ar%C(reset) %C(white)%s%C(reset) %C(dim white)-- %an%C(reset)%C(auto)%d%C(reset)'"
tags = ["lesen"]

[[menu.items]]
key = "v"
icon = "≣"
label = "Letzter Commit im Detail"
run = "git --no-pager show --color=always --stat HEAD"
tags = ["lesen"]

[[menu.items]]
key = "m"
icon = "▤"
label = "Datei-Historie"
run = "git --no-pager log --color=always --follow -p -n 20 -- {datei}"
tags = ["lesen"]
[[menu.items.prompts]]
name = "datei"
label = "Pfad der Datei"

[[menu.items]]
heading = "Aendern"

[[menu.items]]
key = "A"
icon = "+"
label = "Alles stagen"
run = "git add -A && git -c color.ui=always status -sb"

[[menu.items]]
key = "P"
icon = "+"
label = "Interaktiv stagen"
desc = "git add -p -- Haeppchenweise auswaehlen."
run = "git add -p"
interactive = true

[[menu.items]]
key = "C"
icon = "✓"
label = "Commit"
desc = "Stagen und committen in einem Schritt."
run = "git add -A && git commit -m {nachricht} && git -c color.ui=always log --oneline -n 3"
[[menu.items.prompts]]
name = "nachricht"
label = "Commit-Nachricht"

[[menu.items]]
key = "N"
icon = "✓"
label = "Commit nachbessern"
desc = "--amend, Nachricht im Editor."
run = "git commit --amend"
interactive = true

[[menu.items]]
key = "u"
icon = "-"
label = "Letzten Commit zuruecknehmen"
desc = "git reset --soft HEAD~1 -- Aenderungen bleiben erhalten."
run = "git reset --soft HEAD~1 && git -c color.ui=always status -sb"
confirm = "Letzten Commit aufloesen? Dateien bleiben unveraendert."

[[menu.items]]
key = "X"
icon = "✗"
label = "Alle Aenderungen verwerfen"
desc = "git reset --hard + clean -fd. Nicht umkehrbar."
run = "git reset --hard && git clean -fd"
confirm = "ALLE lokalen Aenderungen und neuen Dateien loeschen?"
tags = ["gefaehrlich"]

[[menu.items]]
heading = "Mehr"

[[menu.items]]
key = "b"
icon = "⎇"
label = "Branches"
goto = "git_branch"

[[menu.items]]
key = "r"
icon = "⇅"
label = "Remote"
goto = "git_remote"

[[menu.items]]
key = "t"
icon = "⧉"
label = "Stash"
goto = "git_stash"

# ------------------------------------------------------------- Git / Branch
[[menu]]
id = "git_branch"
title = "Branches"

[[menu.items]]
key = "l"
icon = "≣"
label = "Liste (lokal + remote)"
run = "git --no-pager branch -vv --color=always --all"
tags = ["lesen"]

[[menu.items]]
key = "s"
icon = "→"
label = "Wechseln"
run = "git switch {branch} && git -c color.ui=always status -sb"
[[menu.items.prompts]]
name = "branch"
label = "Branch-Name"

[[menu.items]]
key = "n"
icon = "+"
label = "Neu anlegen und wechseln"
run = "git switch -c {branch} && git -c color.ui=always status -sb"
[[menu.items.prompts]]
name = "branch"
label = "Neuer Branch-Name"

[[menu.items]]
key = "m"
icon = "⑂"
label = "Branch hereinmergen"
run = "git merge {branch}"
[[menu.items.prompts]]
name = "branch"
label = "Welchen Branch mergen?"

[[menu.items]]
key = "r"
icon = "⑂"
label = "Auf Branch rebasen"
run = "git rebase {branch}"
confirm = true
[[menu.items.prompts]]
name = "branch"
label = "Basis-Branch"

[[menu.items]]
key = "D"
icon = "✗"
label = "Branch loeschen"
run = "git branch -D {branch}"
confirm = "Branch wirklich loeschen?"
[[menu.items.prompts]]
name = "branch"
label = "Branch-Name"

[[menu.items]]
key = "c"
icon = "◔"
label = "Zuletzt benutzte Branches"
run = "git --no-pager reflog --date=relative --color=always | grep -oP 'moving from \\K[^ ]+' | awk '!a[$0]++' | head -15"
tags = ["lesen"]

# ------------------------------------------------------------- Git / Remote
[[menu]]
id = "git_remote"
title = "Remote"

[[menu.items]]
key = "l"
icon = "≣"
label = "Remotes anzeigen"
run = "git remote -v"
tags = ["lesen"]

[[menu.items]]
key = "f"
icon = "↓"
label = "Fetch (alles, mit prune)"
run = "git fetch --all --prune --progress"

[[menu.items]]
key = "u"
icon = "↓"
label = "Pull (rebase)"
run = "git pull --rebase --progress"

[[menu.items]]
key = "p"
icon = "↑"
label = "Push"
run = "git push --progress"

[[menu.items]]
key = "U"
icon = "↑"
label = "Push mit Upstream setzen"
run = "git push -u origin $(git branch --show-current) --progress"

[[menu.items]]
key = "F"
icon = "↑"
label = "Force-Push (mit Lease)"
run = "git push --force-with-lease --progress"
confirm = "Force-Push -- Remote-Historie wird ueberschrieben. Sicher?"
tags = ["gefaehrlich"]

[[menu.items]]
key = "d"
icon = "±"
label = "Diff gegen Upstream"
run = "git --no-pager diff --color=always @{{u}}...HEAD --stat"
tags = ["lesen"]

# -------------------------------------------------------------- Git / Stash
[[menu]]
id = "git_stash"
title = "Stash"

[[menu.items]]
key = "l"
icon = "≣"
label = "Liste"
run = "git --no-pager stash list --color=always"
tags = ["lesen"]

[[menu.items]]
key = "s"
icon = "+"
label = "Aenderungen wegpacken"
run = "git stash push -u -m {name} && git stash list"
[[menu.items.prompts]]
name = "name"
label = "Beschreibung"
default = "wip"

[[menu.items]]
key = "p"
icon = "→"
label = "Letzten Stash zurueckholen"
run = "git stash pop && git -c color.ui=always status -sb"

[[menu.items]]
key = "v"
icon = "±"
label = "Stash ansehen"
run = "git --no-pager stash show -p --color=always stash@{{{nr}}}"
tags = ["lesen"]
[[menu.items.prompts]]
name = "nr"
label = "Stash-Nummer"
default = "0"
quote = false

[[menu.items]]
key = "D"
icon = "✗"
label = "Alle Stashes loeschen"
run = "git stash clear"
confirm = "Alle Stashes endgueltig loeschen?"
tags = ["gefaehrlich"]

# ------------------------------------------------------------------- Docker
[[menu]]
id = "docker"
title = "Docker"
requires = ["docker"]

[[menu.items]]
heading = "Container"

[[menu.items]]
key = "s"
icon = "●"
label = "Laufende Container"
run = "docker ps --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Image}}}}\\t{{{{.Ports}}}}'"
requires = ["docker"]
tags = ["lesen"]

[[menu.items]]
key = "A"
icon = "○"
label = "Alle Container"
run = "docker ps -a --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Image}}}}'"
requires = ["docker"]
tags = ["lesen"]

[[menu.items]]
key = "L"
icon = "≣"
label = "Logs folgen"
run = "docker logs -f --tail 200 {container}"
interactive = true
requires = ["docker"]
[[menu.items.prompts]]
name = "container"
label = "Container-Name"

[[menu.items]]
key = "E"
icon = "$"
label = "Shell im Container"
run = "docker exec -it {container} sh -c 'command -v bash >/dev/null && exec bash || exec sh'"
interactive = true
requires = ["docker"]
[[menu.items.prompts]]
name = "container"
label = "Container-Name"

[[menu.items]]
key = "t"
icon = "◔"
label = "Live-Statistik"
run = "docker stats"
interactive = true
requires = ["docker"]

[[menu.items]]
key = "R"
icon = "⟳"
label = "Container neu starten"
run = "docker restart {container}"
requires = ["docker"]
confirm = true
[[menu.items.prompts]]
name = "container"
label = "Container-Name"

[[menu.items]]
heading = "Images und Compose"

[[menu.items]]
key = "i"
icon = "▣"
label = "Images"
run = "docker images --format 'table {{{{.Repository}}}}:{{{{.Tag}}}}\\t{{{{.Size}}}}\\t{{{{.CreatedSince}}}}'"
requires = ["docker"]
tags = ["lesen"]

[[menu.items]]
key = "u"
icon = "↑"
label = "Compose hochfahren"
run = "docker compose up -d && docker compose ps"
requires = ["docker"]

[[menu.items]]
key = "D"
icon = "↓"
label = "Compose runterfahren"
run = "docker compose down"
requires = ["docker"]
confirm = true

[[menu.items]]
key = "c"
icon = "≣"
label = "Compose-Logs folgen"
run = "docker compose logs -f --tail 200"
interactive = true
requires = ["docker"]

[[menu.items]]
key = "v"
icon = "⧉"
label = "Volumes und Netze"
run = "echo '== Volumes =='; docker volume ls; echo; echo '== Netze =='; docker network ls"
requires = ["docker"]
tags = ["lesen"]

[[menu.items]]
key = "G"
icon = "✗"
label = "Aufraeumen (prune)"
desc = "Ungenutzte Container, Netze, Images und Build-Cache loeschen."
run = "docker system prune -af && docker system df"
confirm = "Alle ungenutzten Docker-Objekte loeschen?"
requires = ["docker"]
tags = ["gefaehrlich"]

# -------------------------------------------------------------- Entwicklung
[[menu]]
id = "dev"
title = "Entwicklung"
subtitle = "Projekt im aktuellen Verzeichnis"

[[menu.items]]
heading = "Pruefen"

[[menu.items]]
key = "t"
icon = "✓"
label = "Tests"
desc = "Erkennt pytest, npm test, make test oder cargo test selbst."
run = """
if [ -f pytest.ini ] || [ -f pyproject.toml ] || ls tests/test_*.py >/dev/null 2>&1; then
  command -v pytest >/dev/null && exec pytest -q --color=yes
fi
if [ -f package.json ] && grep -q '"test"' package.json; then exec npm test; fi
if [ -f Cargo.toml ]; then exec cargo test --color always; fi
if [ -f Makefile ] && grep -q '^test:' Makefile; then exec make test; fi
echo "Kein Test-Setup gefunden."
"""

[[menu.items]]
key = "L"
icon = "◆"
label = "Linter"
run = """
ran=0
command -v ruff  >/dev/null && { echo '== ruff =='; ruff check . ; ran=1; }
command -v eslint >/dev/null && [ -f package.json ] && { echo '== eslint =='; npx eslint . ; ran=1; }
command -v shellcheck >/dev/null && ls *.sh >/dev/null 2>&1 && { echo '== shellcheck =='; shellcheck *.sh; ran=1; }
[ "$ran" = 0 ] && echo "Kein Linter gefunden (ruff / eslint / shellcheck)."
"""

[[menu.items]]
key = "y"
icon = "◆"
label = "Syntax-Check Python"
run = "find . -name '*.py' -not -path './.git/*' -not -path '*/node_modules/*' -print0 | xargs -0 -r python3 -m py_compile && echo 'Alle Python-Dateien sind syntaktisch sauber.'"

[[menu.items]]
heading = "Bauen und starten"

[[menu.items]]
key = "m"
icon = "⚙"
label = "make"
run = "make {ziel}"
requires = ["make"]
[[menu.items.prompts]]
name = "ziel"
label = "Make-Ziel"
default = ""
optional = true
quote = false

[[menu.items]]
key = "M"
icon = "≣"
label = "Make-Ziele anzeigen"
run = "grep -E '^[a-zA-Z0-9_.-]+:' Makefile | cut -d: -f1 | sort -u"
requires = ["make"]
tags = ["lesen"]

[[menu.items]]
key = "r"
icon = "▶"
label = "Projekt starten"
desc = "npm run dev / make run / python main.py -- mit vollem Terminal."
run = """
if [ -f package.json ] && grep -q '"dev"' package.json; then exec npm run dev; fi
if [ -f Makefile ] && grep -q '^run:' Makefile; then exec make run; fi
if [ -f main.py ]; then exec python3 main.py; fi
if [ -f Cargo.toml ]; then exec cargo run; fi
echo "Kein Start-Befehl gefunden."
"""
interactive = true

[[menu.items]]
key = "n"
icon = "≣"
label = "npm-Skripte"
run = "node -e 'const p=require(\"./package.json\");for(const [k,v] of Object.entries(p.scripts||{}))console.log(k.padEnd(18),v)'"
requires = ["node"]
tags = ["lesen"]

[[menu.items]]
key = "N"
icon = "▶"
label = "npm-Skript starten"
run = "npm run {skript}"
requires = ["npm"]
interactive = true
[[menu.items.prompts]]
name = "skript"
label = "Skript-Name"

[[menu.items]]
heading = "Umgebung"

[[menu.items]]
key = "v"
icon = "◔"
label = "Versionen"
run = """
printf '%-12s %s\\n' 'python' "$(python3 -V 2>&1)"
printf '%-12s %s\\n' 'node'   "$(node -v 2>/dev/null || echo '-')"
printf '%-12s %s\\n' 'npm'    "$(npm -v 2>/dev/null || echo '-')"
printf '%-12s %s\\n' 'git'    "$(git --version 2>/dev/null || echo '-')"
printf '%-12s %s\\n' 'docker' "$(docker --version 2>/dev/null || echo '-')"
printf '%-12s %s\\n' 'go'     "$(go version 2>/dev/null || echo '-')"
printf '%-12s %s\\n' 'rustc'  "$(rustc --version 2>/dev/null || echo '-')"
printf '%-12s %s\\n' 'shell'  "$SHELL"
"""
tags = ["lesen"]

[[menu.items]]
key = "p"
icon = "▣"
label = "Python-Pakete"
run = "python3 -m pip list 2>/dev/null | head -60"
tags = ["lesen"]

[[menu.items]]
key = "V"
icon = "+"
label = "venv anlegen"
run = "python3 -m venv .venv && echo 'Angelegt: .venv  (aktivieren mit: source .venv/bin/activate)'"

# ------------------------------------------------------------------- System
[[menu]]
id = "system"
title = "System"

[[menu.items]]
heading = "Ueberblick"

[[menu.items]]
key = "u"
icon = "◔"
label = "Uebersicht"
desc = "Host, Kernel, Laufzeit, Last, Speicher auf einem Blick."
run = """
printf '%-10s %s\\n' 'Host'   "$(hostname)"
printf '%-10s %s\\n' 'Kernel' "$(uname -sr)"
printf '%-10s %s\\n' 'Uptime' "$(uptime -p 2>/dev/null || uptime)"
printf '%-10s %s\\n' 'Last'   "$(cat /proc/loadavg 2>/dev/null | cut -d' ' -f1-3)"
printf '%-10s %s\\n' 'CPUs'   "$(nproc 2>/dev/null)"
echo; echo '== Speicher =='; free -h 2>/dev/null || vm_stat
echo; echo '== Platten =='; df -h -x tmpfs -x devtmpfs 2>/dev/null | head -12
"""
tags = ["lesen"]

[[menu.items]]
key = "d"
icon = "▤"
label = "Plattenplatz"
run = "df -h -x tmpfs -x devtmpfs"
tags = ["lesen"]

[[menu.items]]
key = "s"
icon = "▤"
label = "Groesste Ordner hier"
run = "du -h -d 1 . 2>/dev/null | sort -hr | head -20"
tags = ["lesen"]

[[menu.items]]
key = "m"
icon = "▣"
label = "Speicher"
run = "free -h; echo; echo '== Top 10 nach RAM =='; ps -eo pid,comm,rss --sort=-rss | head -11"
tags = ["lesen"]

[[menu.items]]
key = "c"
icon = "⚙"
label = "CPU"
run = "lscpu 2>/dev/null | head -20 || sysctl -n machdep.cpu.brand_string"
tags = ["lesen"]

[[menu.items]]
heading = "Dienste und Logs"

[[menu.items]]
key = "f"
icon = "✗"
label = "Fehlgeschlagene Dienste"
run = "systemctl --failed --no-pager"
requires = ["systemctl"]
tags = ["lesen"]

[[menu.items]]
key = "a"
icon = "●"
label = "Aktive Dienste"
run = "systemctl list-units --type=service --state=running --no-pager | head -40"
requires = ["systemctl"]
tags = ["lesen"]

[[menu.items]]
key = "j"
icon = "≣"
label = "Journal folgen"
run = "journalctl -f -n 100"
interactive = true
requires = ["journalctl"]

[[menu.items]]
key = "k"
icon = "≣"
label = "Kernel-Meldungen"
run = "dmesg --color=always 2>/dev/null | tail -60 || sudo dmesg | tail -60"
tags = ["lesen"]

[[menu.items]]
key = "t"
icon = "◔"
label = "top"
run = "command -v htop >/dev/null && exec htop || exec top"
interactive = true

# ----------------------------------------------------------------- Netzwerk
[[menu]]
id = "net"
title = "Netzwerk"

[[menu.items]]
key = "a"
icon = "⌖"
label = "Adressen"
run = "ip -brief address 2>/dev/null || ifconfig"
tags = ["lesen"]

[[menu.items]]
key = "r"
icon = "→"
label = "Routen"
run = "ip route 2>/dev/null || netstat -rn"
tags = ["lesen"]

[[menu.items]]
key = "l"
icon = "●"
label = "Offene Ports"
desc = "Alles, was lokal lauscht, mit Prozess."
run = "ss -tulpn 2>/dev/null || netstat -tulpn 2>/dev/null || lsof -iTCP -sTCP:LISTEN -P -n"
tags = ["lesen"]

[[menu.items]]
key = "w"
icon = "↑"
label = "Oeffentliche IP"
run = "curl -s --max-time 8 https://ifconfig.me ; echo"
requires = ["curl"]
tags = ["lesen"]

[[menu.items]]
key = "p"
icon = "⟳"
label = "Ping"
run = "ping -c 5 {host}"
[[menu.items.prompts]]
name = "host"
label = "Host oder IP"
default = "1.1.1.1"

[[menu.items]]
key = "n"
icon = "⌖"
label = "DNS aufloesen"
run = "(command -v dig >/dev/null && dig +short {host} ANY) || getent hosts {host} || nslookup {host}"
[[menu.items.prompts]]
name = "host"
label = "Domain"

[[menu.items]]
key = "t"
icon = "→"
label = "Route verfolgen"
run = "traceroute -n {host} 2>/dev/null || tracepath {host}"
interactive = true
[[menu.items.prompts]]
name = "host"
label = "Host"

[[menu.items]]
key = "H"
icon = "◆"
label = "HTTP-Check"
desc = "Status, Zeiten und Header einer URL."
run = """
curl -sS -o /dev/null -w 'Status   %{{http_code}}\\nDNS      %{{time_namelookup}}s\\nConnect  %{{time_connect}}s\\nTLS      %{{time_appconnect}}s\\nTotal    %{{time_total}}s\\nGroesse  %{{size_download}} B\\n' {url}
echo; echo '== Header =='; curl -sSI --max-time 10 {url}
"""
requires = ["curl"]
[[menu.items.prompts]]
name = "url"
label = "URL"
default = "https://"

[[menu.items]]
key = "s"
icon = "◆"
label = "Port testen"
run = "timeout 5 bash -c '</dev/tcp/$0/$1' {host} {port} && echo 'offen  ->' {host} {port} || echo 'keine Antwort  ->' {host} {port}"
[[menu.items.prompts]]
name = "host"
label = "Host"
[[menu.items.prompts]]
name = "port"
label = "Port"
default = "443"
quote = false

# ------------------------------------------------------------------ Dateien
[[menu]]
id = "files"
title = "Dateien"

[[menu.items]]
key = "l"
icon = "≣"
label = "Auflisten"
run = "ls -lAh --color=always 2>/dev/null || ls -lAh"
tags = ["lesen"]

[[menu.items]]
key = "t"
icon = "▱"
label = "Baum"
run = "tree -L 3 -C --dirsfirst 2>/dev/null || find . -maxdepth 3 -not -path './.git*' | sort"
tags = ["lesen"]

[[menu.items]]
key = "r"
icon = "◔"
label = "Zuletzt geaendert"
run = "find . -type f -not -path './.git/*' -not -path '*/node_modules/*' -printf '%TY-%Tm-%Td %TH:%TM  %p\\n' 2>/dev/null | sort -r | head -30"
tags = ["lesen"]

[[menu.items]]
key = "b"
icon = "▤"
label = "Groesste Dateien"
run = "find . -type f -not -path './.git/*' -printf '%s\\t%p\\n' 2>/dev/null | sort -rn | head -25 | awk '{printf \"%8.1f MB  %s\\n\", $1/1048576, $2}'"
tags = ["lesen"]

[[menu.items]]
key = "n"
icon = "◆"
label = "Nach Name suchen"
run = "find . -iname '*'{name}'*' -not -path './.git/*' 2>/dev/null | head -60"
[[menu.items.prompts]]
name = "name"
label = "Namensteil"

[[menu.items]]
key = "i"
icon = "◆"
label = "Inhalt durchsuchen"
desc = "grep -rn durch alle Dateien, .git ausgenommen."
run = "grep -rnI --color=always --exclude-dir=.git --exclude-dir=node_modules -e {muster} . | head -120"
[[menu.items.prompts]]
name = "muster"
label = "Suchmuster"

[[menu.items]]
key = "v"
icon = "≣"
label = "Datei ansehen"
run = "(command -v less >/dev/null && less -R {datei}) || cat {datei}"
interactive = true
[[menu.items.prompts]]
name = "datei"
label = "Pfad"

[[menu.items]]
key = "E"
icon = "✎"
label = "Datei bearbeiten"
run = "${EDITOR:-vi} {datei}"
interactive = true
[[menu.items.prompts]]
name = "datei"
label = "Pfad"

# ----------------------------------------------------------------- Prozesse
[[menu]]
id = "proc"
title = "Prozesse"

[[menu.items]]
key = "c"
icon = "⚙"
label = "Top nach CPU"
run = "ps -eo pid,ppid,pcpu,pmem,etime,comm --sort=-pcpu | head -21"
tags = ["lesen"]

[[menu.items]]
key = "m"
icon = "▣"
label = "Top nach Speicher"
run = "ps -eo pid,ppid,pmem,rss,comm --sort=-rss | head -21"
tags = ["lesen"]

[[menu.items]]
key = "s"
icon = "◆"
label = "Prozess suchen"
run = "pgrep -a -f {muster} || echo 'nichts gefunden'"
[[menu.items.prompts]]
name = "muster"
label = "Name oder Teil der Kommandozeile"

[[menu.items]]
key = "T"
icon = "⁂"
label = "Prozessbaum"
run = "pstree -p 2>/dev/null | head -60 || ps -ejH | head -60"
tags = ["lesen"]

[[menu.items]]
key = "K"
icon = "✗"
label = "Prozess beenden (TERM)"
run = "kill {pid} && echo 'TERM an {pid} gesendet'"
confirm = true
[[menu.items.prompts]]
name = "pid"
label = "PID"
quote = false

[[menu.items]]
key = "9"
icon = "✗"
label = "Prozess hart beenden (KILL)"
run = "kill -9 {pid} && echo 'KILL an {pid} gesendet'"
confirm = "SIGKILL senden? Der Prozess kann nicht aufraeumen."
tags = ["gefaehrlich"]
[[menu.items.prompts]]
name = "pid"
label = "PID"
quote = false

[[menu.items]]
key = "o"
icon = "≣"
label = "Offene Dateien eines Prozesses"
run = "ls -l /proc/{pid}/fd 2>/dev/null | head -40 || lsof -p {pid}"
[[menu.items.prompts]]
name = "pid"
label = "PID"
quote = false
# ------------------------------------------------------------------- Pakete
[[menu]]
id = "pakete"
title = "Pakete"
subtitle = "apt -- Installieren braucht dein Passwort"

[[menu.items]]
heading = "Suchen und ansehen"

[[menu.items]]
key = "s"
icon = "◆"
label = "Paket suchen"
run = "apt-cache search {begriff} | head -40"
requires = ["apt-cache"]
[[menu.items.prompts]]
name = "begriff"
label = "Suchbegriff"

[[menu.items]]
key = "n"
icon = "≣"
label = "Paket-Info"
run = "apt-cache show {paket} | head -30"
requires = ["apt-cache"]
[[menu.items.prompts]]
name = "paket"
label = "Paketname"

[[menu.items]]
key = "l"
icon = "≣"
label = "Installierte Pakete"
run = "dpkg-query -W -f='${{Package}}\t${{Version}}\n' | sort | head -80"
requires = ["dpkg-query"]
tags = ["lesen"]

[[menu.items]]
key = "c"
icon = "◆"
label = "Anzahl installierter Pakete"
run = "dpkg-query -f '.\n' -W | wc -l"
requires = ["dpkg-query"]
tags = ["lesen"]

[[menu.items]]
key = "w"
icon = "◆"
label = "Welches Paket liefert diese Datei?"
run = "dpkg -S {datei}"
requires = ["dpkg"]
[[menu.items.prompts]]
name = "datei"
label = "Pfad oder Dateiname"

[[menu.items]]
key = "f"
icon = "≣"
label = "Dateien eines Pakets"
run = "dpkg -L {paket} | head -60"
requires = ["dpkg"]
[[menu.items.prompts]]
name = "paket"
label = "Paketname"

[[menu.items]]
key = "H"
icon = "◔"
label = "Zuletzt installiert"
run = "grep -a '^Commandline' /var/log/apt/history.log 2>/dev/null | tail -20 || echo 'Keine apt-Historie lesbar.'"
tags = ["lesen"]

[[menu.items]]
heading = "Aendern -- fragt nach dem Passwort"

[[menu.items]]
key = "u"
icon = "⟳"
label = "Paketlisten aktualisieren"
run = "sudo apt update"
interactive = true
requires = ["apt"]

[[menu.items]]
key = "U"
icon = "↑"
label = "System aktualisieren"
desc = "apt update und danach apt upgrade."
run = "sudo apt update && sudo apt upgrade"
interactive = true
requires = ["apt"]

[[menu.items]]
key = "I"
icon = "+"
label = "Paket installieren"
run = "sudo apt install {paket}"
interactive = true
requires = ["apt"]
[[menu.items.prompts]]
name = "paket"
label = "Paketname (mehrere mit Leerzeichen)"
quote = false

[[menu.items]]
key = "R"
icon = "✗"
label = "Paket entfernen"
run = "sudo apt remove {paket}"
interactive = true
confirm = "Paket wirklich entfernen?"
requires = ["apt"]
[[menu.items.prompts]]
name = "paket"
label = "Paketname"
quote = false

[[menu.items]]
key = "A"
icon = "✗"
label = "Aufraeumen"
desc = "Nicht mehr benoetigte Pakete und Paket-Cache entfernen."
run = "sudo apt autoremove && sudo apt clean && df -h / | tail -1"
interactive = true
confirm = true
requires = ["apt"]

# ------------------------------------------------------------------ Dienste
[[menu]]
id = "dienste"
title = "Dienste"
subtitle = "systemd"

[[menu.items]]
key = "l"
icon = "●"
label = "Laufende Dienste"
run = "systemctl list-units --type=service --state=running --no-pager"
requires = ["systemctl"]
tags = ["lesen"]

[[menu.items]]
key = "f"
icon = "✗"
label = "Fehlgeschlagene Dienste"
run = "systemctl --failed --no-pager"
requires = ["systemctl"]
tags = ["lesen"]

[[menu.items]]
key = "a"
icon = "≣"
label = "Beim Start aktivierte Dienste"
run = "systemctl list-unit-files --state=enabled --no-pager | head -40"
requires = ["systemctl"]
tags = ["lesen"]

[[menu.items]]
key = "s"
icon = "◆"
label = "Status eines Dienstes"
run = "systemctl status {dienst} --no-pager -l | head -40"
requires = ["systemctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

[[menu.items]]
key = "j"
icon = "≣"
label = "Journal eines Dienstes"
run = "journalctl -u {dienst} -n 200 -f"
interactive = true
requires = ["journalctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

[[menu.items]]
key = "t"
icon = "◔"
label = "Was bremst den Systemstart?"
run = "systemd-analyze && echo && systemd-analyze blame | head -20"
requires = ["systemd-analyze"]
tags = ["lesen"]

[[menu.items]]
heading = "Steuern -- fragt nach dem Passwort"

[[menu.items]]
key = "S"
icon = "▶"
label = "Dienst starten"
run = "sudo systemctl start {dienst} && systemctl status {dienst} --no-pager | head -10"
interactive = true
requires = ["systemctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

[[menu.items]]
key = "T"
icon = "■"
label = "Dienst stoppen"
run = "sudo systemctl stop {dienst}"
interactive = true
confirm = true
requires = ["systemctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

[[menu.items]]
key = "R"
icon = "⟳"
label = "Dienst neu starten"
run = "sudo systemctl restart {dienst} && systemctl status {dienst} --no-pager | head -10"
interactive = true
confirm = true
requires = ["systemctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

[[menu.items]]
key = "E"
icon = "+"
label = "Dienst beim Start aktivieren"
run = "sudo systemctl enable {dienst}"
interactive = true
requires = ["systemctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

[[menu.items]]
key = "D"
icon = "-"
label = "Dienst beim Start abschalten"
run = "sudo systemctl disable {dienst}"
interactive = true
confirm = true
requires = ["systemctl"]
[[menu.items.prompts]]
name = "dienst"
label = "Name des Dienstes"

# ---------------------------------------------------------------------- SSH
[[menu]]
id = "ssh"
title = "SSH"
subtitle = "Fernzugriff und Schluessel"

[[menu.items]]
key = "c"
icon = "⟶"
label = "Verbinden"
run = "ssh {ziel}"
interactive = true
requires = ["ssh"]
[[menu.items.prompts]]
name = "ziel"
label = "benutzer@host"

[[menu.items]]
key = "l"
icon = "≣"
label = "Bekannte Ziele"
desc = "Alles, was in ~/.ssh/config steht."
run = "grep -iE '^host ' ~/.ssh/config 2>/dev/null | sed 's/^[Hh]ost //' || echo 'Keine ~/.ssh/config vorhanden.'"
tags = ["lesen"]

[[menu.items]]
key = "t"
icon = "◆"
label = "Verbindung testen"
run = "ssh -o ConnectTimeout=6 -o BatchMode=yes {ziel} true && echo 'Verbindung steht.' || echo 'Keine Verbindung (oder Passwort noetig).'"
requires = ["ssh"]
[[menu.items.prompts]]
name = "ziel"
label = "benutzer@host"

[[menu.items]]
key = "k"
icon = "◆"
label = "Meine Schluessel"
run = "ls -l ~/.ssh/*.pub 2>/dev/null; echo; echo '== im Agenten =='; ssh-add -l 2>&1"
tags = ["lesen"]

[[menu.items]]
key = "n"
icon = "+"
label = "Neuen Schluessel erzeugen"
desc = "ed25519, der heute uebliche Typ."
run = "ssh-keygen -t ed25519 -C {kommentar}"
interactive = true
requires = ["ssh-keygen"]
[[menu.items.prompts]]
name = "kommentar"
label = "Kommentar (z. B. deine Mailadresse)"

[[menu.items]]
key = "C"
icon = "↑"
label = "Schluessel auf Server kopieren"
run = "ssh-copy-id {ziel}"
interactive = true
requires = ["ssh-copy-id"]
[[menu.items.prompts]]
name = "ziel"
label = "benutzer@host"

[[menu.items]]
key = "p"
icon = "↑"
label = "Datei hochladen"
run = "scp {datei} {ziel}"
interactive = true
requires = ["scp"]
[[menu.items.prompts]]
name = "datei"
label = "lokale Datei"
[[menu.items.prompts]]
name = "ziel"
label = "benutzer@host:/pfad/"

[[menu.items]]
key = "d"
icon = "↓"
label = "Datei holen"
run = "scp {quelle} ."
interactive = true
requires = ["scp"]
[[menu.items.prompts]]
name = "quelle"
label = "benutzer@host:/pfad/datei"

[[menu.items]]
key = "a"
icon = "◉"
label = "Schluessel in den Agenten laden"
run = "ssh-add"
interactive = true
requires = ["ssh-add"]

# --------------------------------------------------------------------- WLAN
[[menu]]
id = "wlan"
title = "WLAN"
subtitle = "NetworkManager"

[[menu.items]]
key = "s"
icon = "≋"
label = "Netze in der Umgebung"
run = "nmcli -f SSID,SIGNAL,SECURITY,CHAN device wifi list"
requires = ["nmcli"]
tags = ["lesen"]

[[menu.items]]
key = "c"
icon = "⟶"
label = "Mit Netz verbinden"
run = "nmcli --ask device wifi connect {ssid}"
interactive = true
requires = ["nmcli"]
[[menu.items.prompts]]
name = "ssid"
label = "Netzname (SSID)"

[[menu.items]]
key = "a"
icon = "◉"
label = "Aktive Verbindungen"
run = "nmcli connection show --active"
requires = ["nmcli"]
tags = ["lesen"]

[[menu.items]]
key = "g"
icon = "≣"
label = "Gespeicherte Verbindungen"
run = "nmcli connection show"
requires = ["nmcli"]
tags = ["lesen"]

[[menu.items]]
key = "d"
icon = "◆"
label = "Netzwerk-Geraete"
run = "nmcli device status"
requires = ["nmcli"]
tags = ["lesen"]

[[menu.items]]
key = "r"
icon = "⟳"
label = "WLAN aus und wieder an"
run = "nmcli radio wifi off && sleep 2 && nmcli radio wifi on && sleep 2 && nmcli radio"
requires = ["nmcli"]

[[menu.items]]
key = "x"
icon = "-"
label = "Verbindung trennen"
run = "nmcli connection down {name}"
requires = ["nmcli"]
confirm = true
[[menu.items.prompts]]
name = "name"
label = "Name der Verbindung"

[[menu.items]]
key = "i"
icon = "◆"
label = "Geht das Internet?"
desc = "Gateway, DNS und eine echte HTTPS-Anfrage."
run = """
gw=$(ip route | awk '/default/{print $3; exit}')
printf '%-10s %s\n' 'Gateway' "${gw:-keins}"
[ -n "$gw" ] && (ping -c 2 -W 2 "$gw" >/dev/null && echo '           erreichbar' || echo '           keine Antwort')
echo
echo '== DNS =='; getent hosts example.org || echo 'DNS antwortet nicht'
echo
echo '== HTTPS =='; curl -sS -o /dev/null -w 'Status %{{http_code}} in %{{time_total}}s\n' --max-time 8 https://example.org || echo 'kein Zugriff'
"""
tags = ["lesen"]

[[menu.items]]
key = "D"
icon = "≣"
label = "DNS-Einstellungen"
run = "resolvectl status 2>/dev/null | head -30 || cat /etc/resolv.conf"
tags = ["lesen"]

# ----------------------------------------------------------------- Hardware
[[menu]]
id = "hardware"
title = "Hardware"

[[menu.items]]
key = "d"
icon = "▤"
label = "Datentraeger"
run = "lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL"
requires = ["lsblk"]
tags = ["lesen"]

[[menu.items]]
key = "u"
icon = "◆"
label = "USB-Geraete"
run = "lsusb"
requires = ["lsusb"]
tags = ["lesen"]

[[menu.items]]
key = "p"
icon = "◆"
label = "PCI-Geraete"
run = "lspci"
requires = ["lspci"]
tags = ["lesen"]

[[menu.items]]
key = "c"
icon = "⚙"
label = "Prozessor"
run = "lscpu | head -25"
requires = ["lscpu"]
tags = ["lesen"]

[[menu.items]]
key = "m"
icon = "▣"
label = "Arbeitsspeicher"
run = "free -h; echo; sudo dmidecode -t memory 2>/dev/null | grep -E 'Size|Speed|Type:' | head -20"
tags = ["lesen"]

[[menu.items]]
key = "t"
icon = "◔"
label = "Temperaturen"
run = "sensors 2>/dev/null || cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{printf \"%.1f C\\n\", $1/1000}' || echo 'Keine Sensoren gefunden.'"
tags = ["lesen"]

[[menu.items]]
key = "a"
icon = "◉"
label = "Akku"
run = "upower -i $(upower -e 2>/dev/null | grep -m1 BAT) 2>/dev/null | grep -E 'state|percentage|time to' || acpi -b 2>/dev/null || echo 'Kein Akku gefunden.'"
tags = ["lesen"]

[[menu.items]]
key = "g"
icon = "▱"
label = "Grafikkarte"
run = "lspci | grep -iE 'vga|3d|display'"
requires = ["lspci"]
tags = ["lesen"]

[[menu.items]]
key = "n"
icon = "⌖"
label = "Netzwerkkarten"
run = "ip -brief link; echo; lspci | grep -iE 'ethernet|network' 2>/dev/null"
tags = ["lesen"]

[[menu.items]]
key = "s"
icon = "▤"
label = "Gesundheit der Platte"
run = "sudo smartctl -H -i {geraet} 2>/dev/null || echo 'smartctl fehlt oder kein Zugriff.'"
interactive = true
[[menu.items.prompts]]
name = "geraet"
label = "Geraet"
default = "/dev/sda"

# ----------------------------------------------------------- Text und Daten
[[menu]]
id = "text"
title = "Text und Daten"

[[menu.items]]
key = "g"
icon = "◆"
label = "In Dateien suchen"
run = "grep -rnI --color=always --exclude-dir=.git -e {muster} . | head -100"
[[menu.items.prompts]]
name = "muster"
label = "Suchmuster"

[[menu.items]]
key = "e"
icon = "✎"
label = "In einer Datei ersetzen"
desc = "Legt vorher eine Sicherung .bak an."
run = "sed -i.bak 's|'{alt}'|'{neu}'|g' {datei} && echo 'Ersetzt. Sicherung: {datei}.bak' && grep -n --color=always -F {neu} {datei} | head -20"
confirm = "Text in der Datei ersetzen?"
[[menu.items.prompts]]
name = "datei"
label = "Datei"
[[menu.items.prompts]]
name = "alt"
label = "Alter Text"
[[menu.items.prompts]]
name = "neu"
label = "Neuer Text"

[[menu.items]]
key = "z"
icon = "◆"
label = "Zeilen, Woerter, Zeichen zaehlen"
run = "wc -lwc {datei}"
[[menu.items.prompts]]
name = "datei"
label = "Datei"

[[menu.items]]
key = "s"
icon = "≣"
label = "Sortieren, Doppelte entfernen"
run = "sort -u {datei} | head -60"
[[menu.items.prompts]]
name = "datei"
label = "Datei"

[[menu.items]]
key = "D"
icon = "±"
label = "Doppelte Zeilen finden"
run = "sort {datei} | uniq -d | head -40"
[[menu.items.prompts]]
name = "datei"
label = "Datei"

[[menu.items]]
key = "h"
icon = "≣"
label = "Anfang und Ende ansehen"
run = "echo '== erste 20 =='; head -20 {datei}; echo; echo '== letzte 20 =='; tail -20 {datei}"
[[menu.items.prompts]]
name = "datei"
label = "Datei"

[[menu.items]]
key = "j"
icon = "◇"
label = "JSON huebsch anzeigen"
run = "jq -C . {datei} | head -120"
requires = ["jq"]
[[menu.items.prompts]]
name = "datei"
label = "JSON-Datei"

[[menu.items]]
key = "t"
icon = "▤"
label = "CSV als Tabelle"
run = "column -t -s, {datei} | head -40"
requires = ["column"]
[[menu.items.prompts]]
name = "datei"
label = "CSV-Datei"

[[menu.items]]
key = "v"
icon = "±"
label = "Zwei Dateien vergleichen"
run = "diff --color=always -u {a} {b} | head -120 || true"
[[menu.items.prompts]]
name = "a"
label = "Datei A"
[[menu.items.prompts]]
name = "b"
label = "Datei B"

[[menu.items]]
key = "w"
icon = "◆"
label = "Haeufigste Woerter"
run = "tr -cs '[:alnum:]' '\\n' < {datei} | tr '[:upper:]' '[:lower:]' | sort | uniq -c | sort -rn | head -25"
[[menu.items.prompts]]
name = "datei"
label = "Datei"

[[menu.items]]
key = "p"
icon = "◆"
label = "Pruefsumme"
run = "sha256sum {datei}"
[[menu.items.prompts]]
name = "datei"
label = "Datei"

# ---------------------------------------------------------------- Archive
[[menu]]
id = "archive"
title = "Archive"

[[menu.items]]
key = "l"
icon = "≣"
label = "Hineinschauen"
desc = "Zeigt den Inhalt, ohne zu entpacken."
run = """
case {datei} in
  *.tar.gz|*.tgz|*.tar.bz2|*.tar.xz|*.tar) tar tvf {datei} | head -60 ;;
  *.zip) unzip -l {datei} | head -60 ;;
  *.7z)  7z l {datei} | head -60 ;;
  *.rar) unrar l {datei} | head -60 ;;
  *) echo 'Unbekanntes Format.' ;;
esac
"""
[[menu.items.prompts]]
name = "datei"
label = "Archivdatei"

[[menu.items]]
key = "x"
icon = "↓"
label = "Entpacken"
desc = "Erkennt das Format selbst, packt in einen eigenen Ordner."
run = """
ziel="${{1:-}}"
set -- {datei}
name=$(basename "$1"); ziel="${{name%%.*}}"
mkdir -p "$ziel"
case "$1" in
  *.tar.gz|*.tgz)  tar xzf "$1" -C "$ziel" ;;
  *.tar.bz2)       tar xjf "$1" -C "$ziel" ;;
  *.tar.xz)        tar xJf "$1" -C "$ziel" ;;
  *.tar)           tar xf  "$1" -C "$ziel" ;;
  *.zip)           unzip -q "$1" -d "$ziel" ;;
  *.7z)            7z x -o"$ziel" "$1" ;;
  *.rar)           unrar x "$1" "$ziel/" ;;
  *.gz)            gunzip -k "$1" ;;
  *) echo 'Unbekanntes Format.'; exit 1 ;;
esac
echo "Entpackt nach: $ziel"; ls -la "$ziel" | head -20
"""
[[menu.items.prompts]]
name = "datei"
label = "Archivdatei"

[[menu.items]]
key = "c"
icon = "+"
label = "tar.gz aus Ordner"
run = "tar czf {name}.tar.gz {ordner} && ls -lh {name}.tar.gz"
[[menu.items.prompts]]
name = "ordner"
label = "Ordner"
[[menu.items.prompts]]
name = "name"
label = "Name des Archivs (ohne Endung)"

[[menu.items]]
key = "z"
icon = "+"
label = "zip aus Ordner"
run = "zip -r {name}.zip {ordner} >/dev/null && ls -lh {name}.zip"
requires = ["zip"]
[[menu.items.prompts]]
name = "ordner"
label = "Ordner"
[[menu.items.prompts]]
name = "name"
label = "Name des Archivs (ohne Endung)"

[[menu.items]]
key = "t"
icon = "◆"
label = "Archiv auf Fehler pruefen"
run = "gzip -t {datei} 2>&1 && echo 'in Ordnung' || unzip -t {datei} | tail -3"
[[menu.items.prompts]]
name = "datei"
label = "Archivdatei"

# ----------------------------------------------------------------- Medien
[[menu]]
id = "medien"
title = "Medien"
subtitle = "ffmpeg und ImageMagick"

[[menu.items]]
heading = "Ansehen"

[[menu.items]]
key = "i"
icon = "◆"
label = "Infos zu einer Mediendatei"
run = "ffprobe -hide_banner {datei} 2>&1 | head -30"
requires = ["ffprobe"]
[[menu.items.prompts]]
name = "datei"
label = "Datei"

[[menu.items]]
key = "b"
icon = "◆"
label = "Infos zu einem Bild"
run = "identify -verbose {datei} 2>/dev/null | head -25 || file {datei}"
[[menu.items.prompts]]
name = "datei"
label = "Bilddatei"

[[menu.items]]
heading = "Video und Audio"

[[menu.items]]
key = "v"
icon = "▷"
label = "Video nach MP4 wandeln"
run = "ffmpeg -hide_banner -i {datei} -c:v libx264 -crf 23 -preset medium -c:a aac {datei}.mp4 && ls -lh {datei}.mp4"
requires = ["ffmpeg"]
[[menu.items.prompts]]
name = "datei"
label = "Videodatei"

[[menu.items]]
key = "a"
icon = "♪"
label = "Tonspur herausholen"
run = "ffmpeg -hide_banner -i {datei} -vn -c:a libmp3lame -q:a 2 {datei}.mp3 && ls -lh {datei}.mp3"
requires = ["ffmpeg"]
[[menu.items.prompts]]
name = "datei"
label = "Videodatei"

[[menu.items]]
key = "s"
icon = "✂"
label = "Stueck herausschneiden"
run = "ffmpeg -hide_banner -ss {start} -t {dauer} -i {datei} -c copy schnitt_{dauer}s.mp4 && ls -lh schnitt_{dauer}s.mp4"
requires = ["ffmpeg"]
[[menu.items.prompts]]
name = "datei"
label = "Videodatei"
[[menu.items.prompts]]
name = "start"
label = "Startzeit (z. B. 00:01:30)"
quote = false
[[menu.items.prompts]]
name = "dauer"
label = "Dauer in Sekunden"
quote = false

[[menu.items]]
key = "g"
icon = "▷"
label = "GIF aus Video"
run = "ffmpeg -hide_banner -i {datei} -vf 'fps=12,scale=640:-1:flags=lanczos' -loop 0 {datei}.gif && ls -lh {datei}.gif"
requires = ["ffmpeg"]
[[menu.items.prompts]]
name = "datei"
label = "Videodatei"

[[menu.items]]
key = "k"
icon = "◆"
label = "Standbild aus Video"
run = "ffmpeg -hide_banner -ss {zeit} -i {datei} -frames:v 1 standbild.png && ls -lh standbild.png"
requires = ["ffmpeg"]
[[menu.items.prompts]]
name = "datei"
label = "Videodatei"
[[menu.items.prompts]]
name = "zeit"
label = "Zeitpunkt (z. B. 00:00:10)"
quote = false

[[menu.items]]
heading = "Bilder"

[[menu.items]]
key = "r"
icon = "▱"
label = "Bild verkleinern"
run = "convert {datei} -resize {breite} klein_{breite}.png && ls -lh klein_{breite}.png"
requires = ["convert"]
[[menu.items.prompts]]
name = "datei"
label = "Bilddatei"
[[menu.items.prompts]]
name = "breite"
label = "Breite in Pixeln"
default = "1280"
quote = false

[[menu.items]]
key = "j"
icon = "▱"
label = "Nach JPG wandeln"
run = "convert {datei} -quality 88 {datei}.jpg && ls -lh {datei}.jpg"
requires = ["convert"]
[[menu.items.prompts]]
name = "datei"
label = "Bilddatei"

[[menu.items]]
key = "P"
icon = "▤"
label = "Alle Bilder hier in ein PDF"
run = "convert *.jpg *.png bilder.pdf 2>/dev/null && ls -lh bilder.pdf || echo 'Keine Bilder gefunden.'"
requires = ["convert"]

[[menu.items]]
key = "A"
icon = "▱"
label = "Alle Bilder hier verkleinern"
desc = "Kopien in ./klein/, die Originale bleiben unangetastet."
run = """
mkdir -p klein
n=0
for f in *.jpg *.jpeg *.png; do
  [ -e "$f" ] || continue
  convert "$f" -resize '1600x1600>' "klein/$f" && n=$((n+1))
done
echo "$n Bilder nach ./klein/ geschrieben."
"""
requires = ["convert"]

'''


# --------------------------------------------------------------------------- #
#  Konfiguration laden
# --------------------------------------------------------------------------- #

@dataclass
class Config:
    theme: str = "nord"
    opaque: bool = False
    glyphs: str = "auto"
    clock: bool = True
    detail: bool = True
    banner: str = "CI"
    menus: dict[str, Menu] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    path: Path | None = None


def _prompts(raw) -> list[Prompt]:
    out: list[Prompt] = []
    for p in raw or []:
        if isinstance(p, str):
            out.append(Prompt(name=p, label=p))
        elif isinstance(p, dict):
            out.append(Prompt(
                name=str(p.get("name", "wert")),
                label=str(p.get("label") or p.get("name", "Wert")),
                default=str(p.get("default", "")),
                optional=bool(p.get("optional", False)),
                quote=bool(p.get("quote", True)),
            ))
    return out


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def parse_config(text: str, path: Path | None = None) -> Config:
    cfg = Config(path=path)
    try:
        data = tomllib.loads(text)
    except Exception as exc:
        cfg.problems.append("menu.toml ist fehlerhaft: %s" % exc)
        return cfg

    ui = data.get("ui") or {}
    cfg.theme = str(ui.get("theme", "nord"))
    cfg.opaque = bool(ui.get("opaque", False))
    cfg.glyphs = str(ui.get("glyphs", "auto"))
    cfg.clock = bool(ui.get("clock", True))
    cfg.detail = bool(ui.get("detail", True))
    cfg.banner = str(ui.get("banner", "CI"))

    for raw_menu in data.get("menu") or []:
        mid = str(raw_menu.get("id") or "").strip()
        if not mid:
            cfg.problems.append("Ein [[menu]] hat keine id und wurde uebersprungen.")
            continue
        menu = Menu(id=mid,
                    title=str(raw_menu.get("title") or mid.title()),
                    subtitle=str(raw_menu.get("subtitle") or ""))
        for raw in raw_menu.get("items") or []:
            if raw.get("heading"):
                menu.items.append(Item(heading=str(raw["heading"]), menu_id=mid))
                continue
            confirm = raw.get("confirm", "")
            if confirm is True:
                confirm = "Diesen Befehl jetzt ausfuehren?"
            elif confirm is False:
                confirm = ""
            item = Item(
                label=str(raw.get("label") or "(ohne Namen)"),
                key=str(raw.get("key") or "")[:1],
                icon=str(raw.get("icon") or "")[:1],
                desc=str(raw.get("desc") or ""),
                goto=str(raw.get("goto") or ""),
                run=str(raw.get("run") or "").strip(),
                builtin=str(raw.get("builtin") or ""),
                chdir=str(raw.get("chdir") or ""),
                cwd=str(raw.get("cwd") or ""),
                interactive=bool(raw.get("interactive", False)),
                confirm=str(confirm or ""),
                requires=_as_list(raw.get("requires")),
                prompts=_prompts(raw.get("prompts")),
                tags=_as_list(raw.get("tags")),
                menu_id=mid,
            )
            menu.items.append(item)
        cfg.menus[mid] = menu
        cfg.order.append(mid)

    if "root" not in cfg.menus:
        if cfg.order:
            cfg.menus["root"] = cfg.menus[cfg.order[0]]
        else:
            cfg.problems.append("Keine Menues in der Konfiguration gefunden.")
            cfg.menus["root"] = Menu(id="root", title="Leer")
    # Querverweise pruefen
    for menu in cfg.menus.values():
        for it in menu.items:
            if it.goto and it.goto not in cfg.menus:
                cfg.problems.append("%s/%s zeigt auf unbekanntes Menue '%s'."
                                    % (menu.id, it.label, it.goto))
    return cfg


def ensure_config() -> Config:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not MENU_FILE.exists():
        MENU_FILE.write_text(DEFAULT_MENU, encoding="utf-8")
    try:
        return parse_config(MENU_FILE.read_text(encoding="utf-8"), MENU_FILE)
    except Exception as exc:
        cfg = parse_config(DEFAULT_MENU, None)
        cfg.problems.append("menu.toml nicht lesbar (%s) -- Standard wird benutzt." % exc)
        return cfg


# --------------------------------------------------------------------------- #
#  Zustand (Favoriten, Statistik, Theme)
# --------------------------------------------------------------------------- #

class State:
    def __init__(self):
        self.data: dict = {"favorites": [], "stats": {}, "theme": None, "last_dir": None}
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data.update(raw)
        except Exception:
            pass
        self.data.setdefault("favorites", [])
        self.data.setdefault("stats", {})

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(STATE_FILE)
        except Exception:
            pass

    # -- Favoriten ---------------------------------------------------------
    def is_fav(self, uid: str) -> bool:
        return any(f.get("uid") == uid for f in self.data["favorites"])

    def toggle_fav(self, item: Item) -> bool:
        favs = self.data["favorites"]
        for i, f in enumerate(favs):
            if f.get("uid") == item.uid:
                favs.pop(i)
                self.save()
                return False
        favs.append({"uid": item.uid, "menu": item.menu_id, "label": item.label,
                     "icon": item.icon, "key": item.key})
        self.save()
        return True

    # -- Statistik ---------------------------------------------------------
    def stat(self, uid: str) -> dict:
        return self.data["stats"].get(uid, {})

    def record(self, uid: str, rc: int | None, ms: float) -> None:
        st = self.data["stats"].setdefault(uid, {"runs": 0})
        st["runs"] = st.get("runs", 0) + 1
        st["rc"] = rc
        st["ms"] = round(ms)
        st["ts"] = int(time.time())
        self.save()


def log_history(cmd: str, cwd: str, rc: int | None) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        line = "%s\t%s\t%s\t%s\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), rc if rc is not None else "-",
            cwd, cmd.replace("\n", " ¶ "))
        with HISTORY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def read_history(limit: int = 300) -> list[dict]:
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: list[dict] = []
    for line in reversed(lines[-2000:]):
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        out.append({"ts": parts[0], "rc": parts[1], "cwd": parts[2],
                    "cmd": "\t".join(parts[3:])})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- #
#  Kontext: Verzeichnis + Git-Info, im Hintergrund aktualisiert
# --------------------------------------------------------------------------- #

class Context:
    def __init__(self):
        self.lock = threading.Lock()
        self.info: dict = {"branch": "", "dirty": 0, "ahead": 0, "behind": 0,
                           "repo": "", "git": False, "stash": 0}
        self._stop = threading.Event()
        self._tick = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._tick.set()

    def poke(self) -> None:
        self._tick.set()

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.info)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                info = self._collect()
            except Exception:
                info = {"branch": "", "dirty": 0, "ahead": 0, "behind": 0,
                        "repo": "", "git": False, "stash": 0}
            with self.lock:
                self.info = info
            self._tick.wait(2.5)
            self._tick.clear()

    @staticmethod
    def _git(*args: str) -> str:
        try:
            r = subprocess.run(("git",) + args, capture_output=True, text=True,
                               timeout=3)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    def _collect(self) -> dict:
        info = {"branch": "", "dirty": 0, "ahead": 0, "behind": 0, "repo": "",
                "git": False, "stash": 0}
        if not have("git"):
            return info
        top = self._git("rev-parse", "--show-toplevel")
        if not top:
            return info
        info["git"] = True
        info["repo"] = os.path.basename(top)
        info["branch"] = self._git("rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
        porcelain = self._git("status", "--porcelain")
        info["dirty"] = len([l for l in porcelain.splitlines() if l.strip()])
        counts = self._git("rev-list", "--left-right", "--count", "@{u}...HEAD")
        if counts:
            parts = counts.split()
            if len(parts) == 2:
                info["behind"], info["ahead"] = int(parts[0]), int(parts[1])
        stash = self._git("stash", "list")
        info["stash"] = len(stash.splitlines()) if stash else 0
        return info


# --------------------------------------------------------------------------- #
#  Platzhalter einsetzen
# --------------------------------------------------------------------------- #

_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")


def substitute(template: str, values: dict[str, str]) -> str:
    def rep(m: re.Match) -> str:
        whole = m.group(0)
        if whole == "{{":
            return "{"
        if whole == "}}":
            return "}"
        name = m.group(1) or ""
        return values[name] if name in values else whole
    return _PLACEHOLDER.sub(rep, template)


def placeholders(template: str) -> list[str]:
    return [m.group(1) for m in _PLACEHOLDER.finditer(template) if m.group(1)]


# --------------------------------------------------------------------------- #
#  ANSI-Farben in Attribut-Laeufe uebersetzen
# --------------------------------------------------------------------------- #

@dataclass
class Style:
    fg: int = -1
    bold: bool = False
    dim: bool = False
    under: bool = False
    rev: bool = False

    def copy(self) -> "Style":
        return Style(self.fg, self.bold, self.dim, self.under, self.rev)


_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_runs(line: str, carry: Style) -> tuple[list[tuple[str, Style]], Style]:
    """Zeile in (Text, Style)-Laeufe zerlegen; Style wird mitgenommen."""
    line = _OSC.sub("", line)
    runs: list[tuple[str, Style]] = []
    style = carry.copy()
    pos = 0
    for m in _SGR.finditer(line):
        if m.start() > pos:
            runs.append((line[pos:m.start()], style.copy()))
        pos = m.end()
        codes = [c for c in m.group(1).split(";") if c != ""] or ["0"]
        i = 0
        while i < len(codes):
            try:
                c = int(codes[i])
            except ValueError:
                i += 1
                continue
            if c == 0:
                style = Style()
            elif c == 1:
                style.bold = True
            elif c == 2:
                style.dim = True
            elif c == 4:
                style.under = True
            elif c == 7:
                style.rev = True
            elif c in (21, 22):
                style.bold = style.dim = False
            elif c == 24:
                style.under = False
            elif c == 27:
                style.rev = False
            elif 30 <= c <= 37:
                style.fg = c - 30
            elif c == 39:
                style.fg = -1
            elif 90 <= c <= 97:
                style.fg = c - 90 + 8
            elif c == 38 and i + 1 < len(codes):
                if codes[i + 1] == "5" and i + 2 < len(codes):
                    style.fg = int(codes[i + 2]) % 256
                    i += 2
                elif codes[i + 1] == "2" and i + 4 < len(codes):
                    r, g, b = (int(codes[i + 2]), int(codes[i + 3]), int(codes[i + 4]))
                    style.fg = 16 + 36 * (r * 5 // 255) + 6 * (g * 5 // 255) + (b * 5 // 255)
                    i += 4
            i += 1
    if pos < len(line):
        runs.append((line[pos:], style.copy()))
    cleaned: list[tuple[str, Style]] = []
    for text, st in runs:
        text = sanitize(strip_ansi(text))
        if text:
            cleaned.append((text, st))
    return cleaned, style



def wrap_runs(runs: list[tuple[str, Style]], width: int
              ) -> list[list[tuple[str, Style]]]:
    """Farbige Laeufe auf Breite umbrechen -- wie ein echtes Terminal."""
    if width < 2:
        return [runs]
    out: list[list[tuple[str, Style]]] = []
    cur: list[tuple[str, Style]] = []
    used = 0
    for text, st in runs:
        while text:
            space = width - used
            if space <= 0:
                out.append(cur)
                cur, used, space = [], 0, width
            piece, text = text[:space], text[space:]
            cur.append((piece, st))
            used += len(piece)
    out.append(cur)
    return out or [[]]

# --------------------------------------------------------------------------- #
#  Job: ein laufender Shell-Befehl
# --------------------------------------------------------------------------- #

MAX_LINES = 20000


def pick_shell() -> str:
    sh = os.environ.get("SHELL") or ""
    base = os.path.basename(sh)
    if base in ("bash", "zsh", "sh", "dash", "ksh", "mksh", "ash"):
        return sh
    for cand in ("/bin/bash", "/usr/bin/bash", "/bin/sh"):
        if os.path.exists(cand):
            return cand
    return "/bin/sh"


class Job:
    def __init__(self, cmd: str, cwd: str, title: str = ""):
        self.cmd = cmd
        self.cwd = cwd
        self.title = title or cmd
        self.lines: list[list[tuple[str, Style]]] = []
        self.plain: list[str] = []
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.rc: int | None = None
        self.running = False
        self.started = 0.0
        self.ms = 0.0
        self.truncated = False
        self._carry = Style()
        self._reader: threading.Thread | None = None

    # -- Steuerung ---------------------------------------------------------
    def start(self) -> None:
        env = dict(os.environ)
        env.update({
            "CI_SHELL": "1",
            "CLICOLOR_FORCE": "1",
            "FORCE_COLOR": "1",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
            "SYSTEMD_COLORS": "1",
            "COLUMNS": "200",
        })
        self.started = time.time()
        self.running = True
        try:
            self.proc = subprocess.Popen(
                [pick_shell(), "-c", self.cmd],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, cwd=self.cwd, env=env,
                text=True, errors="replace", bufsize=1,
                start_new_session=True,
            )
        except Exception as exc:
            self._append("Start fehlgeschlagen: %s" % exc)
            self.running = False
            self.rc = 127
            self.ms = 0.0
            return
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _append(self, raw: str) -> None:
        runs, self._carry = ansi_runs(raw.rstrip("\n"), self._carry)
        with self.lock:
            if len(self.lines) >= MAX_LINES:
                self.truncated = True
                self.lines.pop(0)
                self.plain.pop(0)
            self.lines.append(runs)
            self.plain.append("".join(t for t, _ in runs))

    def _pump(self) -> None:
        assert self.proc is not None
        try:
            if self.proc.stdout:
                for raw in self.proc.stdout:
                    self._append(raw)
        except Exception:
            pass
        try:
            self.rc = self.proc.wait()
        except Exception:
            self.rc = -1
        self.ms = (time.time() - self.started) * 1000.0
        self.running = False

    def signal(self, sig: int = signal.SIGTERM) -> None:
        if self.proc and self.running:
            try:
                os.killpg(os.getpgid(self.proc.pid), sig)
            except Exception:
                try:
                    self.proc.send_signal(sig)
                except Exception:
                    pass

    def count(self) -> int:
        with self.lock:
            return len(self.lines)

    def view(self, start: int, n: int) -> list[list[tuple[str, Style]]]:
        with self.lock:
            return self.lines[start:start + n]

    def save(self) -> Path | None:
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            name = time.strftime("%Y%m%d-%H%M%S") + ".txt"
            path = OUTPUT_DIR / name
            with self.lock:
                body = "\n".join(self.plain)
            path.write_text("$ %s\n(%s)\n\n%s\n" % (self.cmd, self.cwd, body),
                            encoding="utf-8")
            return path
        except Exception:
            return None


# --------------------------------------------------------------------------- #
#  Einzeiliger Editor fuer Filter- und Eingabefelder
# --------------------------------------------------------------------------- #

class LineEdit:
    def __init__(self, text: str = ""):
        self.text = text
        self.pos = len(text)

    def set(self, text: str) -> None:
        self.text = text
        self.pos = len(text)

    def handle(self, ch) -> bool:
        if isinstance(ch, int):
            if ch in (curses.KEY_LEFT,):
                self.pos = max(0, self.pos - 1)
            elif ch in (curses.KEY_RIGHT,):
                self.pos = min(len(self.text), self.pos + 1)
            elif ch in (curses.KEY_HOME,):
                self.pos = 0
            elif ch in (curses.KEY_END,):
                self.pos = len(self.text)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.pos > 0:
                    self.text = self.text[:self.pos - 1] + self.text[self.pos:]
                    self.pos -= 1
            elif ch in (curses.KEY_DC,):
                self.text = self.text[:self.pos] + self.text[self.pos + 1:]
            else:
                return False
            return True
        if ch in ("\x7f", "\b"):
            if self.pos > 0:
                self.text = self.text[:self.pos - 1] + self.text[self.pos:]
                self.pos -= 1
            return True
        if ch == "\x15":                      # Ctrl-U  Zeile loeschen
            self.text = self.text[self.pos:]
            self.pos = 0
            return True
        if ch == "\x0b":                      # Ctrl-K  bis Ende loeschen
            self.text = self.text[:self.pos]
            return True
        if ch == "\x17":                      # Ctrl-W  Wort loeschen
            i = self.pos
            while i > 0 and self.text[i - 1] == " ":
                i -= 1
            while i > 0 and self.text[i - 1] != " ":
                i -= 1
            self.text = self.text[:i] + self.text[self.pos:]
            self.pos = i
            return True
        if ch == "\x01":                      # Ctrl-A
            self.pos = 0
            return True
        if ch == "\x05":                      # Ctrl-E
            self.pos = len(self.text)
            return True
        if isinstance(ch, str) and len(ch) == 1 and (ch >= " " and ch != "\x7f"):
            self.text = self.text[:self.pos] + ch + self.text[self.pos:]
            self.pos += 1
            return True
        return False


# --------------------------------------------------------------------------- #
#  Die Anwendung
# --------------------------------------------------------------------------- #

# get_wch() liefert normale Tasten als String, Sondertasten als Zahl --
# darum muss beides in diesen Listen stehen.
BACKSPACES = (curses.KEY_BACKSPACE, 127, 8, "\x7f", "\b")
ENTERS = (curses.KEY_ENTER, 10, 13, "\n", "\r")
RESERVED = set("q/?!*")

# Rohe Escape-Folgen auf curses-Tastencodes abbilden -- fuer Terminals, die
# Sondertasten nicht selbst uebersetzen.
ESC_SEQUENCES: dict[str, int] = {
    "[A": curses.KEY_UP,    "OA": curses.KEY_UP,
    "[B": curses.KEY_DOWN,  "OB": curses.KEY_DOWN,
    "[C": curses.KEY_RIGHT, "OC": curses.KEY_RIGHT,
    "[D": curses.KEY_LEFT,  "OD": curses.KEY_LEFT,
    "[H": curses.KEY_HOME,  "OH": curses.KEY_HOME, "[1~": curses.KEY_HOME,
    "[F": curses.KEY_END,   "OF": curses.KEY_END,  "[4~": curses.KEY_END,
    "[5~": curses.KEY_PPAGE, "[6~": curses.KEY_NPAGE,
    "[3~": curses.KEY_DC,    "[Z": curses.KEY_BTAB,
}


class App:
    def __init__(self, scr, cfg: Config, state: State):
        self.scr = scr
        self.cfg = cfg
        self.state = state
        self.g = pick_glyphs(cfg.glyphs)
        opaque = state.data.get("opaque")
        self.pal = Palette(state.data.get("theme") or cfg.theme,
                           cfg.opaque if opaque is None else bool(opaque))
        self.pal.start()
        self.apply_background()
        self.ctx = Context()
        self.stack: list[str] = ["root"]
        self.sel: dict[str, int] = {}
        self.scroll: dict[str, int] = {}
        self.edit = LineEdit()
        self.filtering = False
        self.msg = ""
        self.msg_kind = "info"
        self.msg_until = 0.0
        self.quit = False
        self.ascii = (self.g["v"] == "|")
        self.last_job: Job | None = None
        if cfg.problems:
            self.notify(cfg.problems[0], "warn", 8)

    # ------------------------------------------------------------------ Hilfen
    def apply_background(self) -> None:
        """Leere Flaechen einfaerben -- oder das Terminal durchscheinen lassen."""
        try:
            self.scr.bkgd(" ", self.pal("text"))
        except curses.error:
            pass

    def toggle_opaque(self) -> None:
        self.pal.opaque = not self.pal.opaque
        self.pal.load(self.pal.theme)
        self.apply_background()
        self.state.data["opaque"] = self.pal.opaque
        self.state.save()
        self.notify("Hintergrund: %s" % ("deckend" if self.pal.opaque
                                         else "Terminal durchscheinend"),
                    "ok", 3)

    def notify(self, text: str, kind: str = "info", secs: float = 4.0) -> None:
        self.msg = text
        self.msg_kind = kind
        self.msg_until = time.time() + secs

    @property
    def filter(self) -> str:
        return self.edit.text

    # ----------------------------------------------------------- Zeichnen (low)
    def put(self, y: int, x: int, text: str, attr: int = 0,
            maxw: int | None = None) -> int:
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w or not text:
            return 0
        if x < 0:
            text = text[-x:]
            x = 0
        avail = w - x
        if maxw is not None:
            avail = min(avail, maxw)
        if avail <= 0:
            return 0
        s = text[:avail]
        last = (y == h - 1 and x + len(s) >= w)
        if last:
            head, tail = s[:-1], s[-1]
            if head:
                try:
                    self.scr.addstr(y, x, head, attr)
                except curses.error:
                    pass
            try:
                self.scr.insstr(y, x + len(head), tail, attr)
            except curses.error:
                pass
        else:
            try:
                self.scr.addstr(y, x, s, attr)
            except curses.error:
                pass
        return len(s)

    def frame(self, y: int, x: int, h: int, w: int, attr: int) -> None:
        g = self.g
        if h < 2 or w < 2:
            return
        self.put(y, x, g["tl"] + g["h"] * (w - 2) + g["tr"], attr)
        for i in range(1, h - 1):
            self.put(y + i, x, g["v"], attr)
            self.put(y + i, x + w - 1, g["v"], attr)
        self.put(y + h - 1, x, g["bl"] + g["h"] * (w - 2) + g["br"], attr)

    def clear_box(self, y: int, x: int, h: int, w: int, attr: int = 0) -> None:
        for i in range(h):
            self.put(y + i, x, " " * w, attr)

    def panel(self, y: int, x: int, h: int, w: int, title: str = "",
              hint: str = "") -> None:
        """Rahmen mit Titel links oben und Hinweis unten rechts."""
        g, p = self.g, self.pal
        # etwas Luft rundherum, damit sich das Fenster klar abhebt
        self.clear_box(max(0, y - 1), max(0, x - 2), h + 2, w + 4, p("text"))
        self.frame(y, x, h, w, p("border_hi"))
        if title:
            t = ell(" " + title + " ", max(0, w - 4), g)
            self.put(y, x + 2, t, p("title", curses.A_BOLD))
        if hint:
            t = ell(" " + hint + " ", max(0, w - 4), g)
            self.put(y + h - 1, x + max(2, w - 2 - len(t)), t, p("dim"))


    def icon_for(self, it: Item) -> str:
        """Symbol des Eintrags -- mit Rueckfall, wenn nur ASCII geht."""
        default = {"menu": self.g["folder"], "cmd": self.g["cmd"],
                   "builtin": self.g["lock"], "chdir": self.g["home"]}.get(
                       it.kind, " ")
        icon = it.icon
        if not icon:
            return default
        if self.ascii and not icon.isascii():
            return default
        return icon

    # --------------------------------------------------------------- Menuedaten
    @property
    def current_id(self) -> str:
        return self.stack[-1]

    def menu_for(self, mid: str) -> Menu:
        if mid == "@fav":
            return self._fav_menu()
        if mid == "@hist":
            return self._hist_menu()
        m = self.cfg.menus.get(mid)
        if m is None:
            return Menu(id=mid, title="Unbekannt",
                        subtitle="Menue '%s' existiert nicht" % mid)
        return m

    def _fav_menu(self) -> Menu:
        menu = Menu(id="@fav", title="Favoriten",
                    subtitle="mit * markiert · * entfernt wieder")
        for f in self.state.data["favorites"]:
            src = self.cfg.menus.get(f.get("menu", ""))
            found = None
            if src:
                for it in src.items:
                    if it.uid == f.get("uid"):
                        found = it
                        break
            if found:
                menu.items.append(found)
            else:
                menu.items.append(Item(
                    label=f.get("label", "?"), icon=self.g["err"],
                    desc="Dieser Eintrag existiert in menu.toml nicht mehr.",
                    menu_id="@fav"))
        if not menu.items:
            menu.items.append(Item(
                label="Noch keine Favoriten",
                desc="Irgendwo im Menue mit  *  einen Eintrag markieren.",
                icon=self.g["nostar"], menu_id="@fav"))
        return menu

    def _hist_menu(self) -> Menu:
        menu = Menu(id="@hist", title="Historie",
                    subtitle="Enter startet den Befehl erneut")
        seen: set[str] = set()
        for h in read_history(200):
            cmd = h["cmd"].replace("¶", ";")
            if cmd in seen:
                continue
            seen.add(cmd)
            rc = h["rc"]
            icon = self.g["ok"] if rc == "0" else (self.g["err"] if rc not in ("-", "") else self.g["bullet"])
            menu.items.append(Item(
                label=cmd, icon=icon, run=cmd, menu_id="@hist",
                desc="%s  ·  %s" % (h["ts"], short_path(h["cwd"]))))
            if len(menu.items) >= 120:
                break
        if not menu.items:
            menu.items.append(Item(label="Noch keine Historie",
                                   desc="Hier landet alles, was du ausfuehrst.",
                                   menu_id="@hist"))
        return menu

    def visible(self) -> list[Item]:
        """Eintraege des aktuellen Menues, gefiltert."""
        items = self.menu_for(self.current_id).items
        f = self.filter.strip()
        if not f:
            return items
        scored: list[tuple[int, int, Item]] = []
        for i, it in enumerate(items):
            if it.is_heading:
                continue
            hay = "%s %s %s" % (it.label, it.desc, " ".join(it.tags))
            sc = fuzzy(f, hay)
            if sc is not None:
                scored.append((-sc, i, it))
        scored.sort()
        return [it for _, _, it in scored]

    def sel_index(self) -> int:
        return self.sel.get(self.current_id, 0)

    def set_sel(self, idx: int) -> None:
        self.sel[self.current_id] = idx

    def selected(self) -> Item | None:
        items = self.visible()
        real = [i for i, it in enumerate(items) if not it.is_heading]
        if not real:
            return None
        idx = self.sel_index()
        if idx < 0 or idx >= len(items) or items[idx].is_heading:
            idx = real[0]
            self.set_sel(idx)
        return items[idx]

    def move(self, delta: int, absolute: int | None = None) -> None:
        items = self.visible()
        real = [i for i, it in enumerate(items) if not it.is_heading]
        if not real:
            return
        cur = self.sel_index()
        if cur in real:
            pos = real.index(cur)
        else:
            pos = 0
        if absolute is not None:
            pos = absolute if absolute >= 0 else len(real) + absolute
        else:
            pos += delta
        pos = max(0, min(len(real) - 1, pos))
        self.set_sel(real[pos])

    # ------------------------------------------------------------- Kopfzeilen
    def breadcrumb(self) -> list[tuple[str, int]]:
        g, p = self.g, self.pal
        out: list[tuple[str, int]] = [(g["home"] + " ", p("accent"))]
        for n, mid in enumerate(self.stack):
            title = self.menu_for(mid).title
            last = (n == len(self.stack) - 1)
            out.append((title, p("title", curses.A_BOLD) if last else p("dim")))
            if not last:
                out.append((" %s " % g["sep"], p("faint")))
        return out

    def context_cells(self) -> list[tuple[str, int]]:
        g, p = self.g, self.pal
        info = self.ctx.snapshot()
        cells: list[tuple[str, int]] = []
        cells.append((short_path(os.getcwd()), p("path")))
        if info["git"]:
            cells.append(("%s %s" % (g["branch"], info["branch"]), p("accent2", curses.A_BOLD)))
            if info["dirty"]:
                cells.append(("%s%d" % (g["dot"], info["dirty"]), p("warn")))
            else:
                cells.append(("%s clean" % g["ok"], p("ok")))
            if info["ahead"]:
                cells.append(("%s%d" % (g["up"], info["ahead"]), p("accent")))
            if info["behind"]:
                cells.append(("%s%d" % (g["down"], info["behind"]), p("accent")))
            if info["stash"]:
                cells.append(("stash %d" % info["stash"], p("dim")))
        return cells

    # --------------------------------------------------------------- Zeichnen
    def layout(self) -> tuple[int, int, int, int, int]:
        """(h, w, listw, detailw, rows) -- rows = Zeilen im Inhaltsbereich."""
        h, w = self.scr.getmaxyx()
        detail = 0
        if self.cfg.detail and w >= 84:
            detail = max(32, min(54, w // 3))
        listw = w - 2 - detail - (1 if detail else 0)
        rows = h - 6
        return h, w, listw, detail, rows

    def draw(self) -> None:
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        if h < 14 or w < 46:
            self.put(0, 0, "Terminal zu klein", self.pal("err", curses.A_BOLD))
            self.put(1, 0, "mindestens 46x14, aktuell %dx%d" % (w, h), self.pal("dim"))
            self.scr.noutrefresh()
            curses.doupdate()
            return
        h, w, listw, detailw, rows = self.layout()
        p, g = self.pal, self.g

        # Aussenrahmen
        self.frame(0, 0, h, w, p("border"))

        # --- Titelzeile mit Banner und Breadcrumb
        banner = " %s " % self.cfg.banner.strip()
        self.put(0, 2, banner, p("badge", curses.A_BOLD))
        x = 2 + len(banner) + 1
        x += self.put(0, x, g["h"] + " ", p("border"))
        for text, attr in self.breadcrumb():
            if x >= w - 14:
                break
            x += self.put(0, x, text, attr, maxw=w - 14 - x)
        x += self.put(0, x, " ", p("border"))
        sub = self.menu_for(self.current_id).subtitle
        if sub and (w - 16 - x) >= len(sub) + 4:
            x += self.put(0, x, "%s %s " % (g["h"], sub), p("faint"),
                          maxw=w - 16 - x)
        if self.cfg.clock:
            stamp = time.strftime(" %H:%M:%S ")
            self.put(0, w - 2 - len(stamp), stamp, p("dim"))

        # --- Kontextzeile
        self.put(1, 1, " " * (w - 2), p("text"))
        total = len([i for i in self.menu_for(self.current_id).items
                     if not i.is_heading])
        shown = len([i for i in self.visible() if not i.is_heading])
        if self.filter.strip():
            right = "%d/%d Treffer" % (shown, total)
        else:
            right = "%d Befehl" % total if total == 1 else "%d Befehle" % total
        limit = w - 4 - len(right)          # bis hierher darf die linke Seite

        x = 2
        for n, (text, attr) in enumerate(self.context_cells()):
            avail = limit - x - (6 if n else 0)
            if avail < 6:
                break
            if n == 0:
                # Pfad darf schrumpfen, damit der Branch sicher Platz hat
                text = ell_left(text, min(avail, max(14, int((w - 26) * 0.55))), g)
            if n:
                x += self.put(1, x, "  %s  " % g["bullet"], p("faint"))
            x += self.put(1, x, ell(text, avail, g), attr)
        self.put(1, max(x + 2, w - 2 - len(right)), right, p("faint"))

        # --- Trennlinie oben
        self.put(2, 1, g["h"] * (w - 2), p("border"))
        self.put(2, 0, g["ltee"], p("border"))
        self.put(2, w - 1, g["rtee"], p("border"))
        if detailw:
            self.put(2, 1 + listw, g["ttee"], p("border"))
            for i in range(rows):
                self.put(3 + i, 1 + listw, g["v"], p("border"))

        # --- Inhalt
        self.draw_list(3, 1, rows, listw)
        if detailw:
            self.draw_detail(3, 2 + listw, rows, detailw)

        # --- Trennlinie unten
        yb = 3 + rows
        self.put(yb, 1, g["h"] * (w - 2), p("border"))
        self.put(yb, 0, g["ltee"], p("border"))
        self.put(yb, w - 1, g["rtee"], p("border"))
        if detailw:
            self.put(yb, 1 + listw, g["btee"], p("border"))

        # --- Fusszeile
        self.draw_footer(yb + 1, w)

        if self.filtering:
            cx = 4 + len(self.filter[:self.edit.pos])
            try:
                curses.curs_set(1)
                self.scr.move(yb + 1, min(cx, w - 2))
            except curses.error:
                pass
        else:
            try:
                curses.curs_set(0)
            except curses.error:
                pass

        self.scr.noutrefresh()
        curses.doupdate()

    def draw_list(self, y0: int, x0: int, rows: int, width: int) -> None:
        p, g = self.pal, self.g
        items = self.visible()
        sel = self.sel_index()
        if not items:
            self.put(y0 + 1, x0 + 3, "nichts gefunden", p("dim"))
            return

        # Scrollfenster
        key = self.current_id + "|" + self.filter
        top = self.scroll.get(key, 0)
        if sel < top:
            top = sel
        if sel >= top + rows:
            top = sel - rows + 1
        top = max(0, min(top, max(0, len(items) - rows)))
        self.scroll[key] = top

        for row in range(rows):
            idx = top + row
            if idx >= len(items):
                break
            it = items[idx]
            y = y0 + row
            if it.is_heading:
                label = " %s " % it.heading.upper()
                self.put(y, x0 + 2, label, p("head", curses.A_BOLD))
                rest = width - 3 - len(label)
                if rest > 1:
                    self.put(y, x0 + 2 + len(label), g["h"] * rest, p("faint"))
                continue

            active = (idx == sel)
            missing = it.missing
            if active:
                base = p("sel")
                self.put(y, x0, " " * width, base)
            else:
                base = p("text")
            dim = curses.A_DIM if missing else 0

            x = x0 + 1
            # Auswahlmarke
            self.put(y, x, g["sel"] if active else " ",
                     (base | curses.A_BOLD) if active else p("faint"))
            x += 2
            # Hotkey
            if it.key:
                self.put(y, x, "[", base if active else p("faint"))
                self.put(y, x + 1, it.key,
                         (base | curses.A_BOLD) if active else p("key", curses.A_BOLD))
                self.put(y, x + 2, "]", base if active else p("faint"))
            x += 4
            # Favoritenstern
            star = g["star"] if self.state.is_fav(it.uid) else " "
            self.put(y, x, star, base if active else p("accent2"))
            x += 2
            # Symbol
            self.put(y, x, self.icon_for(it), base if active else p("accent"))
            x += 2

            # Rechter Teil: Tags / Pfeil / Hinweis
            right = ""
            right_attr = p("faint")
            if missing:
                right = "%s fehlt" % missing[0]
                right_attr = p("err") if not active else base
            elif it.kind == "menu":
                right = g["arrow"]
                right_attr = base if active else p("accent")
            elif it.tags:
                right = " ".join(it.tags[:2])
                right_attr = base if active else p("faint")
            rspace = len(right) + 2 if right else 0

            labelw = max(4, x0 + width - x - rspace - 1)
            self.put(y, x, ell(it.label, labelw, g),
                     (base | curses.A_BOLD) if active else (p("text") | dim))
            if right:
                self.put(y, x0 + width - len(right) - 1, right, right_attr)

        # Scroll-Indikatoren
        if top > 0:
            self.put(y0, x0 + width - 1, g["up"], p("accent"))
        if top + rows < len(items):
            self.put(y0 + rows - 1, x0 + width - 1, g["down"], p("accent"))

    def draw_detail(self, y0: int, x0: int, rows: int, width: int) -> None:
        p, g = self.pal, self.g
        it = self.selected()
        inner = width - 3
        y = y0

        def line(text: str = "", attr: int = 0, indent: int = 0) -> None:
            nonlocal y
            if y < y0 + rows:
                self.put(y, x0 + 1 + indent, ell(text, inner - indent, g), attr)
                y += 1

        if it is None:
            line("Kein Eintrag", p("dim"))
            return

        # Kopf
        head = "%s  %s" % (self.icon_for(it), it.label)
        for n, chunk in enumerate(wrap(head, inner)):
            line(chunk, p("title", curses.A_BOLD))
        kind_label = {"menu": "Untermenue", "cmd": "Befehl",
                      "builtin": "Funktion", "chdir": "Verzeichnis",
                      "noop": "Hinweis"}.get(it.kind, "")
        meta = kind_label
        if it.key:
            meta += "   ·   Taste [%s]" % it.key
        if self.state.is_fav(it.uid):
            meta += "   ·   %s Favorit" % g["star"]
        line(meta, p("faint"))
        line()

        # Beschreibung
        if it.desc:
            for chunk in wrap(it.desc, inner):
                line(chunk, p("dim"))
            line()

        # Fehlende Programme
        if it.missing:
            line("%s nicht installiert: %s" % (g["err"], ", ".join(it.missing)),
                 p("err", curses.A_BOLD))
            line()

        # Eingabefelder
        if it.prompts:
            line("Fragt vorher", p("head", curses.A_BOLD))
            for pr in it.prompts:
                suffix = "  (optional)" if pr.optional else ""
                line("%s %s%s" % (g["bullet"], pr.label or pr.name, suffix),
                     p("text"), indent=1)
                if pr.default:
                    line("vorbelegt: %s" % pr.default, p("faint"), indent=3)
            line()

        # Flags
        flags: list[tuple[str, int]] = []
        if it.interactive:
            flags.append(("%s nimmt das ganze Terminal" % g["tri"], p("accent2")))
        if it.confirm:
            flags.append(("%s fragt vor dem Start nach" % g["lock"], p("warn")))
        if "gefaehrlich" in it.tags:
            flags.append(("%s nicht umkehrbar" % g["err"], p("err", curses.A_BOLD)))
        if it.cwd:
            flags.append(("%s laeuft in %s" % (g["home"], it.cwd), p("dim")))
        for text, attr in flags:
            line(text, attr)
        if flags:
            line()

        # Befehl
        if it.run:
            line("Befehl", p("head", curses.A_BOLD))
            cmd_lines = [l for l in it.run.strip().splitlines()]
            budget = max(3, (y0 + rows) - y - 4)
            shown = 0
            for raw in cmd_lines:
                if shown >= budget:
                    line("%s  (%d weitere Zeilen)" % (g["ell"], len(cmd_lines) - shown),
                         p("faint"), indent=1)
                    break
                for n, chunk in enumerate(wrap(raw.strip(), inner - 2)):
                    if shown >= budget:
                        break
                    line(("%s " % g["cmd"] if (shown == 0) else "  ") + chunk,
                         p("cmd"))
                    shown += 1
            line()
        elif it.goto:
            sub = self.menu_for(it.goto)
            n = len([i for i in sub.items if not i.is_heading])
            line("1 Eintrag darin" if n == 1 else "%d Eintraege darin" % n,
                 p("dim"))
            for s in sub.items[:min(6, rows - (y - y0) - 3)]:
                if s.is_heading:
                    continue
                line("%s %s" % (g["bullet"], s.label), p("faint"), indent=1)
            line()

        # Statistik -- immer ganz unten
        st = self.state.stat(it.uid)
        if st.get("runs"):
            ybase = y0 + rows - 2
            if ybase > y:
                y = ybase
            rc = st.get("rc")
            ok = (rc == 0)
            sym = g["ok"] if ok else g["err"]
            attr = p("ok") if ok else p("err")
            when = st.get("ts")
            ago = ""
            if when:
                d = max(0, int(time.time()) - int(when))
                ago = ("vor %ds" % d) if d < 60 else (
                    "vor %dmin" % (d // 60) if d < 3600 else (
                        "vor %dh" % (d // 3600) if d < 86400 else
                        "vor %dT" % (d // 86400)))
            line("%s zuletzt rc=%s  %s  %s" % (
                sym, rc, human_ms(st.get("ms", 0)), ago), attr)
            line("%dx benutzt" % st["runs"], p("faint"))

    # ----------------------------------------------------------- Fusszeile
    def hints(self) -> list[tuple[str, str]]:
        g = self.g
        it = self.selected()
        out: list[tuple[str, str]] = [("%s%s" % (g["up"], g["down"]), "Bewegen")]
        if it is not None:
            if it.kind == "menu":
                out.append((g["enter"], "Oeffnen"))
            elif it.kind in ("cmd", "builtin", "chdir"):
                out.append((g["enter"], "Ausfuehren"))
        if len(self.stack) > 1:
            out.append((g["bs"], "Zurueck"))
        out.append(("/", "Filter"))
        out.append(("*", "Favorit"))
        out.append(("^P", "Alle Befehle"))
        out.append(("!", "Shell"))
        out.append(("?", "Hilfe"))
        out.append(("q", "Ende"))
        return out

    def draw_footer(self, y: int, w: int) -> None:
        p, g = self.pal, self.g
        self.put(y, 1, " " * (w - 2), p("text"))

        if self.msg and time.time() < self.msg_until:
            attr = {"info": p("accent"), "ok": p("ok"), "warn": p("warn"),
                    "err": p("err", curses.A_BOLD)}.get(self.msg_kind, p("accent"))
            sym = {"ok": g["ok"], "warn": g["lock"], "err": g["err"]}.get(
                self.msg_kind, g["dot"])
            self.put(y, 2, "%s %s" % (sym, ell(self.msg, w - 6, g)), attr)
            return

        if self.filtering or self.filter:
            self.put(y, 2, "/ ", p("accent", curses.A_BOLD))
            self.put(y, 4, ell(self.filter, w - 24, g), p("title"))
            tail = "%s uebernehmen · Esc leeren" % g["enter"]
            self.put(y, max(6, w - 2 - len(tail)), tail, p("faint"))
            return

        x = 2
        for keyname, label in self.hints():
            need = len(keyname) + len(label) + 4
            if x + need > w - 2:
                break
            x += self.put(y, x, keyname, p("key", curses.A_BOLD))
            x += self.put(y, x, " " + label, p("dim"))
            x += self.put(y, x, "   ", 0)

    # ------------------------------------------------------- Overlay: Hilfe
    def view_help(self) -> None:
        g, p = self.g, self.pal
        sections: list[tuple[str, list[tuple[str, str]]]] = [
            ("Bewegen", [
                ("%s / %s  oder  j / k" % (g["up"], g["down"]), "Eintrag wechseln"),
                ("Bild auf / ab", "seitenweise"),
                ("Pos1 / Ende", "erster / letzter Eintrag"),
                ("1 ... 9", "direkt zum n-ten Eintrag"),
                ("Buchstabe", "Eintrag mit diesem Hotkey sofort starten"),
            ]),
            ("Benutzen", [
                ("%s  oder  %s" % (g["enter"], g["arrow"]), "oeffnen / ausfuehren"),
                ("%s  oder  %s / Esc" % (g["bs"], "←"), "eine Ebene zurueck"),
                ("/", "Filter tippen (fuzzy), Esc leert ihn"),
                ("*", "Eintrag als Favorit an- oder abwaehlen"),
                ("Strg-P", "Suche ueber alle Befehle aller Menues"),
                ("!", "freien Shell-Einzeiler eingeben"),
            ]),
            ("Ausgabe-Fenster", [
                ("j / k, Bild auf/ab", "scrollen"),
                ("g / G", "Anfang / Ende"),
                ("h / l", "waagerecht scrollen (ohne Umbruch)"),
                ("u", "Zeilenumbruch an / aus"),
                ("f", "Ausgabe mitlaufen lassen (tail)"),
                ("n / N", "naechster / vorheriger Suchtreffer"),
                ("s", "Ausgabe in Datei speichern"),
                ("r", "Befehl erneut starten"),
                ("Strg-C / K", "laufenden Befehl abbrechen"),
                ("q / Esc / %s" % g["enter"], "Fenster schliessen"),
            ]),
            ("Allgemein", [
                ("Strg-B", "Hintergrund deckend / durchscheinend"),
                ("Strg-O", "letzte Ausgabe nochmal ansehen"),
                ("Strg-T", "Farbschema durchschalten"),
                ("Strg-R", "menu.toml neu laden"),
                ("Strg-L", "Bildschirm neu zeichnen"),
                ("?", "diese Hilfe"),
                ("q", "CI beenden"),
            ]),
        ]
        info = [
            "Konfiguration   %s" % (self.cfg.path or "(eingebaut)"),
            "Zustand         %s" % STATE_FILE,
            "Historie        %s" % HISTORY_FILE,
            "Ausgaben        %s" % OUTPUT_DIR,
            "Farbschema      %s   (%d Farben)" % (self.pal.theme, self.pal.colors),
            "Version         CI %s" % VERSION,
        ]

        lines: list[tuple[str, int]] = []
        for title, rowset in sections:
            lines.append((title.upper(), p("head", curses.A_BOLD)))
            for keyname, label in rowset:
                lines.append(("  %-24s %s" % (keyname, label), p("text")))
            lines.append(("", 0))
        lines.append(("WO LIEGT WAS", p("head", curses.A_BOLD)))
        for i in info:
            lines.append(("  " + i, p("dim")))
        if self.cfg.problems:
            lines.append(("", 0))
            lines.append(("PROBLEME IN DER KONFIGURATION", p("err", curses.A_BOLD)))
            for prob in self.cfg.problems[:8]:
                for chunk in wrap("  " + prob, 70):
                    lines.append((chunk, p("err")))

        self._scroll_overlay("Hilfe  ·  Tastenbelegung", lines)

    def _scroll_overlay(self, title: str, lines: list[tuple[str, int]]) -> None:
        top = 0
        while True:
            h, w = self.scr.getmaxyx()
            bw = min(w - 4, 82)
            bh = min(h - 2, len(lines) + 4)
            x = (w - bw) // 2
            y = (h - bh) // 2
            rows = bh - 4
            top = max(0, min(top, max(0, len(lines) - rows)))
            self.draw()
            self.panel(y, x, bh, bw, title,
                       "%s/%s scrollen · q schliessen" % (self.g["up"], self.g["down"]))
            for i in range(rows):
                if top + i >= len(lines):
                    break
                text, attr = lines[top + i]
                self.put(y + 2 + i, x + 3, ell(text, bw - 6, self.g),
                         attr or self.pal("text"))
            if len(lines) > rows:
                self.put(y + bh - 1, x + 3, " %d-%d/%d " % (
                    top + 1, min(top + rows, len(lines)), len(lines)), self.pal("faint"))
            self.scr.noutrefresh()
            curses.doupdate()
            ch = self.getch(-1)
            if ch is None:
                continue
            if ch in (curses.KEY_DOWN,) or ch == "j":
                top += 1
            elif ch in (curses.KEY_UP,) or ch == "k":
                top -= 1
            elif ch == curses.KEY_NPAGE:
                top += rows
            elif ch == curses.KEY_PPAGE:
                top -= rows
            elif ch == curses.KEY_HOME or ch == "g":
                top = 0
            elif ch == curses.KEY_END or ch == "G":
                top = len(lines)
            elif ch == curses.KEY_RESIZE:
                continue
            elif ch in ("q", "\x1b", "?") or ch in ENTERS:
                return

    # ------------------------------------------------- Overlay: Eingabefelder
    def ask(self, prompts: list[Prompt], title: str = "Eingabe") -> dict | None:
        g, p = self.g, self.pal
        edits = [LineEdit(pr.default) for pr in prompts]
        cur = 0
        while True:
            h, w = self.scr.getmaxyx()
            bw = min(w - 6, 74)
            bh = min(h - 2, 5 + len(prompts) * 3)
            x = (w - bw) // 2
            y = (h - bh) // 3
            self.draw()
            self.panel(y, x, bh, bw, title,
                       "%s weiter · Esc abbrechen" % g["enter"])
            yy = y + 2
            for i, pr in enumerate(prompts):
                active = (i == cur)
                label = pr.label or pr.name
                if pr.optional:
                    label += "   (optional, leer lassen moeglich)"
                self.put(yy, x + 3, ell(label, bw - 6, g),
                         p("head", curses.A_BOLD) if active else p("dim"))
                fieldw = bw - 8
                val = edits[i].text
                vis = val
                off = 0
                if len(vis) > fieldw - 2:
                    off = max(0, edits[i].pos - (fieldw - 4))
                    vis = val[off:off + fieldw - 2]
                box_attr = p("sel") if active else p("faint")
                self.put(yy + 1, x + 3, " " + vis.ljust(fieldw - 2) + " ",
                         box_attr if active else p("text", curses.A_UNDERLINE))
                if active:
                    try:
                        curses.curs_set(1)
                        self.scr.move(yy + 1, x + 4 + (edits[i].pos - off))
                    except curses.error:
                        pass
                yy += 3
            self.scr.noutrefresh()
            curses.doupdate()

            ch = self.getch(-1)
            if ch is None:
                continue
            if ch == curses.KEY_RESIZE:
                continue
            if ch == "\x1b" or ch == "\x03":
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass
                return None
            if ch in ENTERS:
                if cur < len(prompts) - 1:
                    cur += 1
                    continue
                vals: dict[str, str] = {}
                for pr, ed in zip(prompts, edits):
                    raw = ed.text.strip()
                    if not raw and not pr.optional:
                        cur = prompts.index(pr)
                        self.notify("%s wird gebraucht" % (pr.label or pr.name), "warn")
                        break
                    if not raw:
                        vals[pr.name] = ""
                    else:
                        vals[pr.name] = shlex.quote(raw) if pr.quote else raw
                else:
                    try:
                        curses.curs_set(0)
                    except curses.error:
                        pass
                    return vals
                continue
            if ch == "\t" or ch == curses.KEY_DOWN:
                cur = (cur + 1) % len(prompts)
                continue
            if ch == curses.KEY_BTAB or ch == curses.KEY_UP:
                cur = (cur - 1) % len(prompts)
                continue
            edits[cur].handle(ch)

    # ----------------------------------------------- Overlay: Bestaetigung
    def confirm(self, question: str, cmd: str = "", danger: bool = False) -> bool:
        g, p = self.g, self.pal
        while True:
            h, w = self.scr.getmaxyx()
            bw = min(w - 6, 72)
            qlines = wrap(question, bw - 8)
            clines = wrap(cmd.strip().replace("\n", " ; "), bw - 8)[:4] if cmd else []
            bh = min(h - 2, 6 + len(qlines) + (len(clines) + 1 if clines else 0))
            x = (w - bw) // 2
            y = (h - bh) // 3
            self.draw()
            self.panel(y, x, bh, bw,
                       ("%s Achtung" % g["err"]) if danger else "Bestaetigen",
                       ("nur j bestaetigt · Esc = nein" if danger
                        else "%s / j = ja · n / Esc = nein" % g["enter"]))
            yy = y + 2
            for q in qlines:
                self.put(yy, x + 3, q, p("err", curses.A_BOLD) if danger else p("text"))
                yy += 1
            if clines:
                yy += 1
                for i, c in enumerate(clines):
                    self.put(yy, x + 3, ("%s " % g["cmd"] if i == 0 else "  ") + c,
                             p("cmd"))
                    yy += 1
            tip = "  [j] ja     [n] nein  "
            self.put(y + bh - 2, x + (bw - len(tip)) // 2, tip,
                     p("badge", curses.A_BOLD))
            self.scr.noutrefresh()
            curses.doupdate()
            ch = self.getch(-1)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            if isinstance(ch, str) and ch.lower() in ("j", "y"):
                return True
            if ch in ENTERS:
                return not danger
            if ch in ("n", "N", "\x1b", "\x03", "q"):
                return False

    # ----------------------------------------------- Overlay: Ausgabe-Pager
    def pager(self, job: Job) -> None:
        g, p = self.g, self.pal
        top = 0
        hoff = 0
        wrap_on = True
        follow = True
        search = ""
        killed = 0
        while True:
            h, w = self.scr.getmaxyx()
            y, x = 1, 1
            bh, bw = max(8, h - 2), max(30, w - 2)
            rows = bh - 3
            inner = bw - 6
            count = job.count()

            if follow and job.running:
                top = max(0, count - rows)
            top = max(0, min(top, max(0, count - 1)))

            self.clear_box(y, x, bh, bw, p("text"))
            self.frame(y, x, bh, bw, p("border_hi"))

            # Kopf
            title = ell(" %s " % job.title.splitlines()[0].strip(), bw - 24, g)
            self.put(y, x + 2, title, p("title", curses.A_BOLD))
            if job.running:
                spin = ("|/-\\"[int(time.time() * 6) % 4] if self.ascii
                        else "◐◓◑◒"[int(time.time() * 5) % 4])
                status = " %s laeuft " % spin
                sattr = p("accent", curses.A_BOLD)
            elif job.rc == 0:
                status = " %s fertig  %s " % (g["ok"], human_ms(job.ms))
                sattr = p("ok", curses.A_BOLD)
            else:
                status = " %s rc=%s  %s " % (g["err"], job.rc, human_ms(job.ms))
                sattr = p("err", curses.A_BOLD)
            self.put(y, x + bw - 2 - len(status), status, sattr)

            # Inhalt
            lines = job.view(top, rows + 40)
            plain = job.plain[top:top + rows + 40]
            row = 0
            shown_logical = 0
            for n, runs in enumerate(lines):
                if row >= rows:
                    break
                shown_logical += 1
                hit = bool(search) and search.lower() in (
                    plain[n] if n < len(plain) else "").lower()
                if wrap_on:
                    vlines = wrap_runs(runs, inner) if runs else [[]]
                else:
                    vlines = [runs]
                for ci, vline in enumerate(vlines):
                    if row >= rows:
                        break
                    yy = y + 1 + row
                    self.put(yy, x + 2, (g["tri"] if hit else " ") if ci == 0 else " ",
                             p("accent", curses.A_BOLD))
                    xx = x + 4
                    skip = 0 if wrap_on else hoff
                    for text_run, st in vline:
                        if skip >= len(text_run):
                            skip -= len(text_run)
                            continue
                        piece = text_run[skip:]
                        skip = 0
                        if xx >= x + bw - 2:
                            break
                        xx += self.put(yy, xx, piece,
                                       p.ansi(st.fg, st.bold, st.dim, st.under,
                                              st.rev),
                                       maxw=x + bw - 2 - xx)
                    row += 1

            if count == 0:
                self.put(y + 1, x + 4,
                         "(noch keine Ausgabe)" if job.running else "(keine Ausgabe)",
                         p("faint"))

            # Fusszeile des Pagers
            fy = y + bh - 1
            left = (" %d-%d/%d " % (top + 1, min(top + shown_logical, count), count)
                    if count else " 0 ")
            self.put(fy, x + 2, left, p("faint"))
            keys = [("j/k", "scrollen"), ("g/G", "Anfang/Ende"),
                    ("u", "Umbruch " + ("an" if wrap_on else "aus")),
                    ("f", "mitlaufen " + ("an" if follow else "aus")),
                    ("/", "suchen"), ("s", "speichern"), ("r", "erneut")]
            if job.running:
                keys.append(("^C", "abbrechen"))
            keys.append(("q", "zu"))
            tail = (" · ").join("%s %s" % (k, v) for k, v in keys)
            tail = " " + ell(tail, bw - 8 - len(left), g) + " "
            self.put(fy, x + bw - 2 - len(tail), tail, p("dim"))
            if job.truncated:
                self.put(y + bh - 1, x + 2 + len(left) + 1, "[gekuerzt]", p("warn"))

            self.scr.noutrefresh()
            curses.doupdate()

            ch = self.getch(120 if job.running else -1)
            if ch is None:
                continue
            if ch == curses.KEY_RESIZE:
                continue
            if ch in ("q", "\x1b") or ch in ENTERS:
                if job.running:
                    job.signal(signal.SIGTERM)
                return
            if ch in ("\x03", "K"):
                if job.running:
                    killed += 1
                    job.signal(signal.SIGKILL if killed > 1 else signal.SIGTERM)
                    self.notify("Abbruchsignal gesendet", "warn")
                continue
            if ch == "j" or ch == curses.KEY_DOWN:
                top += 1
                follow = False
            elif ch == "k" or ch == curses.KEY_UP:
                top -= 1
                follow = False
            elif ch == curses.KEY_NPAGE or ch == " ":
                top += rows
                follow = False
            elif ch == curses.KEY_PPAGE:
                top -= rows
                follow = False
            elif ch == "g" or ch == curses.KEY_HOME:
                top = 0
                follow = False
            elif ch == "G" or ch == curses.KEY_END:
                top = max(0, count - rows)
                follow = True
            elif ch == "l" or ch == curses.KEY_RIGHT:
                hoff += 8
                wrap_on = False
            elif ch == "h" or ch == curses.KEY_LEFT:
                hoff = max(0, hoff - 8)
            elif ch == "u":
                wrap_on = not wrap_on
                hoff = 0
            elif ch == "f":
                follow = not follow
            elif ch == "s":
                path = job.save()
                self.notify("gespeichert: %s" % path if path else "Speichern fehlgeschlagen",
                            "ok" if path else "err")
            elif ch == "r":
                if job.running:
                    job.signal(signal.SIGTERM)
                    time.sleep(0.1)
                fresh = Job(job.cmd, job.cwd, job.title)
                fresh.start()
                job = fresh
                top, follow = 0, True
            elif ch == "/":
                res = self.ask([Prompt(name="s", label="In der Ausgabe suchen",
                                       default=search, quote=False)], "Suche")
                if res:
                    search = res["s"]
                    for i, line in enumerate(job.plain[top + 1:], start=top + 1):
                        if search.lower() in line.lower():
                            top, follow = i, False
                            break
            elif ch in ("n", "N") and search:
                rng = range(top + 1, count) if ch == "n" else range(top - 1, -1, -1)
                for i in rng:
                    if i < len(job.plain) and search.lower() in job.plain[i].lower():
                        top, follow = i, False
                        break

    # ------------------------------------------ Overlay: alle Befehle suchen
    def menu_path(self, target: str) -> list[str]:
        """Weg von root zu einem Menue finden (fuer Breadcrumb)."""
        if target == "root":
            return ["root"]
        seen = {"root"}
        queue: list[list[str]] = [["root"]]
        while queue:
            path = queue.pop(0)
            menu = self.cfg.menus.get(path[-1])
            if not menu:
                continue
            for it in menu.items:
                if it.goto and it.goto not in seen:
                    nxt = path + [it.goto]
                    if it.goto == target:
                        return nxt
                    seen.add(it.goto)
                    queue.append(nxt)
        return ["root", target] if target in self.cfg.menus else ["root"]

    def all_commands(self) -> list[tuple[Item, str]]:
        out: list[tuple[Item, str]] = []
        for mid in self.cfg.order:
            menu = self.cfg.menus[mid]
            crumb = " %s " % self.g["sep"]
            label = crumb.join(self.menu_for(m).title for m in self.menu_path(mid))
            for it in menu.items:
                if it.is_heading or it.kind == "noop":
                    continue
                out.append((it, label))
        return out

    def palette(self) -> None:
        g, p = self.g, self.pal
        pool = self.all_commands()
        ed = LineEdit()
        sel = 0
        top = 0
        while True:
            q = ed.text.strip()
            if q:
                scored = []
                for it, path in pool:
                    hay = "%s %s %s %s" % (it.label, path, it.desc, " ".join(it.tags))
                    sc = fuzzy(q, hay)
                    if sc is not None:
                        scored.append((-sc, it.label, it, path))
                scored.sort()
                hits = [(it, path) for _, _, it, path in scored]
            else:
                hits = list(pool)
            sel = max(0, min(sel, max(0, len(hits) - 1)))

            h, w = self.scr.getmaxyx()
            bw = min(w - 4, 96)
            bh = min(h - 2, 22)
            x = (w - bw) // 2
            y = max(1, (h - bh) // 4)
            rows = bh - 4
            if sel < top:
                top = sel
            if sel >= top + rows:
                top = sel - rows + 1
            top = max(0, min(top, max(0, len(hits) - rows)))

            self.draw()
            self.panel(y, x, bh, bw, "Alle Befehle  ·  %d" % len(hits),
                       "%s ausfuehren · Esc zu" % g["enter"])
            self.put(y + 1, x + 2, " %s " % g["sel"], p("accent", curses.A_BOLD))
            self.put(y + 1, x + 5, ell(ed.text or "tippen zum Filtern …",
                                       bw - 8, g),
                     p("title") if ed.text else p("faint"))
            self.put(y + 2, x + 1, g["h"] * (bw - 2), p("faint"))

            for i in range(rows):
                idx = top + i
                if idx >= len(hits):
                    break
                it, path = hits[idx]
                yy = y + 3 + i
                active = (idx == sel)
                if active:
                    self.put(yy, x + 1, " " * (bw - 2), p("sel"))
                base = p("sel") if active else p("text")
                self.put(yy, x + 2, "%s " % self.icon_for(it),
                         base if active else p("accent"))
                lw = max(10, (bw - 10) // 2)
                self.put(yy, x + 5, ell(it.label, lw, g),
                         (base | curses.A_BOLD) if active else p("text"))
                self.put(yy, x + 6 + lw, ell(path, bw - 8 - lw, g),
                         base if active else p("faint"))
            if not hits:
                self.put(y + 4, x + 5, "kein Treffer", p("dim"))

            try:
                curses.curs_set(1)
                self.scr.move(y + 1, min(x + 5 + ed.pos, x + bw - 3))
            except curses.error:
                pass
            self.scr.noutrefresh()
            curses.doupdate()

            ch = self.getch(-1)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            if ch in ("\x1b", "\x03"):
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass
                return
            if ch in ENTERS:
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass
                if not hits:
                    return
                it, _ = hits[sel]
                self.stack = self.menu_path(it.menu_id)
                items = self.menu_for(it.menu_id).items
                if it in items:
                    self.edit.set("")
                    self.filtering = False
                    self.set_sel(items.index(it))
                self.activate(it)
                return
            if ch == curses.KEY_DOWN or ch == "\x0e":
                sel += 1
                continue
            if ch == curses.KEY_UP or ch == "\x10":
                sel -= 1
                continue
            if ch == curses.KEY_NPAGE:
                sel += rows
                continue
            if ch == curses.KEY_PPAGE:
                sel -= rows
                continue
            if ed.handle(ch):
                sel = 0
                top = 0

    # ------------------------------------------------ Overlay: Ordner waehlen
    def browse(self, start: str | None = None) -> str | None:
        g, p = self.g, self.pal
        here = Path(start or os.getcwd()).resolve()
        sel = 0
        ed = LineEdit()
        while True:
            try:
                entries = sorted(
                    [e for e in os.scandir(here) if e.is_dir() and not e.name.startswith(".")],
                    key=lambda e: e.name.lower())
                hidden = sorted(
                    [e for e in os.scandir(here) if e.is_dir() and e.name.startswith(".")],
                    key=lambda e: e.name.lower())
                entries += hidden
                names = [e.name for e in entries]
                err = ""
            except Exception as exc:
                names, err = [], str(exc)
            q = ed.text.strip()
            if q:
                scored = []
                for n in names:
                    sc = fuzzy(q, n)
                    if sc is not None:
                        scored.append((-sc, n))
                scored.sort()
                names = [n for _, n in scored]
            rowsdata = [".."] + names
            sel = max(0, min(sel, len(rowsdata) - 1))

            h, w = self.scr.getmaxyx()
            bw = min(w - 4, 80)
            bh = min(h - 2, 20)
            x = (w - bw) // 2
            y = max(1, (h - bh) // 4)
            rows = bh - 5
            top = max(0, min(sel - rows // 2, max(0, len(rowsdata) - rows)))

            self.draw()
            self.panel(y, x, bh, bw, "Verzeichnis wechseln",
                       "%s hinein · o hierher wechseln · Esc zu" % g["enter"])
            self.put(y + 1, x + 2, "%s %s" % (g["home"],
                     ell_left(short_path(str(here)), bw - 8, g)),
                     p("path", curses.A_BOLD))
            self.put(y + 2, x + 1, g["h"] * (bw - 2), p("faint"))
            for i in range(rows):
                idx = top + i
                if idx >= len(rowsdata):
                    break
                name = rowsdata[idx]
                yy = y + 3 + i
                active = (idx == sel)
                if active:
                    self.put(yy, x + 1, " " * (bw - 2), p("sel"))
                base = p("sel") if active else p("text")
                icon = ".." if name == ".." else g["folder"]
                self.put(yy, x + 3, "%-2s " % icon, base if active else p("accent"))
                self.put(yy, x + 7, ell(name if name != ".." else "(eine Ebene hoch)",
                                        bw - 10, g),
                         (base | curses.A_BOLD) if active else p("text"))
            if err:
                self.put(y + 3, x + 3, ell("Fehler: " + err, bw - 6, g), p("err"))
            if ed.text:
                self.put(y + bh - 2, x + 3, "/ %s" % ell(ed.text, bw - 8, g), p("accent"))

            self.scr.noutrefresh()
            curses.doupdate()

            ch = self.getch(-1)
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            if ch in ("\x1b", "\x03", "q"):
                return None
            if ch in ("o", "O"):
                return str(here)
            if ch in ENTERS or ch == curses.KEY_RIGHT:
                name = rowsdata[sel]
                here = (here.parent if name == ".." else (here / name)).resolve()
                sel = 0
                ed.set("")
                continue
            if ch in BACKSPACES or ch == curses.KEY_LEFT:
                if ed.text:
                    ed.handle(ch)
                else:
                    here = here.parent.resolve()
                    sel = 0
                continue
            if ch == curses.KEY_DOWN:
                sel += 1
                continue
            if ch == curses.KEY_UP:
                sel -= 1
                continue
            if ch == curses.KEY_NPAGE:
                sel += rows
                continue
            if ch == curses.KEY_PPAGE:
                sel -= rows
                continue
            if isinstance(ch, str) and ch.isprintable():
                ed.handle(ch)
                sel = 0

    # ------------------------------------------------------------ Ausfuehren
    def run_interactive(self, cmd: str, cwd: str) -> int | None:
        rc: int | None = None
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        self.scr.clear()
        self.scr.refresh()
        curses.def_prog_mode()
        curses.endwin()
        try:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.write("\x1b[1m$ %s\x1b[0m\n\n" % cmd.strip().splitlines()[0])
            sys.stdout.flush()
            env = dict(os.environ)
            env["CI_SHELL"] = "1"
            rc = subprocess.call([pick_shell(), "-c", cmd], cwd=cwd, env=env)
        except KeyboardInterrupt:
            rc = 130
        except Exception as exc:
            rc = 127
            sys.stdout.write("\nFehler: %s\n" % exc)
        finally:
            try:
                sys.stdout.write("\n\x1b[2m-- beendet (rc=%s) -- Enter bringt dich "
                                 "zurueck zu CI --\x1b[0m\n" % rc)
                sys.stdout.flush()
                try:
                    sys.stdin.readline()
                except Exception:
                    pass
            except Exception:
                pass
            curses.reset_prog_mode()
            self.scr.clear()
            self.scr.refresh()
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        return rc

    def execute(self, item: Item, cmd_override: str | None = None) -> None:
        template = cmd_override if cmd_override is not None else item.run
        if not template:
            return
        values: dict[str, str] = {}
        if item.prompts:
            res = self.ask(item.prompts, title=item.label)
            if res is None:
                self.notify("abgebrochen", "warn", 2)
                return
            values = res
        cmd = substitute(template, values)
        # Aus der Vorlage ermitteln, nicht aus dem Ergebnis: sonst gelten
        # eingesetzte Werte wie curls %{http_code} als fehlende Platzhalter.
        open_names = sorted({n for n in placeholders(template) if n not in values})
        if open_names:
            self.notify("Platzhalter ohne Wert: %s" % ", ".join(open_names),
                        "warn", 6)
        if item.confirm:
            if not self.confirm(item.confirm, cmd, danger="gefaehrlich" in item.tags):
                self.notify("nicht ausgefuehrt", "info", 2)
                return
        cwd = os.getcwd()
        if item.cwd:
            cand = os.path.abspath(os.path.expanduser(item.cwd))
            if os.path.isdir(cand):
                cwd = cand
            else:
                self.notify("Verzeichnis gibt es nicht: %s" % item.cwd, "err")
                return

        if item.interactive:
            t0 = time.time()
            rc = self.run_interactive(cmd, cwd)
            ms = (time.time() - t0) * 1000.0
        else:
            job = Job(cmd, cwd, title=item.label or cmd)
            job.start()
            self.last_job = job
            self.pager(job)
            rc, ms = job.rc, job.ms
        self.state.record(item.uid, rc, ms)
        log_history(cmd, cwd, rc)
        self.ctx.poke()
        if rc not in (0, None):
            self.notify("%s endete mit rc=%s" % (item.label, rc), "warn", 5)

    def activate(self, item: Item | None) -> None:
        if item is None:
            return
        if item.missing:
            self.notify("%s ist nicht installiert -- Eintrag inaktiv"
                        % ", ".join(item.missing), "err", 5)
            return
        if item.goto:
            if item.goto not in self.cfg.menus:
                self.notify("Menue '%s' gibt es nicht" % item.goto, "err")
                return
            self.stack.append(item.goto)
            self.edit.set("")
            self.filtering = False
            return
        if item.builtin:
            self.builtin(item)
            return
        if item.chdir:
            target = os.path.abspath(os.path.expanduser(item.chdir))
            self.chdir(target)
            return
        if item.run:
            self.execute(item)
            return
        self.notify("Dieser Eintrag macht nichts", "info", 2)

    def chdir(self, target: str) -> None:
        try:
            os.chdir(target)
        except Exception as exc:
            self.notify("Wechsel fehlgeschlagen: %s" % exc, "err")
            return
        self.state.data["last_dir"] = target
        self.state.save()
        self.ctx.poke()
        self.notify("jetzt in %s" % short_path(target), "ok")

    def builtin(self, item: Item) -> None:
        name = item.builtin
        if name == "favorites":
            self.stack.append("@fav")
            self.edit.set("")
        elif name == "history":
            self.stack.append("@hist")
            self.edit.set("")
        elif name == "browse":
            path = self.browse()
            if path:
                self.chdir(path)
        elif name == "shell":
            res = self.ask([Prompt(name="cmd", label="Shell-Befehl", quote=False)],
                           "Freier Befehl")
            if not res or not res["cmd"].strip():
                return
            cmd = res["cmd"]
            tmp = Item(label=cmd, run=cmd, menu_id="@shell", key="")
            job = Job(cmd, os.getcwd(), title=cmd)
            job.start()
            self.last_job = job
            self.pager(job)
            log_history(cmd, os.getcwd(), job.rc)
            self.state.record(tmp.uid, job.rc, job.ms)
            self.ctx.poke()
        elif name == "help":
            self.view_help()
        elif name == "palette":
            self.palette()
        elif name == "theme":
            self.cycle_theme()
        elif name == "reload":
            self.reload()
        elif name == "edit_config":
            path = self.cfg.path or MENU_FILE
            if not path.exists():
                path.write_text(DEFAULT_MENU, encoding="utf-8")
            editor = os.environ.get("EDITOR") or ("nano" if have("nano") else "vi")
            self.run_interactive("%s %s" % (editor, shlex.quote(str(path))), os.getcwd())
            self.reload()
        elif name == "quit":
            self.quit = True
        elif name == "back":
            self.back()
        else:
            self.notify("Unbekannte Funktion: %s" % name, "err")

    # -------------------------------------------------------------- Aktionen
    def back(self) -> None:
        if self.filter:
            self.edit.set("")
            self.filtering = False
            return
        if len(self.stack) > 1:
            self.stack.pop()
            self.edit.set("")
            self.filtering = False
        else:
            self.notify("Du bist schon im Hauptmenue · q beendet CI", "info", 3)

    def cycle_theme(self) -> None:
        try:
            i = THEME_ORDER.index(self.pal.theme)
        except ValueError:
            i = -1
        nxt = THEME_ORDER[(i + 1) % len(THEME_ORDER)]
        self.pal.load(nxt)
        self.apply_background()
        self.state.data["theme"] = nxt
        self.state.save()
        self.notify("Farbschema: %s" % nxt, "ok", 2)

    def reload(self) -> None:
        cfg = ensure_config()
        self.cfg = cfg
        self.g = pick_glyphs(cfg.glyphs)
        self.ascii = (self.g["v"] == "|")
        keep = [m for m in self.stack if m in cfg.menus or m.startswith("@")]
        self.stack = keep or ["root"]
        if cfg.problems:
            self.notify(cfg.problems[0], "err", 8)
        else:
            self.notify("Konfiguration neu geladen", "ok", 3)

    def toggle_fav(self) -> None:
        it = self.selected()
        if it is None or it.is_heading or it.kind == "noop":
            return
        if it.menu_id.startswith("@") and it.menu_id != "@fav":
            self.notify("Favoriten gehen nur bei echten Menue-Eintraegen", "warn", 3)
            return
        on = self.state.toggle_fav(it)
        self.notify("%s %s" % (self.g["star"] if on else self.g["nostar"],
                               "als Favorit gespeichert" if on else "aus Favoriten entfernt"),
                    "ok", 2)

    # ------------------------------------------------------------ Tasteneingabe
    def getch(self, timeout: int = 1000):
        try:
            self.scr.timeout(timeout)
        except curses.error:
            pass
        try:
            ch = self.scr.get_wch()
        except curses.error:
            return None
        except KeyboardInterrupt:
            return "\x03"
        if ch != "\x1b":
            return ch
        # Manche Terminals (tmux, aeltere SSH-Ketten) schicken Sondertasten
        # als rohe Escape-Folge. Kurz nachschauen, ob noch etwas kommt.
        seq = ""
        try:
            self.scr.timeout(30)
            while len(seq) < 6:
                try:
                    nxt = self.scr.get_wch()
                except (curses.error, KeyboardInterrupt):
                    break
                if not isinstance(nxt, str):
                    break
                seq += nxt
                if seq in ESC_SEQUENCES:
                    return ESC_SEQUENCES[seq]
                if seq[-1].isalpha() or seq[-1] == "~":
                    break
        finally:
            try:
                self.scr.timeout(timeout)
            except curses.error:
                pass
        return ESC_SEQUENCES.get(seq, "\x1b")

    def hotkey_item(self, ch: str) -> Item | None:
        for it in self.visible():
            if it.key and it.key == ch:
                return it
        return None

    def handle(self, ch) -> None:
        # --- Filtermodus: Tippen landet im Filter
        if self.filtering:
            if ch == "\x1b":
                self.edit.set("")
                self.filtering = False
                return
            if ch in ENTERS:
                self.filtering = False
                return
            if ch in BACKSPACES and not self.edit.text:
                self.filtering = False
                return
            if ch in (curses.KEY_DOWN, curses.KEY_UP, curses.KEY_NPAGE,
                      curses.KEY_PPAGE):
                pass  # unten normal behandeln
            elif self.edit.handle(ch):
                self.move(0, absolute=0)
                return

        if ch == curses.KEY_RESIZE or ch == "\x0c":
            self.scr.clear()
            return
        if ch == "\x03":                        # Strg-C
            self.quit = True
            return
        if ch == "\x10":                        # Strg-P
            self.palette()
            return
        if ch == "\x12":                        # Strg-R
            self.reload()
            return
        if ch == "\x14":                        # Strg-T
            self.cycle_theme()
            return
        if ch == "\x02":                        # Strg-B
            self.toggle_opaque()
            return
        if ch == "\x0f":                        # Strg-O
            if self.last_job is not None:
                self.pager(self.last_job)
            else:
                self.notify("noch keine Ausgabe da", "info", 2)
            return
        if ch == curses.KEY_MOUSE:
            self.handle_mouse()
            return

        # --- Navigation
        if ch in (curses.KEY_DOWN, "\x0e") or ch == "\t":
            self.move(1)
            return
        if ch in (curses.KEY_UP,) or ch == curses.KEY_BTAB:
            self.move(-1)
            return
        if ch == curses.KEY_NPAGE:
            self.move(10)
            return
        if ch == curses.KEY_PPAGE:
            self.move(-10)
            return
        if ch == curses.KEY_HOME:
            self.move(0, absolute=0)
            return
        if ch == curses.KEY_END:
            self.move(0, absolute=-1)
            return
        if ch in ENTERS or ch == curses.KEY_RIGHT:
            self.activate(self.selected())
            return
        if ch in BACKSPACES or ch == curses.KEY_LEFT or ch == "\x1b":
            self.back()
            return

        if not isinstance(ch, str):
            return

        # --- Globale Einzeltasten
        if ch == "q":
            self.quit = True
            return
        if ch == "/":
            self.filtering = True
            return
        if ch == "?":
            self.view_help()
            return
        if ch == "*":
            self.toggle_fav()
            return
        if ch == "!":
            self.builtin(Item(builtin="shell"))
            return

        # --- Hotkeys der Eintraege
        if ch not in RESERVED:
            it = self.hotkey_item(ch)
            if it is not None:
                items = self.visible()
                self.set_sel(items.index(it))
                self.draw()
                self.activate(it)
                return

        # --- vi-Navigation, nur wenn kein Eintrag diesen Hotkey hat
        if ch == "j":
            self.move(1)
            return
        if ch == "k":
            self.move(-1)
            return
        if ch == "g":
            self.move(0, absolute=0)
            return
        if ch == "G":
            self.move(0, absolute=-1)
            return
        if ch.isdigit() and ch != "0":
            self.move(0, absolute=int(ch) - 1)
            return

    def handle_mouse(self) -> None:
        try:
            _id, mx, my, _z, bstate = curses.getmouse()
        except curses.error:
            return
        up = getattr(curses, "BUTTON4_PRESSED", 0)
        down = getattr(curses, "BUTTON5_PRESSED", 0)
        if up and (bstate & up):
            self.move(-3)
            return
        if down and (bstate & down):
            self.move(3)
            return
        if bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_PRESSED:
            h, w, listw, detailw, rows = self.layout()
            if 3 <= my < 3 + rows and 1 <= mx <= listw:
                key = self.current_id + "|" + self.filter
                idx = self.scroll.get(key, 0) + (my - 3)
                items = self.visible()
                if 0 <= idx < len(items) and not items[idx].is_heading:
                    if idx == self.sel_index():
                        self.activate(items[idx])
                    else:
                        self.set_sel(idx)

    # ----------------------------------------------------------------- Lauf
    def run(self) -> None:
        while not self.quit:
            self.draw()
            ch = self.getch(1000)
            if ch is None:
                continue
            try:
                self.handle(ch)
            except Exception as exc:
                self.notify("Fehler: %s" % exc, "err", 6)


# --------------------------------------------------------------------------- #
#  Start
# --------------------------------------------------------------------------- #

def _curses_main(scr, cfg: Config, state: State) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    scr.keypad(True)
    try:
        curses.set_escdelay(25)
    except Exception:
        pass
    try:
        curses.mousemask(curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED |
                         getattr(curses, "BUTTON4_PRESSED", 0) |
                         getattr(curses, "BUTTON5_PRESSED", 0))
    except Exception:
        pass
    app = App(scr, cfg, state)
    app.ascii = (app.g["v"] == "|")
    try:
        app.run()
    finally:
        app.ctx.stop()


def main(argv: list[str]) -> int:
    args = argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__.strip())
        print("\nOptionen:")
        print("  --ascii           nur ASCII-Zeichen benutzen")
        print("  --unicode         Unicode-Zeichen erzwingen")
        print("  --theme NAME      %s" % " | ".join(THEME_ORDER))
        print("  --config PFAD     andere menu.toml benutzen")
        print("  --no-detail       rechtes Panel ausschalten")
        print("  --opaque          eigener Hintergrund (bei transparentem Terminal)")
        print("  --transparent     Terminal-Hintergrund durchlassen")
        print("  --dump-config     eingebaute Standard-Konfiguration ausgeben")
        print("  --check           Konfiguration pruefen und beenden")
        print("  --version         Version ausgeben")
        return 0
    if "--version" in args:
        print("CI %s" % VERSION)
        return 0
    if "--dump-config" in args:
        sys.stdout.write(DEFAULT_MENU)
        return 0

    global MENU_FILE, CONFIG_DIR, STATE_FILE, HISTORY_FILE, OUTPUT_DIR
    if "--config" in args:
        i = args.index("--config")
        if i + 1 < len(args):
            MENU_FILE = Path(args[i + 1]).expanduser()

    cfg = ensure_config()
    if "--ascii" in args:
        cfg.glyphs = "ascii"
    if "--unicode" in args:
        cfg.glyphs = "unicode"
    if "--no-detail" in args:
        cfg.detail = False
    if "--opaque" in args:
        cfg.opaque = True
    if "--transparent" in args:
        cfg.opaque = False
    if "--theme" in args:
        i = args.index("--theme")
        if i + 1 < len(args) and args[i + 1] in THEMES:
            cfg.theme = args[i + 1]

    if "--check" in args:
        print("Konfiguration: %s" % (cfg.path or "(eingebaut)"))
        print("Menues: %d" % len(cfg.menus))
        total = sum(len([i for i in m.items if not i.is_heading])
                    for m in cfg.menus.values())
        print("Eintraege: %d" % total)
        for mid in cfg.order:
            m = cfg.menus[mid]
            keys = [i.key for i in m.items if i.key]
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            bad = sorted({k for k in keys if k in RESERVED})
            note = []
            if dupes:
                note.append("doppelte Hotkeys: %s" % " ".join(dupes))
            if bad:
                note.append("belegte Hotkeys: %s" % " ".join(bad))
            print("  %-14s %3d Eintraege %s" % (
                mid, len([i for i in m.items if not i.is_heading]),
                ("-- " + "; ".join(note)) if note else ""))
        if cfg.problems:
            print("\nProbleme:")
            for p in cfg.problems:
                print("  - %s" % p)
            return 1
        print("\nAlles in Ordnung.")
        return 0

    if not sys.stdout.isatty():
        sys.stderr.write("CI braucht ein Terminal.\n")
        return 2

    state = State()
    if cfg.theme in THEMES and "--theme" in args:
        state.data["theme"] = cfg.theme
    if "--opaque" in args or "--transparent" in args:
        state.data["opaque"] = cfg.opaque

    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(_curses_main, cfg, state)
    except KeyboardInterrupt:
        pass

    # Wenn die Shell-Funktion aus shell-init.sh gestartet hat, bleibt die
    # Shell nach dem Beenden in dem Verzeichnis, in dem CI gerade war.
    handoff = os.environ.get("CI_SHELL_CWD_FILE")
    if handoff:
        try:
            Path(handoff).write_text(os.getcwd(), encoding="utf-8")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
