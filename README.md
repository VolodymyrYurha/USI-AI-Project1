# Project 1 starter code

This folder holds the starter code for Project 1. Read the
[Project 1 handout](https://www.composablesystems.org/courses/engineering-ai-systems/fa2026/projects/project-1/)
first. In it, you find the task, the rules, how to set up, the steps for each milestone, how to label, and how
to submit.

## Files

| File | What it holds |
|---|---|
| `RUBRIC.md` | the rubric: how we decide the right answer for every request |
| `data/public.jsonl` | the 150 public requests, each with its five candidate games |
| `data/public_answers.jsonl` | the right answer to each public request: the letters of the acceptable games, or an empty list when the right answer is to decline |
| `data/practice.jsonl` | the 10 public practice requests |
| `data/labeling.jsonl` | the 10 hidden labeling requests, without answers |
| `systems/single.py` | your single-call system; you write its instructions |
| `systems/compound.py` | your compound system; at the start, it has one example step |
| `score.py` | your scorer; you write `score()` |
| `p1/` | the starter code's package. Don't change it: on Gradescope, we use our own copy. |
| `p1/version.py` | the version of this starter code |
| `tests/` | the starter code's tests; they make no model calls |

## Commands

Run each command in this folder, with your environment active. Add `--help` to any command to see its options.

```
# Run a system on the first 10 public requests. Leave out --limit to run all 150.
# Give each run its own --out folder.
python -m p1.run systems/single.py --requests data/public.jsonl --limit 10 --out runs/single-1

# Score a run with your scorer.
python score.py runs/single-1

# Check the contracts and the call limits of a run.
python -m p1.contracts runs/compound-1

# Send your model steps' inputs to the course app, then download your team's labels.
python -m p1.labels send systems/compound.py --requests data/practice.jsonl
python -m p1.labels pull

# Check that at least 2 of your compound system's model steps are connected (Milestone 2), with your labels.
python -m p1.contracts systems/compound.py

# Step accuracy: run your system on the requests you labeled, then compare one model step's outputs with your labels.
python -m p1.run systems/compound.py --requests data/practice.jsonl --out runs/compound-practice
python -m p1.labels accuracy runs/compound-practice --step my_step --labels labels/my_step.jsonl

# Swap-in test: run your system with your labels in place of one model step's outputs.
python -m p1.run systems/compound.py --requests data/public.jsonl --ids-from labels/my_step.jsonl \
    --override my_step=labels/my_step.jsonl --out runs/swap-my_step

# Run the starter code's tests.
python -m pytest
```

To test your code without spending budget, set `P1_BACKEND=fake`. You then get the same fake reply to every model
call, `{"pick": null, "explanation": "fake backend: no model was called"}`, so a step with a different output type
fails with a contract error.
