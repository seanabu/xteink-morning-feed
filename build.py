#!/usr/bin/env python3
"""Entry point: python build.py --profile <name> [--check | --daily]."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from feed.config import ProfileError, load_profile

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", required=True, help="profile folder name under profiles/")
    p.add_argument("--profiles-dir", default=str(ROOT / "profiles"))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="validate config and test every feed")
    mode.add_argument("--daily", action="store_true", help="build today's issue and catalog")
    p.add_argument("--out", default=str(ROOT / "site"), help="output folder for the static site")
    p.add_argument("--state", default=str(ROOT / "state"),
                   help="state folder (dedupe, inbox, reading history); the state branch in CI")
    p.add_argument("--base-url", default=os.environ.get("SITE_URL"),
                   help="public URL of the site root (catalog links must be absolute for CrossPoint)")
    p.add_argument("--if-missing", action="store_true",
                   help="skip a profile that already has today's issue (used by the schedule)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    try:
        profile = load_profile(Path(args.profiles_dir) / args.profile)
    except ProfileError as e:
        print(f"Profile error:\n{e}", file=sys.stderr)
        return 1

    if args.check:
        from feed.check import run_check
        failures = run_check(profile)
        return 0 if failures == 0 else 2

    if args.daily:
        from feed.daily import build_daily
        return build_daily(profile, out_dir=Path(args.out), state_dir=Path(args.state),
                           base_url=args.base_url, force=not args.if_missing)

    p.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
