"""draft-data CLI: refresh / validate / query."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="draft-data")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_refresh = sub.add_parser("refresh", help="fetch + parse sources, rebuild outputs")
    p_refresh.add_argument("--source", help="refresh a single source")
    p_refresh.add_argument("--force", action="store_true", help="ignore raw-cache freshness")
    p_refresh.add_argument("--no-build", action="store_true", help="fetch only, skip normalize")

    sub.add_parser("validate", help="schema, null, and sanity checks on processed outputs")

    p_query = sub.add_parser("query", help="run DuckDB SQL against processed outputs")
    p_query.add_argument("sql")

    args = parser.parse_args()

    if args.cmd == "refresh":
        from draft_data.cli.refresh import run_refresh

        return run_refresh(source=args.source, force=args.force, build=not args.no_build)
    if args.cmd == "validate":
        from draft_data.cli.validate import run_validate

        return run_validate()
    if args.cmd == "query":
        from draft_data.cli.query import run_query

        return run_query(args.sql)
    return 2


if __name__ == "__main__":
    sys.exit(main())
