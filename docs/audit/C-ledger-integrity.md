# Audit C — ledger integrity

I deep-compared whole JSON objects for gates 0 through 7b, not selected fields.

Command: Python 3.12 `json.load` on the live ledger, `evidence/cpm1/ledger-snapshot-verified.json`, `evidence/loop5/ledger-snap-pre6.json`, and `evidence/theme01/ledger-snap-pre7.json`, followed by `current[key] == snapshot[key]` and witness membership/equality. Output:

```text
key  current==snapshot  pre6 contains/equal  pre7 contains/equal
0    TRUE               TRUE/TRUE            TRUE/TRUE
1    TRUE               TRUE/TRUE            TRUE/TRUE
2    TRUE               TRUE/TRUE            TRUE/TRUE
3    TRUE               TRUE/TRUE            TRUE/TRUE
4    TRUE               TRUE/TRUE            TRUE/TRUE
4b   TRUE               TRUE/TRUE            TRUE/TRUE
4c   TRUE               TRUE/TRUE            TRUE/TRUE
5    TRUE               TRUE/TRUE            TRUE/TRUE
5b   TRUE               TRUE/TRUE            TRUE/TRUE
6    TRUE               TRUE/FALSE           TRUE/TRUE
7a   TRUE               FALSE/-              FALSE/-
7b   TRUE               FALSE/-              FALSE/-
```

Gate 6 differs from the pre6 witness because that witness caught its pre-promotion placeholder. Exact changed fields are `authorized_by`, `basis`, `claimed_by`, `evaluated_by`, `evidence`, `note`, `status`, and `utc`; the pre7 witness contains the promoted object and matches it in full. This is expected witness chronology, not a current/snapshot mismatch.

Gates 7a and 7b appear in **neither witness**. The snapshot says so itself: `evidence/cpm1/ledger-snapshot-verified.json:5-20` lists corroborated keys only through 6; `:21-24` lists 7a/7b as self-attested. The objects begin at `:982` and `:1071`. Therefore “gates 0–7b byte-identical to the snapshot” is true, but the stronger implication “independently witnessed through 7b” is false.

I scanned every `evidence[].sha256` in the full live ledger with regex `^[0-9a-f]{64}$`: 379 hashes scanned, zero malformed. No 63-character value remains.

**Verdict:** whole-object snapshot fidelity is intact. Gates 0–6 are witness-corroborated with the stated pre6 chronology for gate 6; 7a/7b are only self-attested. This structural integrity does not repair the live evidence drift found in Audit B.
