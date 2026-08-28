from pathlib import Path

app = Path("app.py")
src = app.read_text(encoding="utf-8")

old = '''try:
    CONFIG = load_config(CONFIG_PATH)
except ConfigurationError as exc:
    print(f"FATAL: {exc}", file=sys.stderr)
    print(
        "FATAL: refusing to start with a corrupt configuration; "
        "fix config.json (original bytes were left untouched).",
        file=sys.stderr,
    )
    raise SystemExit(2) from None'''
new = '''try:
    CONFIG = load_config(CONFIG_PATH)
    OLLAMA, OLLAMA_ENDPOINT_CLASS = resolve_ollama_base(
        CONFIG["ollama_url"],
        os.environ.get("OLLAMA_URL"),
        CONFIG["allow_remote_ollama"],
        CONFIG_PATH,
    )
except ConfigurationError as exc:
    print(f"FATAL: {exc}", file=sys.stderr)
    print(
        "FATAL: refusing to start; fix config.json"
        " (original bytes were left untouched).",
        file=sys.stderr,
    )
    raise SystemExit(2) from None
if OLLAMA_ENDPOINT_CLASS == "remote":
    # Deliberate opt-in only. Never describe this deployment as local-only.
    print(
        "WARNING: remote Ollama endpoint enabled by operator opt-in;"
        f" traffic will leave this host ({OLLAMA})",
        file=sys.stderr,
    )'''

assert src.count(old) == 1
src = src.replace(old, new, 1)

dup = '''OLLAMA, OLLAMA_ENDPOINT_CLASS = resolve_ollama_base(
    CONFIG["ollama_url"],
    os.environ.get("OLLAMA_URL"),
    CONFIG["allow_remote_ollama"],
    CONFIG_PATH,
)
if OLLAMA_ENDPOINT_CLASS == "remote":
    # Deliberate opt-in only. Never describe this deployment as local-only.
    print(
        "WARNING: remote Ollama endpoint enabled by operator opt-in;"
        f" traffic will leave this host ({OLLAMA})",
        file=sys.stderr,
    )
'''
assert src.count(dup) == 1
src = src.replace(dup, "", 1)

app.write_bytes(src.encode("utf-8"))
print("GUARD_FIX_OK")