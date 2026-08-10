"""Command-line entry points for audit and governance operations."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Sequence

from .audit import audit_facts
from .domain import FactObservation
from .governance import (
    environment_manifest,
    freeze_entry_000,
    freeze_entry_001,
    require_entry_001,
    source_control_manifest,
    verify_artifact,
)
from .identification import rule17


def _load_facts_csv(path: str | Path) -> list[FactObservation]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [FactObservation.from_mapping(row) for row in csv.DictReader(handle)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="graham-research")
    commands = parser.add_subparsers(dest="command", required=True)

    audit = commands.add_parser("audit-facts", help="audit a PIT long-form fact CSV")
    audit.add_argument("input_csv")
    audit.add_argument("output_json")

    entry0 = commands.add_parser("freeze-entry-000", help="freeze Architecture v3.1")
    entry0.add_argument("architecture_text")
    entry0.add_argument("output_json")

    entry1 = commands.add_parser("freeze-entry-001", help="freeze complete experiment config")
    entry1.add_argument("config_json")
    entry1.add_argument("output_json")
    entry1.add_argument("--repository", required=True)

    verify = commands.add_parser("verify", help="verify a frozen artifact")
    verify.add_argument("artifact_json")

    check_entry = commands.add_parser(
        "check-entry-001",
        help="verify Entry 001 and report current runtime compatibility",
    )
    check_entry.add_argument("artifact_json")

    manifest = commands.add_parser("manifest", help="print an environment manifest")
    manifest.add_argument("--repository")

    rule = commands.add_parser("rule17", help="evaluate sign-aligned deltas")
    rule.add_argument("deltas", nargs="+", type=float)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit-facts":
        report = audit_facts(_load_facts_csv(args.input_csv))
        report.write_json(args.output_json)
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.command == "freeze-entry-000":
        text = Path(args.architecture_text).read_text(encoding="utf-8")
        print(freeze_entry_000(args.output_json, text))
    elif args.command == "freeze-entry-001":
        payload = json.loads(Path(args.config_json).read_text(encoding="utf-8"))
        print(freeze_entry_001(args.output_json, payload, repository=args.repository))
    elif args.command == "verify":
        print(verify_artifact(args.artifact_json))
    elif args.command == "check-entry-001":
        payload, runtime = require_entry_001(args.artifact_json)
        result = {
            "entry": payload["entry"],
            "sha256": verify_artifact(args.artifact_json),
            "runtime_validation": runtime.to_dict(),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        for message in runtime.warnings:
            print(f"WARNING: {message}", file=sys.stderr)
    elif args.command == "manifest":
        output: dict[str, object] = {
            "environment_manifest": environment_manifest(),
        }
        if args.repository:
            output["source_control"] = source_control_manifest(args.repository)
        print(json.dumps(output, indent=2, sort_keys=True))
    elif args.command == "rule17":
        print(json.dumps(asdict(rule17(args.deltas)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
