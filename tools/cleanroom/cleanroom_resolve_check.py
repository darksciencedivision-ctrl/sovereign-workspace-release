"""
Clean-room adapter RESOLUTION check (SWS-PUNCHLIST-DIRECTIVE-20260921 WS-0.2).

Runs the shell's OWN adapter loader against an extracted distribution and asserts, per module,
that what the shell would actually launch resolves to real paths INSIDE that distribution. This
is the gate that would have caught WS-0.1 (root pointing at a build-host tree), WS-0.3 (a `-m`
entry module that is absent from the shipped tree), and any future path/config regression of that
class.

It does this by importing the EXTRACTED copy's `shell.src.adapter`, so `install_root()` — which
that module derives from its own file location — resolves to the clean-room directory, exactly as
it would when the shell runs there. Nothing is reimplemented; the containment/config validation is
the shell's, and this script adds the existence checks that `compile_adapter` deliberately does not
perform (a resolved path string is validated, but the file it names is not opened at compile time).

Usage:
    py -3.12 cleanroom_resolve_check.py --dist "<extracted dist root>" [--json <out.json>]
    py -3.12 cleanroom_resolve_check.py --selftest      # prove the checker FAILS on a bad entry

Exit code: 0 when no module is FAIL; 1 otherwise. PROVISION-PENDING is not a failure — it means the
resolved path is correct but a build/venv/binary artifact is not present in a source-only tree.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Build-host / developer-tree markers that must never appear in a resolved, shipped launch path.
# Their presence means an absolute build-host location leaked into config (the WS-0.1 / WS-0.4 class).
BUILD_HOST_MARKERS = (
    "Sov 1",
    "SOVEREIGN_PRODUCT_COMPLETION_WORK",
    "Product Software",
    "SOVEREIGN_SYSTEM",
    "Production Workspace",
)


def _load_adapter_module(dist: str):
    """Import the EXTRACTED distribution's shell.src.adapter so install_root() == dist."""
    dist = os.path.abspath(dist)
    if not os.path.isfile(os.path.join(dist, "shell", "src", "adapter.py")):
        raise SystemExit(f"FATAL: {dist} does not look like a distribution (no shell/src/adapter.py)")
    # Purge any previously-imported shell.* so the dist copy is the one that binds.
    for name in [m for m in sys.modules if m == "shell" or m.startswith("shell.")]:
        del sys.modules[name]
    sys.path.insert(0, dist)
    from shell.src import adapter  # noqa: E402  (import after sys.path injection is the point)
    if os.path.abspath(adapter.install_root()) != dist:
        raise SystemExit(
            f"FATAL: install_root() resolved to {adapter.install_root()!r}, expected {dist!r}")
    return adapter


def _module_entry(root: str, argv: list[str], cwd: str) -> tuple[str, str]:
    """Return (kind, path) for the code entry point the interpreter will run.

    kind is 'module' (python -m pkg.mod), 'script' (a .py/.js file argument), or 'dir' (e.g. an
    Electron app root passed as '.'). A relative script argument is resolved against the module's
    launch cwd — that is where the process actually runs, so `python app.py` means `<cwd>/app.py`.
    """
    if "-m" in argv:
        mod = argv[argv.index("-m") + 1]
        return "module", os.path.join(root, *mod.split("."))
    for arg in argv[1:]:
        low = arg.lower()
        if low.endswith((".py", ".js", ".mjs", ".cjs")):
            path = arg if os.path.isabs(arg) else os.path.normpath(os.path.join(cwd, arg))
            return "script", path
    return "dir", root  # interpreter (e.g. electron.exe) launched against its cwd/root


def _entry_exists(kind: str, path: str) -> bool:
    if kind == "module":
        return os.path.isfile(path + ".py") or os.path.isfile(os.path.join(path, "__init__.py"))
    if kind == "script":
        return os.path.isfile(path)
    return os.path.isdir(path)  # 'dir'


def _is_provisioning_path(interp: str) -> bool:
    """True when the interpreter is a per-module venv / node_modules artifact — absent in a
    source-only tree, present after provisioning. Its ABSENCE is PROVISION-PENDING, not a defect."""
    low = interp.replace("\\", "/").lower()
    return "/.venv/" in low or "/node_modules/" in low


