import argparse
import json

from . import __version__
from .core import MAX_BYTES, PlaylistError, plan_relocation, write_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview relocation of a local M3U playlist.")
    parser.add_argument("playlist")
    parser.add_argument("--map", required=True, dest="mapping_file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--write", action="store_true", help="Create a new output only when ready")
    parser.add_argument("--absolute", action="store_true", help="Emit absolute native target paths")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-findings", type=int, default=50)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--max-entries", type=int, default=100_000)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        plan = plan_relocation(
            args.playlist,
            args.mapping_file,
            args.output,
            absolute=args.absolute,
            max_findings=args.max_findings,
            max_bytes=args.max_bytes,
            max_entries=args.max_entries,
        )
        receipt = write_plan(plan) if args.write and plan.content is not None else plan.report
    except PlaylistError as exc:
        receipt = {
            "schema_version": 1,
            "status": "error",
            "error": {"side": exc.side, "code": exc.code},
        }
    if args.json:
        print(json.dumps(receipt, ensure_ascii=True, indent=2))
    elif receipt["status"] == "error":
        print(f"ERROR {receipt['error']['side']}: {receipt['error']['code']}")
    else:
        print(
            f"{receipt['status'].upper()}: {receipt['resolved']}/{receipt['entries']} "
            f"entries resolved, {receipt['issue_count']} issue(s)"
        )
        for finding in receipt["findings"]:
            print(f"  line {finding['line']}: {finding['code']}")
    return 2 if receipt["status"] == "error" else int(receipt["status"] == "blocked")
