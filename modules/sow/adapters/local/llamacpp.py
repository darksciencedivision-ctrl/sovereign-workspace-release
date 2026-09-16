"""LlamaCppBackend — translates request semantics to llama.cpp. No routing policy."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

# F-016. Loopback backend only; force a direct connection past any configured proxy.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LLAMACPP_LOCAL_ADAPTER = "llamacpp_local"


def build_interactive_llamacpp_command(executable: str, *, model: str) -> list[str]:
    """Build the interactive client for one server-advertised model id.

    The configured llama-server is the runtime.  ``llama-cli`` is optional and is never used as a
    hidden fallback; this command starts the workspace's local endpoint client under the exact
    Python executable authorized by the pane supervisor.
    """
    if not isinstance(model, str) or not model.strip() or any(c in model for c in "\r\n\x00"):
        raise ValueError("llama.cpp model id must be a non-empty single-line string")
    host = (os.environ.get("SOVEREIGN_LLAMACPP_HOST")
            or os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL")
            or "http://127.0.0.1:18080").rstrip("/")
    _loopback_host(host)
    return [str(executable), "-m", "adapters.local.llamacpp", "--interactive",
            "--host", host, "--model", model.strip()]


def _loopback_host(host: str) -> str:
    parsed = urlsplit(host)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("llama.cpp endpoint must be loopback HTTP")
    return host.rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = os.environ.get("SOVEREIGN_LLAMA_CPP_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


class LlamaCppBackend:
    def __init__(self, host: str | None = None, *, model: str = "") -> None:
        selected_host = (host or os.environ.get("SOVEREIGN_LLAMACPP_HOST")
                         or os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL")
                         or "http://127.0.0.1:18080")
        self.host = _loopback_host(selected_host)
        self.model = model.strip()
        self.name = "llamacpp"
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256,
                 messages: list[dict[str, str]] | None = None) -> str:
        self.calls += 1
        selected_messages = list(messages or [])
        selected_messages.append({"role": "user", "content": prompt})
        body = json.dumps({
            "model": self.model,
            "messages": selected_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/v1/chat/completions", data=body,
            headers=_headers())
        with _NO_PROXY_OPENER.open(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def list_models(self) -> dict:
        errors = []
        for path in ("/v1/models", "/models"):
            try:
                request = urllib.request.Request(f"{self.host}{path}", headers=_headers())
                with _NO_PROXY_OPENER.open(request, timeout=5) as r:
                    return {"supported": True, "payload": json.loads(r.read().decode("utf-8")),
                            "endpoint": path}
            except Exception as e:  # noqa: BLE001 - backend reports transport failure to caller
                errors.append(f"{path}: {e}")
        return {"supported": True, "ok": False, "reason": "; ".join(errors)}

    def load_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "load is requested via router /models/load; this backend does not own routing"}

    def unload_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "unload is requested via router /models/unload; this backend does not own routing"}

    def cancel(self, request_id: str) -> dict:
        return {"supported": False, "reason": "cancel is a server-side abort; not a routing policy"}

    def health(self) -> dict:
        result = self.list_models()
        return {"supported": True, "ok": bool(result.get("payload")),
                **({} if result.get("payload") else {"reason": result.get("reason", "no model endpoint")})}

    def capabilities(self) -> dict:
        return {"generate": True, "stream": True, "load": False, "unload": False, "cancel": False}

    def metrics(self) -> dict:
        return {
            "supported": True,
            "runtime": self.name,
            "model_id": None,
            "artifact_id": None,
            "request_id": None,
            "load_state": "unknown",
            "fallback_reason": None,
            "calls": self.calls,
        }


def interactive_session(*, host: str, model: str) -> int:
    """Run a long-lived terminal chat against the supervised loopback router."""
    backend = LlamaCppBackend(host, model=model)
    inventory = backend.list_models()
    if not inventory.get("payload"):
        print(f"llama.cpp unavailable: {inventory.get('reason', 'model endpoint unavailable')}",
              file=sys.stderr)
        return 2
    print(f"Local llama.cpp session | {model} | {backend.host}")
    print("Type /exit to close. No cloud fallback is configured.")
    history: list[dict[str, str]] = []
    while True:
        try:
            prompt = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt.strip().lower() in {"/exit", "/quit", "exit", "quit"}:
            return 0
        if not prompt.strip():
            continue
        try:
            answer = backend.generate(prompt, messages=history)
        except Exception as exc:  # the pane must show the local transport failure clearly
            print(f"local llama.cpp request failed: {exc}", file=sys.stderr)
            continue
        print(f"assistant> {answer}")
        history.extend((
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": str(answer)},
        ))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sovereign local llama.cpp terminal client")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--host", default=(os.environ.get("SOVEREIGN_LLAMACPP_HOST")
                                           or os.environ.get("SOVEREIGN_LLAMA_CPP_BASE_URL")
                                           or "http://127.0.0.1:18080"))
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)
    if not args.interactive:
        parser.error("--interactive is required")
    return interactive_session(host=args.host, model=args.model)


if __name__ == "__main__":
    raise SystemExit(main())
