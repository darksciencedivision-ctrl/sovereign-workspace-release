"""LlamaCppBackend — translates request semantics to llama.cpp. No routing policy."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.request

# F-016. Loopback backend only; force a direct connection past any configured proxy.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LLAMACPP_LOCAL_ADAPTER = "llamacpp_local"


def build_interactive_llamacpp_command(executable: str, *, model: str) -> list[str]:
    """Build a contained llama.cpp CLI command for one server-advertised model id.

    A model root may be supplied when ``/v1/models`` returns a logical filename.  The model id is
    otherwise passed verbatim as the ``-m`` value; no download, shell expansion, or cloud fallback
    is introduced by this builder.
    """
    if not isinstance(model, str) or not model.strip() or any(c in model for c in "\r\n\x00"):
        raise ValueError("llama.cpp model id must be a non-empty single-line string")
    root = os.environ.get("SOVEREIGN_LLAMACPP_MODEL_ROOT", "").strip()
    candidate = Path(model)
    if root and not candidate.is_absolute():
        candidate = Path(root) / model
    model_arg = str(candidate) if candidate.exists() else model
    return [str(executable), "-m", model_arg]


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
        with _NO_PROXY_OPENER.open(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def list_models(self) -> dict:
        errors = []
        for path in ("/v1/models", "/models"):
            try:
                with _NO_PROXY_OPENER.open(f"{self.host}{path}", timeout=5) as r:
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
