#!/usr/bin/env sh
#
# Prepare a restored Debate Table checkout for first run. Linux / macOS.
#
# Checks the Python version, creates a virtual environment, installs from
# requirements.lock.txt, then CHECKS that Ollama responds and that every model
# named in config.json is present.
#
# This script never installs, removes or replaces a model, and never edits
# config.json. Missing models are reported with the exact `ollama pull` command
# to run; you run it yourself.
#
# Every failure prints a message naming the missing prerequisite, not a traceback.
#
#   usage:  sh scripts/bootstrap.sh [--skip-ollama]
#
# NOTE ON VERIFICATION STATUS: this script's Windows counterpart
# (scripts/bootstrap.ps1) was executed end to end during the v1.2-phase1-baseline
# snapshot. This POSIX version was NOT executed -- the snapshot was produced on a
# Windows host and no non-Windows machine was available. See the "Known
# limitations" section of SNAPSHOT-RESTORE.md.

set -eu

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
VERIFIED_PYTHON="3.14.6"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")
VENV_DIR="$ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
LOCKFILE="$ROOT/requirements.lock.txt"
CONFIG_PATH="$ROOT/config.json"

SKIP_OLLAMA=0
for arg in "$@"; do
    case "$arg" in
        --skip-ollama) SKIP_OLLAMA=1 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

FAILED=0
WARNED=0

if [ -t 1 ]; then
    C_CYAN=$(printf '\033[36m'); C_GREEN=$(printf '\033[32m')
    C_YELLOW=$(printf '\033[33m'); C_RED=$(printf '\033[31m')
    C_OFF=$(printf '\033[0m')
else
    C_CYAN=''; C_GREEN=''; C_YELLOW=''; C_RED=''; C_OFF=''
fi

step() { printf '\n%s==> %s%s\n' "$C_CYAN" "$1" "$C_OFF"; }
ok()   { printf '    %sOK    %s%s\n' "$C_GREEN" "$1" "$C_OFF"; }
warn() { printf '    %sWARN  %s%s\n' "$C_YELLOW" "$1" "$C_OFF"; WARNED=1; }
fail() { printf '    %sFAIL  %s%s\n' "$C_RED" "$1" "$C_OFF"; FAILED=1; }

echo "Debate Table -- bootstrap"
echo "Project root: $ROOT"

# --- 1. Python -------------------------------------------------------------
step "Checking Python"

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON=$(command -v "$candidate")
        break
    fi
done
if [ -z "$PYTHON" ]; then
    fail "Python was not found on PATH. Install Python $VERIFIED_PYTHON (or ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+) and re-run."
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo "")
if [ -z "$PY_VERSION" ]; then
    fail "Found '$PYTHON' but could not determine its version. Is it a working Python interpreter?"
    exit 1
fi

if ! "$PYTHON" -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($MIN_PYTHON_MAJOR, $MIN_PYTHON_MINOR) else 1)"; then
    fail "Python $PY_VERSION found at $PYTHON, but this project needs ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} or newer."
    exit 1
fi
ok "Python $PY_VERSION at $PYTHON"
if [ "$PY_VERSION" != "$VERIFIED_PYTHON" ]; then
    warn "This baseline was validated only on Python $VERIFIED_PYTHON. $PY_VERSION satisfies the declared minimum but is untested here."
fi

# --- 2. Lockfile -----------------------------------------------------------
step "Checking lockfile"
if [ ! -f "$LOCKFILE" ]; then
    fail "requirements.lock.txt not found at $LOCKFILE. The restore is incomplete -- re-extract the snapshot."
    exit 1
fi
ok "requirements.lock.txt present"

# --- 3. Virtual environment ------------------------------------------------
step "Creating virtual environment"
if [ -x "$VENV_PYTHON" ]; then
    ok ".venv already exists, reusing it"
else
    if ! "$PYTHON" -m venv "$VENV_DIR" 2>/dev/null || [ ! -x "$VENV_PYTHON" ]; then
        fail "Could not create a virtual environment at $VENV_DIR. On Debian/Ubuntu the venv module ships separately: apt install python3-venv"
        exit 1
    fi
    ok "Created $VENV_DIR"
fi

# --- 4. Dependencies -------------------------------------------------------
step "Installing pinned dependencies"
if ! "$VENV_PYTHON" -m pip install --quiet --disable-pip-version-check -r "$LOCKFILE"; then
    fail "pip could not install from requirements.lock.txt. If you are offline, this step needs network access to PyPI."
    exit 1
fi
ok "Installed all pins from requirements.lock.txt"
warn "requirements.lock.txt was resolved on Windows: uvloop (which uvicorn[standard] uses on this platform) is not pinned in it. The app runs correctly without uvloop, on the default asyncio event loop."

step "Installing pytest (development-only self-check tool)"
if "$VENV_PYTHON" -m pip install --quiet --disable-pip-version-check pytest; then
    ok "pytest installed (deliberately not a runtime dependency -- see README)"
else
    warn "Could not install pytest. The app will still run; you just cannot run the self-check suite."
fi

# --- 5. Ollama and models --------------------------------------------------
if [ "$SKIP_OLLAMA" -eq 1 ]; then
    step "Skipping Ollama checks (--skip-ollama)"
    warn "Ollama not checked. The app starts, but no seat can speak without it."
