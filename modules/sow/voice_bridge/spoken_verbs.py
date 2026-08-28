"""Shared spoken-verb normalization for the voice input surfaces (Plan §2.4, §9.9).

BOTH voice surfaces map spoken words to canonical command verbs through the SAME table. When the
caller supplies the gated set, a protected/destructive verb anywhere in the utterance wins over polite
leading words, so "please delete" cannot evade the broker:

  * the Phase-12 shell-control `VoiceAdapter` (voice as a control-command bus), and
  * the Phase-15E `ConductorVoiceBridge` (voice into the CONDUCTOR conversation).

The table only ever maps toward the canonical control verbs the `CommandBroker` classifies; it never
invents a verb and never maps toward a LESS restrictive one (escalation table, F-voice). Pure,
deterministic, no I/O — never model output.
"""
from __future__ import annotations

import re

#: spoken form -> canonical control verb. Escalation-only: each entry maps toward a verb the broker
#: classifies protected/destructive (or an equally-restrictive one), never toward a safe verb.
VOICE_VERB_SYNONYMS = {
    "stop": "terminate", "shut": "shutdown", "make": "spawn", "create": "spawn", "start": "spawn",
    "give": "grant", "allow": "grant",
    "erase": "delete", "destroy": "delete", "wipe": "purge",
    "deletes": "delete", "deleted": "delete", "deleting": "delete",
    "removes": "remove", "removed": "remove", "removing": "remove",
    "kills": "kill", "killed": "kill", "killing": "kill",
    "terminates": "terminate", "terminated": "terminate", "terminating": "terminate",
    "merges": "merge", "merged": "merge", "merging": "merge",
    "purges": "purge", "purged": "purge", "purging": "purge",
    "spawns": "spawn", "spawned": "spawn", "spawning": "spawn",
    "grants": "grant", "granted": "grant", "granting": "grant",
    "approves": "approve", "approved": "approve", "approving": "approve",
    "promotes": "promote", "promoted": "promote", "promoting": "promote",
    "elevates": "elevate", "elevated": "elevate", "elevating": "elevate",
    "authorizes": "authorize", "authorized": "authorize", "authorizing": "authorize",
    "authorise": "authorize", "authorises": "authorize", "authorised": "authorize",
    "authorising": "authorize",
}


def normalize_spoken_verb(word: str) -> str:
    """Canonicalize a single spoken verb (lowercased) through the synonym table."""
    w = word.strip().lower() if isinstance(word, str) else ""
    return VOICE_VERB_SYNONYMS.get(w, w)


def split_spoken_command(text: str, gated_verbs: frozenset[str] = frozenset()) -> tuple[str, str]:
    """Split text into a normalized verb + target, preferring any gated verb in the utterance.

    Empty/blank text -> ('', ''). This is the ONE place spoken text becomes a (verb, target)
    candidate. Supplying ``gated_verbs`` makes protected/destructive detection conservative:
    false positives queue for operator review; a false negative could reach a tool-capable model.
    """
    words = re.findall(r"[A-Za-z0-9_-]+", text.lower()) if isinstance(text, str) else []
    if not words:
        return ("", "")
    normalized = [normalize_spoken_verb(word) for word in words]
    chosen = next((i for i, verb in enumerate(normalized) if verb in gated_verbs), 0)
    verb = normalized[chosen]
    target = " ".join(words[chosen + 1:]) if chosen + 1 < len(words) else ""
    return (verb, target)
