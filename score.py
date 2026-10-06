"""Your scorer: how many of a run's requests did your system answer right?

Run it on a run folder, from this folder:

    python score.py runs/single-1

You see how many of the run's requests are right, then the id of each request that's wrong:

    6 of 10 right
    P003
    P007
    ...

Write score() below, and keep main() as it is. When we grade your scorer, we call your score() on test runs of
our own.

When an answer counts as right:
- `answers.jsonl` in the run folder has one line per request: {"id": ..., "pick": ..., "explanation": ...}, plus
  "error" if the system failed on that request.
- The answers file, `data/public_answers.jsonl` unless you give another one, has the right answer for each request:
  {"id": ..., "correct": [...]}, the letters of the acceptable games, or an empty list when the right answer is to
  decline.
- A pick is right if it's one of the listed letters. A decline ("pick": null) is right if the list is empty.
- A request with an "error" counts as wrong.
- Count every request in the run, so a run on 10 requests is scored out of 10.

To read a .jsonl file one dict per line, you can use `read_jsonl` from `p1.io`.
"""

from __future__ import annotations
import os
from p1.io import read_jsonl

import argparse


def score(
    run_dir: str, answers: str = "data/public_answers.jsonl"
) -> tuple[int, int, list[str]]:
    run_answers = list(read_jsonl(os.path.join(run_dir, "answers.jsonl")))
    answer_key = read_jsonl(answers)
    correct_by_id = {item["id"]: item["correct"] for item in answer_key}

    right = 0
    wrong_ids = []

    for item in run_answers:
        request_id = item["id"]
        correct = correct_by_id.get(request_id, [])

        is_right = False

        if "error" not in item:
            pick = item.get("pick")

            if pick is None:
                is_right = len(correct) == 0
            else:
                is_right = pick in correct

        if is_right:
            right += 1
        else:
            wrong_ids.append(request_id)

    total = len(run_answers)
    return right, total, wrong_ids


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Score a run: how many of its requests are right."
    )
    ap.add_argument("run_dir", help="a run folder, e.g. runs/single-1")
    ap.add_argument(
        "--answers",
        default="data/public_answers.jsonl",
        help="the right answers (default: %(default)s)",
    )
    args = ap.parse_args()
    right, total, wrong = score(args.run_dir, args.answers)
    print(f"{right} of {total} right")
    for request_id in wrong:
        print(request_id)


if __name__ == "__main__":
    main()
