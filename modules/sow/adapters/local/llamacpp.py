"""LlamaCppBackend — translates request semantics to llama.cpp. No routing policy."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class LlamaCppBackend:
    def __init__(self, host: str = "http://127.0.0.1:5183") -> None:
        self.host = host.rstrip("/")
        self.name = "llamacpp"
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        body = json.dumps({
            "model": "",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def list_models(self) -> dict:
        try:
            with urllib.request.urlopen(f"{self.host}/models", timeout=5) as r:
                return {"supported": True, "payload": json.loads(r.read().decode("utf-8"))}
        except Exception as e:
            return {"supported": True, "ok": False, "reason": str(e)}

    def load_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "load is requested via router /models/load; this backend does not own routing"}

    def unload_model(self, artifact_id: str) -> dict:
        return {"supported": False, "reason": "unload is requested via router /models/unload; this backend does not own routing"}

    def cancel(self, request_id: str) -> dict:
        return {"supported": False, "reason": "cancel is a server-side abort; not a routing policy"}

    def health(self) -> dict:
        try:
            urllib.request.urlopen(f"{self.host}/models", timeout=3)
            return {"supported": True, "ok": True}
        except Exception as e:
            return {"supported": True, "ok": False, "reason": str(e)}

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
