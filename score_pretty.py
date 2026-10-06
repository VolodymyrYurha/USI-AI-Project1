"""Pretty output for your scorer: uses score() from score.py, prints "84/150 (56.0%)" with the numbers in color.

python score_pretty.py runs/single-1
"""

from __future__ import annotations

import argparse
import re
import sys

from score import score

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"


def color_numbers(text: str, color: str) -> str:
    """Wrap every number in `text` in the given color."""
    return re.sub(r"\d+(?:\.\d+)?", lambda m: f"{color}{m.group()}{RESET}", text)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Score a run, with a percentage and colored numbers."
    )
    ap.add_argument("run_dir", help="a run folder, e.g. runs/single-1")
    ap.add_argument(
        "--answers",
        default="data/public_answers.jsonl",
        help="the right answers (default: %(default)s)",
    )
    args = ap.parse_args()

    right, total, wrong = score(args.run_dir, args.answers)
    pct = 100 * right / total if total else 0.0
    use_color = sys.stdout.isatty()

    summary = f"{right}/{total} ({pct:.1f}%) right"
    if not use_color:
        print(summary)
        for request_id in wrong:
            print(request_id)
        return

    if wrong:
        print(f"{RED}{len(wrong)} wrong:{RESET}")
    for request_id in wrong:
        print(color_numbers(request_id, RED))

    pct_color = GREEN if pct >= 80 else YELLOW if pct >= 50 else RED
    print(
        f"{BOLD}{pct_color}{right}{RESET}{BOLD}/{CYAN}{total}{RESET} "
        f"{BOLD}({pct_color}{pct:.1f}%{RESET}{BOLD}){RESET} right"
    )


if __name__ == "__main__":
    main()
