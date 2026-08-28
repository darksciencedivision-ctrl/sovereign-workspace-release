from __future__ import annotations

import argparse
import json
from pathlib import Path

from distillery.common import utc_now
from distillery.identity import resolve_identity
from exclusion import e7_acceptance
from grounded.g0_live import run_live_acceptance
from grounded.harness_adapters import import_turn_record
from grounded.telemetry import TraceStore, run_g0_probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="grounded")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version")
    acceptance = commands.add_parser("acceptance")
    acceptance.add_argument("--output", type=Path, required=True)
    live = commands.add_parser("import-sovereign-turn")
    live.add_argument("--input", type=Path, required=True)
    live.add_argument("--event-log", type=Path, required=True)
    live.add_argument("--summary", type=Path, required=True)
    g0 = commands.add_parser("live-g0-acceptance")
    g0.add_argument("--success-turn", type=Path, action="append", required=True)
    g0.add_argument("--failure-result", type=Path, required=True)
    g0.add_argument("--recovery-failure-result", type=Path, required=True)
    g0.add_argument("--recovery-success-result", type=Path, required=True)
    g0.add_argument("--no-trace-source-id", required=True)
    g0.add_argument("--checksum-spec", type=Path, required=True)
    g0.add_argument("--component", action="append", required=True, help="component_id=absolute_path")
    g0.add_argument("--event-log", type=Path, required=True)
    g0.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "version":
        identity = resolve_identity()
        print(json.dumps(identity, indent=2, sort_keys=True))
        return 0
    if args.command == "acceptance":
        result = {"g0": run_g0_probes(), "e7": e7_acceptance()}
        result["passed"] = result["g0"]["passed"] and result["e7"]["passed"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return 0 if result["passed"] else 1
    if args.command == "live-g0-acceptance":
        specification = json.loads(args.checksum_spec.read_text(encoding="utf-8"))
        component_paths = {}
        for assignment in args.component:
            component, separator, path = assignment.partition("=")
            if not separator or not component or not path:
                parser.error("--component must be component_id=absolute_path")
            component_paths[component] = Path(path)
        result = run_live_acceptance(
            success_turn_paths=args.success_turn,
            failure_result_path=args.failure_result,
            recovery_failure_result_path=args.recovery_failure_result,
            recovery_success_result_path=args.recovery_success_result,
            no_trace_source_id=args.no_trace_source_id,
            store=TraceStore(args.event_log),
            expected_checksums=specification["components"],
            component_paths=component_paths,
        )
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    store = TraceStore(args.event_log)
    imported = import_turn_record(args.input, store)
    summary = {
        "status": "STARTED_PARTIAL",
        "captured_at": utc_now(),
        "adapter": "sovereign_product.semantic_deep",
        "mode": "active-runtime-immutable-evidence-import",
        "imported": imported,
        "aggregate": store.summary(),
        "event_log": str(args.event_log),
        "source_admission": "UNKNOWN",
        "telemetry_blocked_by_admission": False,
        "private_content_copied": False,
        "limitations": [
            "Imported real pre-existing runtime turn evidence; no newly generated session was initiated.",
            "Live recovery, implicit-signal, dashboard, alert, and alarm paths remain unverified.",
            "Source classifications remain fail-closed pending primary evidence and operator authority.",
        ],
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
