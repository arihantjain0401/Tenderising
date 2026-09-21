"""CLI entrypoint for the collection schedules (T0-T4).

Every scrape command is serialized through an exclusive file lock so two jobs
(scheduled or manual) never write the curated DB at the same time: a later run
waits for the earlier one to finish, then proceeds.
"""

from __future__ import annotations

import argparse
import fcntl
import json

from tenderising.config import DATA_DIR
from tenderising.schedule import tiers

_LOCK_FILE = DATA_DIR / "scrape.lock"


def _acquire_lock():
    """Take an exclusive lock, waiting for any in-progress scrape run."""
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    f = _LOCK_FILE.open("w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another scrape run is in progress — waiting for it to finish…", flush=True)
        fcntl.flock(f, fcntl.LOCK_EX)
    return f


def _print_summary(result: dict) -> None:
    print(json.dumps(result, indent=2, default=str))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tenderising", description="GeM collection schedules")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("on-demand", help="T0: fetch one bid by public number")
    p.add_argument("bid_number")

    p = sub.add_parser("hot-set", help="T1: re-poll top-N bids by change-probability")
    p.add_argument("--top", type=int, default=50)

    p = sub.add_parser("delta", help="T2: broad active delta (convergence crawl)")
    p.add_argument("--max-pages", type=int, default=None)

    p = sub.add_parser("baseline", help="T3: nightly full convergence crawl")
    p.add_argument("--max-pages", type=int, default=None)

    p = sub.add_parser("weekly", help="T4: weekly full enumeration")
    p.add_argument("--max-pages", type=int, default=None)

    p = sub.add_parser("awards", help="Collect recently-awarded bids via the Awarded facet")
    p.add_argument("--max-pages", type=int, default=None)

    args = parser.parse_args(argv)

    lock = _acquire_lock()
    try:
        if args.command == "on-demand":
            _print_summary(tiers.t0_on_demand(args.bid_number))
        elif args.command == "hot-set":
            _print_summary(tiers.t1_hot_set(args.top))
        elif args.command == "delta":
            _print_summary(tiers.t2_broad_delta(args.max_pages))
        elif args.command == "baseline":
            _print_summary(tiers.t3_baseline(args.max_pages))
        elif args.command == "weekly":
            _print_summary(tiers.t4_weekly(args.max_pages))
        elif args.command == "awards":
            _print_summary(tiers.t_award_delta(args.max_pages))
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    main()
