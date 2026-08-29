# Release Gate Policy

Release verdicts bind to a clean archive of the exact release commit.
Run `git archive HEAD`, extract it to an empty temporary directory, and run the package boundary gate there.
Archive results are authoritative because ignored host state is absent by construction.
Live-tree scans are operational-hygiene checks and may report ignored caches or dependencies.
Keep `node_modules` for the offline desktop suite; it is ignored and never enters `git archive`.
Before packaging, remove test caches, bytecode, and test-created databases outside quarantined evidence lanes.
Record both archive and live-tree measurements; never substitute one for the other.

## Release identity and the seal commit

`VERSION.json` is a tracked file, so its bytes are part of the tree that its own commit hash is
taken over. It therefore cannot contain the hash of the commit that introduces it: writing the
hash changes the tree, which changes the commit, which invalidates the hash just written. A fixed
point would require a deliberate SHA-1 preimage, so no ordering, no retry and no "manifests last"
discipline can produce one. An earlier directive asked for exactly that and was unsatisfiable; the
builder of the day was right to park it rather than fabricate a value.

The convention, so that the two identity documents cannot silently disagree again:

* `VERSION.json.source_commit` is the **last product/tooling commit** — by definition, never the
  seal. `source_commit_definition` states this inside the file itself.
* `VERSION.json.seal_commit_record` names the file that does hold the seal commit,
  `release-artifacts/release-build-manifest.json`.
* That build manifest is **untracked**, which is what lets it name the seal commit and carry every
  release-artifact and sidecar hash. It is written after the seal commit exists, and it excludes
  itself for the same self-reference reason.
* `RELEASE-MANIFEST.json` covers **tracked bytes only** and carries no release-artifact hash at
  all; it names the authority above by reference in `release_archive_hash_authority`. Adding a
  hash-bearing section that `release_manifest_check.py` does not verify makes the gate fail by
  construction.

The general rule: a hash belongs in a file that is not itself an input to the thing being hashed.
Artifacts are cut **after** the seal commit, never before it.
