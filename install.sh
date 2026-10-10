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

# Die rc-Datei der tatsaechlich benutzten Shell kommt zuerst dran -- und nur
# sie ist wirklich wichtig. Die andere wird nur angeboten, wenn sie existiert.
case "$(basename "${SHELL:-}")" in
  zsh)  RC_LIST=("$HOME/.zshrc" "$HOME/.bashrc"); MY_RC="$HOME/.zshrc" ;;
  bash) RC_LIST=("$HOME/.bashrc" "$HOME/.zshrc"); MY_RC="$HOME/.bashrc" ;;
  fish) RC_LIST=();                               MY_RC="" ;;
  *)    RC_LIST=("$HOME/.bashrc" "$HOME/.zshrc"); MY_RC="" ;;
esac

# Auch nach Strg-C steht noch da, was zu tun ist.
finish() {
  case ":$PATH:" in
    *":$PREFIX:"*) ;;
    *) warn "${PREFIX} ist nicht im PATH. Fuer bash/zsh:"
       say "  echo 'export PATH=\"${PREFIX}:\$PATH\"' >> ${MY_RC:-~/.profile}" ;;
  esac
  if [ "${HOOKED:-0}" = 0 ]; then
    printf '\n  Noch zu tun -- diese Zeile in %s eintragen:\n' "${MY_RC:-deine Shell-Konfiguration}"
    say "  ${SRCLINE}"
    say "  (ohne sie laeuft CI trotzdem, nur der Verzeichniswechsel"
    say "   beim Beenden wirkt dann nicht in der Shell weiter)"
  fi
  printf '\n\033[1mFertig.\033[0m  Neue Shell oeffnen und  \033[1mci\033[0m  tippen.\n\n'
}
trap finish EXIT

HOOKED=0
if [ "${#RC_LIST[@]}" = 0 ]; then
  warn "fish erkannt -- die Shell-Funktion gibt es nur fuer bash und zsh."
  say  "CI selbst laeuft normal; nur der Verzeichniswechsel beim Beenden fehlt."
fi
for rc in ${RC_LIST[@]+"${RC_LIST[@]}"}; do
  [ -f "$rc" ] || continue
  if grep -Fq "ci-shell/shell-init.sh" "$rc"; then
    say "schon eingebunden in $(basename "$rc")"
    HOOKED=1
    continue
  fi
  [ "$HOOKED" = 1 ] && [ "$rc" != "$MY_RC" ] && continue
  label="$(basename "$rc")"
  [ "$rc" = "$MY_RC" ] && label="${label}  (deine Shell)"
  if [ "$ASSUME_YES" = 1 ]; then
    answer=j
  elif [ -r /dev/tty ]; then
    printf '  Zeile in %s eintragen? [J/n] ' "$label"
    read -r answer </dev/tty || answer=n
    [ -z "$answer" ] && answer=j
  else
    answer=n                      # kein Terminal (z. B. in einer Pipeline)
  fi
  case "$answer" in
    n|N)   say "uebersprungen: $(basename "$rc")" ;;
    *)     printf '\n# CI\n%s\n' "$SRCLINE" >> "$rc"
           ok "eingetragen in $(basename "$rc")"
           HOOKED=1 ;;
  esac
done
