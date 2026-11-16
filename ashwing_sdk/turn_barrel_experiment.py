"""Compare the turn-barrel and bluff-catching changes on paired heads-up deals."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import json

from baseline_v4 import BASELINES
from benchmark import Config, _interval, play_pair, summarize
from pokerbots_sdk.equity_policy import _sized_raise
from pokerbots_sdk.hive_policy import hive_mind
from river_experiment import opponent_policy


VARIANTS = {
  "baseline": (False, False),
  "defense": (True, False),
  "offense": (False, True),
  "combined": (True, True),
}
PROFILES = ("Calling Station", "Tight", "Bluff-heavy barreling", "Aggressive barreling",
  "Frequent overbetting")


def sized_opponent(profile):
  if profile in BASELINES:
    return BASELINES[profile]
  policy = opponent_policy(profile)

  def decide(view, rng):
    action, target = policy(view, rng)
    if action == "raise" and view.legal["check"] and len(view.board) in (3, 4):
      size = view.pot // 2 if len(view.board) == 3 else view.pot * 3 // 2
      return _sized_raise(view, max(view.big_blind, size)) or (action, target)
    return action, target
  return decide


def compare(profile_index, *, pairs, seed_start):
  profile = PROFILES[profile_index]
  opponent = sized_opponent(profile)
  config = Config(stack=10000, small_blind=50, big_blind=100)
  results, paired_totals = {}, {}
  start = seed_start + profile_index * pairs
  for name, (defense, offense) in VARIANTS.items():
    records, times = [], []
    selected = Counter()

    def candidate(view, rng):
      details = {} if offense else None
      action = hive_mind(view, rng, diagnostics=details, bluff_catching=defense, turn_barrel=offense)
      if details and details.get("experimental_bet"):
        selected[details["decision_basis"]] += 1
      return action

    for seed in range(start, start + pairs):
      record, timing = play_pair(seed, profile, config, candidate=candidate, opponent_policy=opponent,
        independent_decisions=True)
      records.append(record)
      times.extend(timing)
    summary = summarize(records, times, config.big_blind, 1000, start)
    if summary["illegal_actions"]:
      raise RuntimeError(f'{profile} / {name} selected an illegal action')
    results[name] = {"bb_per_100": summary["bb_per_100"], "p95_ms": summary["decision_ms_p95"],
      "selected_bets": dict(selected)}
    paired_totals[name] = [sum(hand["net_chips"] for hand in pair["hands"]) for pair in records]
  return profile, results, paired_totals


def deltas(totals, seed):
  comparisons = (("offense", "baseline"), ("defense", "baseline"), ("combined", "baseline"),
    ("combined", "defense"))
  results = {}
  for candidate, control in comparisons:
    changes = [a - b for a, b in zip(totals[candidate], totals[control], strict=True)]
    # A pair has two seat-swapped hands. One big blind is 100 chips.
    results[f"{candidate} vs {control}"] = {
      "bb_per_100": sum(changes) / (2 * len(changes)),
      "interval_95": _interval(changes, 100, 2000, seed),
    }
  return results


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--pairs", type=int, default=400, help="Seat-swapped pairs per opponent and variant")
  parser.add_argument("--seed-start", type=int, default=85001)
  args = parser.parse_args()
  if args.pairs < 2:
    parser.error("--pairs must be at least 2")

  totals = {name: [] for name in VARIANTS}
  report = {"pairs_per_opponent": args.pairs, "seed_start": args.seed_start, "opponents": {}}
  with ProcessPoolExecutor(max_workers=len(PROFILES)) as pool:
    run = partial(compare, pairs=args.pairs, seed_start=args.seed_start)
    for profile, results, paired_totals in pool.map(run, range(len(PROFILES))):
      report["opponents"][profile] = {"variants": results, "deltas": deltas(paired_totals, args.seed_start)}
      for name, chips in paired_totals.items():
        totals[name].extend(chips)
  report["pooled_deltas"] = deltas(totals, args.seed_start)
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