else
    step "Checking Ollama and the models config.json asks for"

    if [ ! -f "$CONFIG_PATH" ]; then
        fail "config.json not found at $CONFIG_PATH. The restore is incomplete."
        exit 1
    fi

    # P0-04/P0-05: resolve configuration through the canonical policy module.
    EFFECTIVE=$("$VENV_PYTHON" "$SCRIPT_DIR/effective_config.py" "$CONFIG_PATH" 2>&1 || true)
    case "$EFFECTIVE" in
        BADCONFIG*)
            fail "config.json could not be read as JSON: ${EFFECTIVE#BADCONFIG|}"
            printf '          Check it is valid JSON and saved as UTF-8.\n'
            FAILED=1
            ;;
        '')
            fail "The effective-config check did not run. Verify the virtual environment exists."
            FAILED=1
            ;;
        *)
            OLLAMA_URL_EFF=$(printf '%s\n' "$EFFECTIVE" | "$VENV_PYTHON" -c "import json,sys;print(json.load(sys.stdin)['ollama_url'])")
            ENDPOINT_CLASS=$(printf '%s\n' "$EFFECTIVE" | "$VENV_PYTHON" -c "import json,sys;print(json.load(sys.stdin)['endpoint_class'])")
            if [ "$ENDPOINT_CLASS" = "remote" ]; then
                warn "remote Ollama endpoint enabled by operator opt-in ($OLLAMA_URL_EFF); traffic leaves this host"
                warn "the local-first privacy statement does not apply to this configuration"
            fi
            ;;
    esac

    CHECK_OUT=$("$VENV_PYTHON" - "$OLLAMA_URL_EFF" "$CONFIG_PATH" <<'PYEOF' 2>&1 || true
import json, sys, pathlib
try:
    import httpx
except ImportError:
    print("NOHTTPX|"); raise SystemExit(0)
# URL arrives pre-resolved and policy-checked from scripts/effective_config.py.
url = sys.argv[1].rstrip("/").strip()
# Seat/extractor model enumeration is content inspection, not resolution;
# the file has already passed the canonical parse+policy gate above.
cfg = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
wanted = []
for seat in cfg.get("seats", []):
    if seat.get("model"):
        wanted.append((seat["model"], "seat " + str(seat.get("name", "?"))))
if cfg.get("insight_panel") and cfg.get("extractor_model"):
    wanted.append((cfg["extractor_model"], "extractor_model"))
try:
    tags = httpx.get(url + "/api/tags", timeout=10).json()
except Exception as exc:
    print("NOOLLAMA|" + url); raise SystemExit(0)
installed = {m["name"] for m in tags.get("models", [])}
print("URL|" + url)
for name, why in wanted:
    print(("HAVE|" if name in installed else "MISS|") + name + "|" + why)
if not cfg.get("insight_panel") and cfg.get("extractor_model"):
    print("NOTE|extractor_model '" + str(cfg["extractor_model"]) +
          "' is NOT required: insight_panel is false")
PYEOF
)

    echo "$CHECK_OUT" | while IFS='|' read -r kind a b; do
        case "$kind" in
            NOHTTPX)  fail "httpx is missing from the virtual environment; the dependency install did not complete. Delete .venv and re-run this script." ;;
            NOOLLAMA) fail "Ollama did not respond at $a. Start it with 'ollama serve', or install it from https://ollama.com/download." ;;
            BADCONFIG) fail "config.json could not be read as JSON: $a"
                      printf '          Check it is valid JSON and saved as UTF-8.\n' ;;
            URL)      ok "Ollama responded at $a" ;;
            HAVE)     ok "model present: $a  ($b)" ;;
            MISS)     fail "model MISSING: $a  ($b)"
                      printf '          run yourself:  ollama pull %s\n' "$a" ;;
            NOTE)     printf '    NOTE  %s\n' "$a" ;;
        esac
    done
    # the while loop runs in a subshell, so re-derive the failure flag here
    if echo "$CHECK_OUT" | grep -q '^MISS|\|^NOOLLAMA|\|^NOHTTPX|\|^BADCONFIG|'; then
        FAILED=1
    fi
    # Never surface a raw traceback: if nothing recognisable came back, say so plainly.
    if ! echo "$CHECK_OUT" | grep -q '^\(URL\|HAVE\|MISS\|NOTE\|NOOLLAMA\|NOHTTPX\|BADCONFIG\)|'; then
        fail "The model check did not complete. Verify Ollama is running and config.json is valid, then re-run."
    fi
fi

# --- 6. Result -------------------------------------------------------------
echo ""
if [ "$FAILED" -ne 0 ]; then
    printf '%sBOOTSTRAP INCOMPLETE -- resolve the FAIL lines above, then re-run.%s\n' "$C_RED" "$C_OFF"
    exit 1
fi

printf '%sBOOTSTRAP OK%s\n' "$C_GREEN" "$C_OFF"
[ "$WARNED" -ne 0 ] && printf '%s(with warnings above)%s\n' "$C_YELLOW" "$C_OFF"

PORT=$(printf '%s\n' "$EFFECTIVE" | "$VENV_PYTHON" -c "import json,sys;print(json.load(sys.stdin)['port'])")

cat <<EOF

Next steps:

  run the self-check suite
      .venv/bin/python -m pytest tests -q -W error

  start the app
      .venv/bin/python app.py

  then open  http://127.0.0.1:$PORT
  stop it with Ctrl+C
EOF
exit 0
