"""W-32 — the Python and JavaScript credential classifiers must agree.

W-29 ported the classifier into ``apps/desktop/conductor/launch-source.js`` because the decision is
needed on the Electron main path, which has no Python in it. It recorded the drift risk and handed
the pin here. This is that pin.

WHY PARITY TESTING RATHER THAN A SHARED SERVICE. The two runtimes cannot import each other, and the
operator ruling is explicit that the answer is not another credential-policy configuration system.
So the Python classifier stays the semantic AUTHORITY and this test exercises a pinned vector
through BOTH, requiring identical verdicts. A name that leaves one classifier and not the other
fails here rather than in a child process nobody is watching.

The vector deliberately includes mixed case: Windows env names are case-insensitive to the OS while
a plain-object delete and a Python ``dict`` are not, which is the divergence U105 exists for.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.frontier.provider_cli_common import is_provider_credential_env_key

ROOT = Path(__file__).resolve().parents[2]
LAUNCH_SOURCE = ROOT / "apps" / "desktop" / "conductor" / "launch-source.js"

#: The pinned parity vector. Each entry is exercised through both classifiers and the verdicts must
#: match. Positives cover the exact-name, prefix and substring nets; negatives cover the names a
#: scrub must NOT eat, because a classifier that removes PATH proves nothing about the scrub.
PARITY_VECTOR: tuple[str, ...] = (
    # exact authority names, including the three W-32 is about
    "NODE_PATH", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS",
    "XAI_API_KEY", "XAI_API_BASE_URL", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT", "GOOGLE_GENAI_API_KEY",
    "ANTIGRAVITY_API_KEY",
    # prefix net
    "XAI_SOMETHING_NEW", "GROK_WHATEVER", "GEMINI_X", "GOOGLE_X", "ANTIGRAVITY_X",
    # substring net
    "MY_SESSION_TOKEN", "SOME_SECRET", "AN_API_KEY", "AN_APIKEY", "A_PASSWORD", "SSH_AUTH_SOCK",
    "SOME_CREDENTIAL", "IPC_KEY", "IPC_TOKEN",
    # the one documented exemption (U265) — a scrubber that removes the sandbox is not a safety feature
    "GROK_SANDBOX",
    # mixed / lower case: the same variable to Windows
    "node_path", "Node_Options", "xai_api_key", "My_Session_Token", "grok_sandbox",
    # benign names that must survive
    "PATH", "KEEP_ME", "USERPROFILE", "HOME", "TEMP", "TMP", "LANG", "HTTP_PROXY", "HTTPS_PROXY",
    "SOVEREIGN_CONTROL_PORT", "SOVEREIGN_STORE_ROOT", "COMPUTERNAME",
)


def _js_verdicts(names: tuple[str, ...]) -> dict[str, bool]:
    """Classify every name through the JavaScript port, in one node process."""
    node = shutil.which("node")
    if node is None:                                                    # pragma: no cover
        pytest.skip("node is not on PATH; the JS half of the parity pin cannot be exercised")
    script = (
        "const {isCredentialEnvName} = require(process.argv[1]);"
        "const names = JSON.parse(process.argv[2]);"
        "const out = {};"
        "for (const n of names) out[n] = isCredentialEnvName(n) === true;"
        "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run(
        [node, "-e", script, str(LAUNCH_SOURCE), json.dumps(list(names))],
        cwd=str(ROOT), capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"node failed: {proc.stderr.strip()}"
    return json.loads(proc.stdout)


def test_the_two_classifiers_agree_over_the_pinned_vector() -> None:
    """ACCEPTANCE 5. Identical verdicts, name by name — the disagreements are NAMED, not counted."""
    js = _js_verdicts(PARITY_VECTOR)
    assert set(js) == set(PARITY_VECTOR), "the JS half did not classify every name in the vector"

    disagreements = [
        (name, is_provider_credential_env_key(name), js[name])
        for name in PARITY_VECTOR
        if is_provider_credential_env_key(name) != js[name]
    ]
    assert not disagreements, (
        "the Python authority and the JavaScript port disagree on "
        f"{len(disagreements)} name(s) — (name, python, js): {disagreements}"
    )


def test_node_path_is_classified_by_both() -> None:
    """W-32's own addition, asserted directly so a green parity run cannot hide a shared blind spot.

    Parity alone is satisfied by BOTH classifiers being wrong together. This is the one name this
    unit adds, so it is checked against the requirement rather than against the other side.
    """
    assert is_provider_credential_env_key("NODE_PATH") is True
    assert _js_verdicts(("NODE_PATH", "node_path"))["NODE_PATH"] is True
    assert _js_verdicts(("node_path",))["node_path"] is True


def test_the_vector_actually_exercises_both_verdicts() -> None:
    """A vector of all-positives or all-negatives would pass parity while testing almost nothing."""
    verdicts = [is_provider_credential_env_key(n) for n in PARITY_VECTOR]
    assert verdicts.count(True) >= 20, "too few positive cases to be evidence"
    assert verdicts.count(False) >= 10, "too few negative cases — a classifier that says True to "
    "everything would pass"
