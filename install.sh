#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  CI installieren
#
#    ./install.sh            installiert nach ~/.local/bin/ci
#    ./install.sh --yes      haengt die Shell-Funktion ohne Rueckfrage an
#    ./install.sh --prefix /usr/local/bin
# ---------------------------------------------------------------------------
set -euo pipefail

PREFIX="${HOME}/.local/bin"
ASSUME_YES=0
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/ci-shell"

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1 ;;
    --prefix) PREFIX="$2"; shift ;;
    -h|--help)
      sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; exit 1 ;;
  esac
  shift
done

say()  { printf '  %s\n' "$*"; }
ok()   { printf '  \033[32m+\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

printf '\n\033[1mCI installieren\033[0m\n\n'

# --- Python pruefen -------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 nicht gefunden. CI braucht Python 3.9 oder neuer." >&2
  exit 1
fi
PYVER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
if ! python3 -c 'import curses' 2>/dev/null; then
  warn "Das Modul curses fehlt (Debian/Ubuntu: apt install python3-curses)."
fi
if ! python3 -c 'import tomllib' 2>/dev/null && ! python3 -c 'import tomli' 2>/dev/null; then
  warn "Python ${PYVER} hat kein tomllib. Bitte: python3 -m pip install --user tomli"
fi
ok "Python ${PYVER}"

# --- Programm ablegen -----------------------------------------------------
mkdir -p "$PREFIX"
install -m 0755 "${SRC_DIR}/ci.py" "${PREFIX}/ci"
ok "installiert: ${PREFIX}/ci"

mkdir -p "$CONFIG_DIR"
if [ ! -f "${CONFIG_DIR}/menu.toml" ]; then
  python3 "${PREFIX}/ci" --dump-config > "${CONFIG_DIR}/menu.toml"
  ok "Konfiguration angelegt: ${CONFIG_DIR}/menu.toml"
else
  say "Konfiguration bleibt wie sie ist: ${CONFIG_DIR}/menu.toml"
fi

# --- Shell-Funktion: Verzeichniswechsel ueberlebt das Beenden -------------
INIT="${CONFIG_DIR}/shell-init.sh"
cat > "$INIT" <<'INITEOF'
# CI -- in die Shell einbinden.  In ~/.bashrc oder ~/.zshrc einlesen:
#   source "${XDG_CONFIG_HOME:-$HOME/.config}/ci-shell/shell-init.sh"
#
# Die Funktion sorgt dafuer, dass das Verzeichnis, in dem CI beim Beenden
# stand, auch in der Shell danach gilt.
ci() {
  local f rc
  f="$(mktemp "${TMPDIR:-/tmp}/ci-cwd.XXXXXX")"
  CI_SHELL_CWD_FILE="$f" command ci "$@"
  rc=$?
  if [ -s "$f" ]; then
    cd -- "$(cat "$f")" || true
  fi
  rm -f "$f"
  return $rc
}
INITEOF
ok "Shell-Anbindung geschrieben: ${INIT}"

SRCLINE="source \"\${XDG_CONFIG_HOME:-\$HOME/.config}/ci-shell/shell-init.sh\""
hooked=0
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  [ -f "$rc" ] || continue
  if grep -Fq "ci-shell/shell-init.sh" "$rc"; then
    say "schon eingebunden in $(basename "$rc")"
    hooked=1
    continue
  fi
  if [ "$ASSUME_YES" = 1 ]; then
    answer=j
  else
    printf '  Zeile in %s eintragen? [j/N] ' "$(basename "$rc")"
    read -r answer </dev/tty || answer=n
  fi
  case "$answer" in
    j|J|y|Y)
      printf '\n# CI\n%s\n' "$SRCLINE" >> "$rc"
      ok "eingetragen in $(basename "$rc")"
      hooked=1 ;;
    *) say "uebersprungen: $(basename "$rc")" ;;
  esac
done
if [ "$hooked" = 0 ]; then
  say "Von Hand eintragen:  ${SRCLINE}"
fi

case ":$PATH:" in
  *":$PREFIX:"*) ;;
  *) warn "${PREFIX} ist nicht im PATH. Eintragen mit:"
     say "  export PATH=\"${PREFIX}:\$PATH\"" ;;
esac

printf '\n\033[1mFertig.\033[0m  Neue Shell oeffnen und  \033[1mci\033[0m  tippen.\n\n'
