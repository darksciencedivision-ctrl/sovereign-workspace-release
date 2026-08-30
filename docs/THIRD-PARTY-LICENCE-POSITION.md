# Third-party licence position

**Scope.** The 240 third-party library components listed in `NOTICE`.
**Generated basis.** `SBOM.json` is produced from the six lock files by
`tools/release/generate_sbom.py`, and `NOTICE` from the SBOM by
`tools/release/generate_notice.py`; this document records the *positions* neither file can
express. **Status: pending counsel sign-off**, in step with `LICENSE`.

---

## What the audit found

**The SBOM has since been regenerated from lock files (P2-1/P2-2/P2-3), and the numbers here
are from that version.** 240 components, every one carrying a licence declaration, zero
unresolved. The scope of each — `required` for what the product installs, `optional` for
build- and test-time — comes from the locks themselves rather than from anyone's assertion.

Two corrections to earlier revisions of this document are recorded rather than quietly
edited:

- The figure of "173 components without a licence" was a miscount. All 173 were `file`-type
  entries — individual files from the build machine's virtual environments, not packages —
  and carried no licence because a file is not a licensable component. They are gone.
- The old SBOM listed **62 packages the product does not contain**. Measured: they are absent
  from every lock file *and* absent from `node_modules` on disk. They were transitive
  dependencies of `@electron/get@2.0.3`, which the lock replaced with `5.1.0` — the old SBOM
  carried both versions and the stale one's dependency tree. For a vulnerability scanner that
  is worse than a gap: it produces findings against software that is not there.

Ten components declared `UNKNOWN`. None were guessed. Each was resolved by reading the
installed distribution's own metadata, and the NOTICE records which field it came from:

| Component | Resolved | Read from |
|---|---|---|
| annotated-types 0.7.0 | MIT | Trove classifier |
| blinker 1.9.0 | MIT | Trove classifier |
| chromadb 1.5.9 | Apache-2.0 | Trove classifier |
| colorama 0.4.6 | BSD-3-Clause | Trove classifier |
| itsdangerous 2.2.0 | BSD-3-Clause | Trove classifier |
| jinja2 3.1.6 | BSD-3-Clause | Trove classifier |
| markdown-it-py 4.2.0 | MIT | Trove classifier |
| mdurl 0.1.2 | MIT | Trove classifier |
| pyproject-hooks 1.2.0 | MIT | Trove classifier |
| tokenizers 0.23.1 | Apache-2.0 | Trove classifier |

One further component, `python-dateutil 2.9.0.post0`, declared the unhelpful string
`Dual License`. Its classifiers name both options, so the NOTICE records
`BSD-3-Clause OR Apache-2.0` rather than repeating the vague field.

**Unresolved components: none.** The generator exits non-zero if any remain, so an
incomplete NOTICE fails the build instead of shipping quietly.

---

## MPL-2.0 — the position

Sixteen components are under, or partly under, the Mozilla Public License 2.0.

| Component | Version | Declared |
|---|---|---|
| `lightningcss` and its 11 platform binaries | 1.33.0 | MPL-2.0 |
| `certifi` | 2026.6.17, 2026.7.22 | MPL-2.0 |
| `orjson` | 3.12.0 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| `tqdm` | 4.70.0 | MPL-2.0 AND MIT |

**MPL-2.0 is file-level copyleft, not project-level.** Its obligations attach to the
individual files that carry the licence, and to modifications of those files. It does not
reach across a boundary into separately-licensed code that merely links to or invokes the
covered work — §1.5 and §3.3 make that explicit, and the licence is designed to permit
combination with proprietary software in exactly this way.

**Position taken.** All sixteen components are used **unmodified**, as published by their
upstream projects. No file carrying MPL-2.0 has been altered, patched, vendored with
changes, or forked. Three consequences follow:

1. **No source-disclosure obligation is triggered for this workspace's own code.** The
   proprietary licence in `LICENSE` applies to the Sovereign Workspace source and is not
   affected by the presence of these components.
2. **The obligation that does apply is attribution plus source availability for the
   covered files themselves.** It is discharged by `NOTICE`, which names every component
   and its licence, and by the fact that each component's unmodified source remains
   publicly available from its upstream project at the exact version pinned.
3. **If any MPL-2.0 file is ever modified, this position lapses.** The modified files
   would then have to be made available under MPL-2.0. Any change to a vendored copy of
   these components must return to this document first.

`lightningcss` and its eleven platform binaries are additionally **build-time only**, and that
is now a fact carried by the SBOM rather than a claim in this document: all twelve are scoped
`optional`, derived from the `dev` flag in `package-lock.json`. They are reached through the
Vite toolchain and are not part of the running product. `certifi`, `orjson` and `tqdm` are
scoped `required`.

That narrows the exposure further but is not the basis of the position above — the
unmodified-use argument stands on its own for all sixteen.

---

## Exceptions register

No component is exempted from attribution. Two presentational normalisations are recorded
here so that the NOTICE cannot be accused of restating a licence it was not given:

- **Spelling normalisation.** The SBOM carried four distinct spellings of Apache-2.0
  (`Apache 2.0`, `Apache License 2.0`, `Apache License Version 2.0`,
  `Apache License, Version 2.0`) and several of MIT and BSD. The NOTICE maps these onto
  single SPDX identifiers. This is presentation only; the mapping table lives in
  `tools/release/generate_notice.py` and is auditable.
- **Licence text as identifier.** One SBOM entry carried an entire MIT licence body in the
  field reserved for a licence *identifier*. The generator reduces it to `MIT` rather than
  reprinting the body inside a summary table. The component's own metadata is unchanged and
  remains the authority.

---

## Obligations this document does not discharge

Stated so the absence is not read as completion:

- **Counsel has not reviewed `LICENSE`, this document, or the NOTICE.** Nothing here is
  legal advice, and the analysis above is an engineering reading of licence text.
- **Governing law and jurisdiction are unfixed** in `LICENSE` §9 pending that review.
- **The SBOM is now generated from lock files** (P2-1/P2-2/P2-3) by
  `tools/release/generate_sbom.py`, which records each lock's path and SHA-256 so its
  provenance is checkable rather than asserted. `--check` on either generator fails the build
  if the SBOM or the NOTICE drifts from its sources.