def check_dist(dist: str) -> dict:
    adapter = _load_adapter_module(dist)
    dist = os.path.abspath(dist)
    adapters = adapter.load_all_adapters()
    results = []
    for mid, a in sorted(adapters.items()):
        r = {"module": mid, "status": None, "detail": "", "entry": "", "interpreter": ""}

        if a.get("error"):
            r["status"] = "FAIL"
            r["detail"] = f"{a.get('error')}: {a.get('reason', '')}".strip()
            results.append(r)
            continue

        if a.get("state_class") != "runnable":
            r["status"] = "INFO"
            r["detail"] = f"state_class={a.get('state_class')!r} (not a launched service)"
            results.append(r)
            continue

        launch = a["launch"]
        argv = launch["argv"]
        root = a["root"]
        interp = argv[0]
        kind, entry = _module_entry(root, argv, launch.get("cwd", root))
        r["entry"] = f"{kind}:{entry}"
        r["interpreter"] = interp

        # Build-host marker scan over everything the shell resolved for this module.
        blob = json.dumps([root, launch.get("cwd"), argv, launch.get("env_set", {})])
        leaked = [m for m in BUILD_HOST_MARKERS if m in blob]

        # Containment sanity: load_all_adapters already enforced root/cwd containment (an escape
        # becomes a CONFIG_ERROR handled above), but assert the entry itself is under root too.
        entry_probe = entry if kind != "module" else entry + ".py"
        entry_contained = adapter.is_contained(root, entry_probe) or entry.startswith(root)

        if not _entry_exists(kind, entry):
            r["status"] = "FAIL"
            r["detail"] = f"launch entry does not exist in the distribution ({kind}: {entry})"
        elif leaked:
            r["status"] = "FAIL"
            r["detail"] = f"build-host path leaked into resolved launch config: {leaked}"
        elif not entry_contained:
            r["status"] = "FAIL"
            r["detail"] = f"launch entry escapes module root: {entry}"
        elif _is_provisioning_path(interp) and not os.path.isfile(interp):
            r["status"] = "PROVISION-PENDING"
            r["detail"] = f"resolved interpreter path is correct but not yet provisioned: {interp}"
        else:
            r["status"] = "PASS"
            note = "" if os.path.exists(interp) else " (shared interpreter; module deps not checked)"
            r["detail"] = f"entry present, root contained, no build-host paths{note}"
        results.append(r)

    fails = [x for x in results if x["status"] == "FAIL"]
    return {
        "dist": dist,
        "install_root": adapter.install_root(),
        "modules": results,
        "summary": {
            "total": len(results),
            "pass": sum(x["status"] == "PASS" for x in results),
            "provision_pending": sum(x["status"] == "PROVISION-PENDING" for x in results),
            "info": sum(x["status"] == "INFO" for x in results),
            "fail": len(fails),
        },
        "ok": not fails,
    }


def _print_report(report: dict) -> None:
    print(f"\nClean-room resolution check — dist: {report['dist']}")
    print(f"install_root(): {report['install_root']}")
    print("-" * 78)
    width = max((len(m["module"]) for m in report["modules"]), default=8)
    for m in report["modules"]:
        print(f"  {m['status']:<17} {m['module']:<{width}}  {m['detail']}")
    s = report["summary"]
    print("-" * 78)
    print(f"  total={s['total']}  PASS={s['pass']}  PROVISION-PENDING={s['provision_pending']}  "
          f"INFO={s['info']}  FAIL={s['fail']}")
    print(f"  RESULT: {'PASS' if report['ok'] else 'FAIL'}\n")


def _selftest() -> int:
    """Prove the checker's core logic FAILS on a missing `-m` entry and PASSES on a present one."""
    here = os.path.dirname(os.path.abspath(__file__))
    # present: this very package (tools/cleanroom has no __init__, so use a known file)
    # cwd is irrelevant for a `-m module` entry (it resolves under root); pass `here`.
    ok_kind, ok_path = _module_entry(here, ["python.exe", "-m", "cleanroom_resolve_check"], here)
    present = _entry_exists(ok_kind, ok_path)
    bad_kind, bad_path = _module_entry(here, ["python.exe", "-m", "does_not_exist_pkg.nope"], here)
    missing = _entry_exists(bad_kind, bad_path)
    print(f"selftest: present-entry detected present = {present} (expect True)")
    print(f"selftest: missing-entry detected present = {missing} (expect False)")
    ok = present and not missing
    print(f"selftest: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Clean-room adapter resolution check (WS-0.2)")
    ap.add_argument("--dist", help="Extracted distribution root to check")
    ap.add_argument("--json", help="Write the full JSON report here")
    ap.add_argument("--selftest", action="store_true", help="Prove the checker catches a bad entry")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.dist:
        ap.error("--dist is required (or use --selftest)")

    report = check_dist(args.dist)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    _print_report(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
