"""phase-18c.close — pin the OP-12 acceptance verdict's JS constants to their Python authorities.

`apps/desktop/selfcheck/op12-acceptance-verdict.js` decides what the 18C in-Electron receipt is
allowed to CLAIM. Three of its constants are authoritatively owned in Python, and a stale JS mirror
would not fail loudly — it would produce a receipt that looks green while measuring the wrong thing:

  * ``OP12_PROVIDERS``          ← ``adapters.frontier.grok_build`` / ``.antigravity`` adapter ids
  * ``OP12_CREDENTIAL_NAMES``   ← ``adapters.frontier.provider_cli_common.PROVIDER_CREDENTIAL_ENV_KEYS``
    (a SUBSET, deliberately: the receipt plants a sentinel under each name it lists, and it lists the
    key-bearing ones. What may never happen is a name staying in the JS list after leaving the
    authority — the receipt would then plant a sentinel under a variable nothing scrubs and report a
    clean scan as evidence about a name the build no longer classifies.)
  * ``OP12_ALLOWANCE``          ← ``live_authorization.provider_terminal_cap`` (operator directive
    §12: allowance 1 each, never merged, never raised without a separate operator amendment)

The subscription REFS are not pinned here because they are not re-declared: the verdict module
imports ``ADAPTER_SUBSCRIPTION_REF`` from ``apps/desktop/picker/launch-source.js``, which
``test_statusbar_constants_pinned`` already ties to ``canonical_subscription_ref``. Asserted rather
than assumed — the import is checked below, so a future edit that re-types the strings locally is
caught by this test rather than by a lease written to a bucket nothing reads (the U76 defect).
"""
from __future__ import annotations

import re
from pathlib import Path

from adapters.frontier.antigravity import ANTIGRAVITY_ADAPTER
from adapters.frontier.grok_build import GROK_ADAPTER
from adapters.frontier.provider_cli_common import PROVIDER_CREDENTIAL_ENV_KEYS
from control_plane.profiles.live_authorization import provider_terminal_cap

_REPO = Path(__file__).resolve().parents[2]
_VERDICT_JS = _REPO / "apps" / "desktop" / "selfcheck" / "op12-acceptance-verdict.js"


def _js_source() -> str:
    return _VERDICT_JS.read_text(encoding="utf-8")


def _js_string_array(name: str) -> list[str]:
    m = re.search(rf"const {name} = Object\.freeze\(\[([^\]]*)\]\)", _js_source(), re.S)
    assert m is not None, f"{name} array not found in op12-acceptance-verdict.js"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_js_op12_providers_are_the_two_adapter_ids() -> None:
    assert _js_string_array("OP12_PROVIDERS") == [GROK_ADAPTER, ANTIGRAVITY_ADAPTER]


def test_js_credential_names_are_a_subset_of_the_scrubbed_authority() -> None:
    names = _js_string_array("OP12_CREDENTIAL_NAMES")
    assert names, "the acceptance receipt plants no sentinel at all"
    missing = [n for n in names if n not in PROVIDER_CREDENTIAL_ENV_KEYS]
    assert not missing, (
        f"{missing} are planted as credential sentinels by the 18C receipt but are no longer in "
        "adapters/frontier/provider_cli_common.PROVIDER_CREDENTIAL_ENV_KEYS — the receipt would "
        "report a clean scan for a name this build does not classify")


def test_js_op12_allowance_matches_the_operator_pinned_per_provider_cap() -> None:
    m = re.search(r"const OP12_ALLOWANCE = (\d+);", _js_source())
    assert m is not None, "OP12_ALLOWANCE literal not found in op12-acceptance-verdict.js"
    caps = {provider_terminal_cap(GROK_ADAPTER), provider_terminal_cap(ANTIGRAVITY_ADAPTER)}
    assert caps == {int(m.group(1))}, (
        f"the 18C receipt asserts an OP-12 ceiling of {m.group(1)} while live_authorization caps "
        f"them at {sorted(caps)} (operator directive §12)")


def test_the_subscription_refs_are_imported_not_retyped() -> None:
    src = _js_source()
    assert "require(\"../picker/launch-source\")" in src, (
        "the verdict module no longer imports the ticket contract's subscription-ref map")
    assert "ADAPTER_SUBSCRIPTION_REF" in src
    # …and the literals are NOT spelled out locally: a second copy is how a lease gets written to one
    # bucket and read from another (U76).
    assert '"grok_build_subscription"' not in src
    assert '"google_antigravity_subscription"' not in src
