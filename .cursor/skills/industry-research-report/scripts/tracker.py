#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict


def run_report(script_path: Path, query: str, mode: str) -> Dict:
    cmd = [
        sys.executable,
        str(script_path),
        "--query",
        query,
        "--mode",
        mode,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "report generation failed")
    try:
        return json.loads(proc.stdout.strip())
    except Exception as exc:
        raise RuntimeError(f"invalid json output: {exc}") from exc


def should_run_weekly(weekday: int, expected_weekday: int) -> bool:
    return weekday == expected_weekday


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily/weekly tracker entry for AI industry reports.")
    parser.add_argument("--query", default="AI产业", help="Tracking topic")
    parser.add_argument(
        "--mode",
        default="daily",
        choices=["daily", "weekly", "both"],
        help="Tracker mode",
    )
    parser.add_argument(
        "--weekly-day",
        type=int,
        default=1,
        help="ISO weekday for weekly run: 1=Mon ... 7=Sun",
    )
    parser.add_argument(
        "--history-path",
        default="",
        help="Optional jsonl history output path",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    report_script = here / "get_data.py"
    now = dt.datetime.now()
    iso_weekday = now.isoweekday()

    outputs = []
    try:
        if args.mode in {"daily", "both"}:
            outputs.append(run_report(report_script, args.query, "daily"))
        if args.mode in {"weekly", "both"} and should_run_weekly(iso_weekday, args.weekly_day):
            outputs.append(run_report(report_script, args.query, "weekly"))

        result = {
            "timestamp": now.isoformat(),
            "query": args.query,
            "mode": args.mode,
            "count": len(outputs),
            "reports": outputs,
        }

        if args.history_path:
            history_path = Path(args.history_path)
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with history_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")

        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
