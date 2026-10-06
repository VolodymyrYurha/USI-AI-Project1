"""Tests for score.py: main() prints what the handout says."""
import sys

import score


def test_main_prints_the_count_then_the_wrong_ids(monkeypatch, capsys):
    seen = {}

    def filled(run_dir, answers="data/public_answers.jsonl"):
        seen.update(run_dir=run_dir, answers=answers)
        return 8, 10, ["P003", "P007"]

    monkeypatch.setattr(score, "score", filled)
    monkeypatch.setattr(sys, "argv", ["score.py", "runs/single-1"])
    score.main()
    assert capsys.readouterr().out == "8 of 10 right\nP003\nP007\n"
    assert seen == {"run_dir": "runs/single-1", "answers": "data/public_answers.jsonl"}


def test_main_passes_another_answers_file(monkeypatch, capsys):
    monkeypatch.setattr(score, "score", lambda run_dir, answers: (0, 0, []) if answers == "other.jsonl" else None)
    monkeypatch.setattr(sys, "argv", ["score.py", "runs/x", "--answers", "other.jsonl"])
    score.main()
    assert capsys.readouterr().out == "0 of 0 right\n"
