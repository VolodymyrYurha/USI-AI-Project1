# Project 1: Analysis

## Results at a glance

All runs are on the 150 public requests. The saved outputs are in `results/`.

| System | Run | Right | Cost per request | Time per request |
|---|---|---|---|---|
| Single-call | `single01` | 🔴 84/150 (56.0%) | $0.00030 | 1.15 s |
| Single-call | `single02` | 🔴 84/150 (56.0%) | $0.00017 | 1.11 s |
| Compound, original | `compound01` | 🟡 140/150 (93.3%) | $0.00018 | 1.64 s |
| Compound, original | `compound02` | 🟡 140/150 (93.3%) | $0.00018 | 1.63 s |
| Compound, evidence-quote experiment (not kept) | `compound-rev01` | 🟡 141/150 (94.0%) | $0.00019 | 1.62 s |
| Compound, revised | `compound-rev02` | 🟢 145/150 (96.7%) | $0.00018 | 1.57 s |

## The wrong requests (10 of 150)

These are the requests the original compound system got wrong in its second run (`compound02`). They fall into three groups.

### 🔴 The judge flagged a problem that isn't there (6 requests, too strict)

Fixed by our change:
- ✅ **P006** – Called a samurai duel game "scary" because of fighting and wounds, but violence isn't horror.
- ✅ **P040** – Rated both correct games as combat because of competition and the word "battle".
- ✅ **P068** – Rejected a game for "no combat" only because the description calls it a wargame.
- ✅ **P072** – Answered "nothing scary" by pointing to player elimination, which isn't horror.
- ✅ **P106** – Read "players modify the rules" as racing against the clock.

Not fixed:
- ❌ **P071** – Read "casualties in battle" as players being knocked out.

### 🟠 Complexity (3 requests)

- ❌ **P062** – Accepted a game whose card said medium, but the description says "easy-to-learn", so it's light.
- ❌ **P135** – Same mistake with "Simple rules". The correct game, a children's game, was also ruled out as light.
- ❌ **P145** – Ruled that same children's game out as light, but its description says it's complex enough for adults. The clues conflict, and the key calls it medium.

### 🟣 Extraction (1 request)

- ❌ **P108** – "A cooperative game would be nice, but it's not a must" was treated as a requirement, so the correct game was rejected.

## What we changed

We chose to fix the largest group: 6 of the 10 wrong requests. In all six, the second AI call (the one that reads a game's description) wrongly decided that a game broke a rule about fighting, horror or timers. It confused related ideas, for example reading violence as "scary" or the word "battle" as combat. It judged too strictly and rejected games that were actually correct.

**The change.** For fighting, horror and timer points that only the description can settle, a "poor" verdict is now treated as "mixed". The game can still be chosen if nothing better exists. A tag on the card, such as Fighting or Horror, still rules a game out as before.

**The result.** On the 150 public requests, the score rose from 140 to 145 correct (93.3% to 96.7%), and the number of wrong requests fell from 10 to 5. No request that was right before became wrong. This is one run of the revised version so far.

**Tried first, not kept.** Before this we asked the judge to quote the sentence that shows a problem before rating a game "poor" (`compound-rev01`). It scored 141/150 with the same 9 requests still wrong, so it had no clear effect.

## Still wrong after the change (5 requests)

P062, P071, P108, P135 and P145. The first three groups above explain them. We left them for a later round.

---

## Appendix: run logs

Commands used (inside the project's virtual environment, with the course endpoint and your own token set as environment variables):

```
python -m p1.run systems/single.py   --requests data/public.jsonl --out results/single01
python -m p1.run systems/single.py   --requests data/public.jsonl --out results/single02
python -m p1.run systems/compound.py --requests data/public.jsonl --out results/compound01
python -m p1.run systems/compound.py --requests data/public.jsonl --out results/compound02
python -m p1.run systems/compound.py --requests data/public.jsonl --out results/compound-rev01
python -m p1.run systems/compound.py --requests data/public.jsonl --out results/compound-rev02
python score_pretty.py results/<run>
```

### Single-call runs

```
single01   Done: 150 requests in 43.6 seconds. Declined 24, failed on 0. 150 model calls, cost $0.0444.
single02   Done: 150 requests in 42.4 seconds. Declined 24, failed on 0. 150 model calls, cost $0.0258.
```

- `single01`: 84/150 right (56.0%), 66 wrong: P007, P008, P009, P010, P012, P014, P016, P018, P023, P025, P026, P028, P029, P030, P033, P040, P043, P045, P046, P050, P052, P055, P057, P058, P061, P062, P065, P068, P069, P071, P072, P073, P074, P076, P077, P080, P081, P083, P086, P093, P095, P098, P100, P104, P105, P106, P107, P108, P110, P112, P116, P119, P120, P121, P126, P127, P130, P131, P132, P134, P135, P139, P144, P145, P146, P148
- `single02`: 84/150 right (56.0%), 66 wrong: P007, P008, P009, P010, P012, P014, P016, P018, P023, P025, P026, P028, P029, P030, P033, P040, P043, P045, P046, P050, P052, P055, P057, P058, P061, P062, P065, P066, P068, P069, P071, P072, P073, P074, P076, P077, P080, P083, P086, P093, P095, P098, P100, P104, P105, P106, P107, P108, P110, P112, P116, P119, P120, P121, P126, P127, P130, P131, P132, P134, P135, P139, P144, P145, P146, P148

### Compound runs, original

```
compound01   Done: 150 requests in 63.9 seconds. Declined 25, failed on 0. 212 model calls, cost $0.0277.
compound02   Done: 150 requests in 63.5 seconds. Declined 25, failed on 0. 212 model calls, cost $0.0277.
```

- `compound01`: 140/150 right (93.3%), 10 wrong: P006, P062, P068, P071, P072, P076, P106, P108, P135, P145
- `compound02`: 140/150 right (93.3%), 10 wrong: P006, P040, P062, P068, P071, P072, P106, P108, P135, P145

### Compound runs, enhanced

```
compound-rev01   Done: 150 requests in 63.1 seconds. Declined 24, failed on 0. 212 model calls, cost $0.0284.
compound-rev02   Done: 150 requests in 61.5 seconds. Declined 20, failed on 0. 212 model calls, cost $0.0277.
```

- `compound-rev01` (evidence-quote experiment): 141/150 right (94.0%), 9 wrong: P006, P062, P068, P071, P072, P106, P108, P135, P145
- `compound-rev02` (revised): 145/150 right (96.7%), 5 wrong: P062, P071, P108, P135, P145
