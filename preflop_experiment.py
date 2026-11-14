"""Compare Range + Sizing and isolate its challengers' preflop changes."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
from time import process_time_ns

from benchmark import Config, _interval, play_hand, summarize
from pokerbots_sdk import TOOLKIT_STRATEGIES
from river_experiment import LINE_FIXTURES, PROFILES, call_losses, fixture_decisions, opponent_policy, position_metrics


POLICIES = ("Value", "Range + Sizing", "Button Open Only", "Big Blind Defense Only", "Heads-up Preflop")
OPPONENTS = (*PROFILES, "Bluff-heavy barreling")
REPORT = LINE_FIXTURES.with_name("preflop-experiment.json")
BOOTSTRAP_SEED = 39404


def matchup(job):
  profile, stack, start, pairs, bootstrap = job
  config = Config(stack=stack)
  opponent = opponent_policy(profile)
  # The ablations delegate to Range + Sizing all hand from the other seat.
  shared = {"Button Open Only": 2, "Big Blind Defense Only": 1}
  control_records = {}
  runs = {}
  rows = []
  for name in POLICIES:
    times = []
    records = []
    for seed in range(start, start + pairs):
      hands = []
      for seat in (1, 2):
        key = seed, seat
        if shared.get(name) == seat:
          hand, elapsed = control_records[key]
        else:
          hand, elapsed = play_hand(seed, seat, profile, config, candidate=TOOLKIT_STRATEGIES[name],
            opponent_policy=opponent, track_calls=True, clock=process_time_ns, independent_decisions=True)
        if name == "Range + Sizing":
          control_records[key] = hand, elapsed
        if hand["illegal_actions"]:
          raise RuntimeError(f"{profile}, {stack} chips, {name}, seed {seed}: {hand['error']}")
        if name != "Value" and hand["deal_hash"] != runs["Value"][seed - start]["hands"][seat - 1]["deal_hash"]:
          raise RuntimeError(f"Policy changed the deal for seed {seed}")
        hands.append(hand)
        times.extend(elapsed)
      if hands[0]["deal_hash"] != hands[1]["deal_hash"]:
        raise RuntimeError(f"Seat swap changed the deal for seed {seed}")
      records.append({"pair_id": seed, "hands": hands})
    runs[name] = records
    row = summarize(records, times, config.big_blind, bootstrap, BOOTSTRAP_SEED)
    position = position_metrics(records, config.big_blind)
    responses = Counter(pair["hands"][1]["big_blind_open_response"] for pair in records)
    responses.pop(None, None)
    row.update(opponent=profile, strategy=name, position=position,
      large_call_losses=call_losses(records), big_blind_responses=dict(responses))
    row["delta_vs_value"], row["delta_interval_95"] = contrast(
      records, runs["Value"], config.big_blind, bootstrap)
    if name != "Value":
      control = runs["Range + Sizing"]
      row["delta_vs_range_sizing"], row["delta_range_sizing_interval_95"] = contrast(
        records, control, config.big_blind, bootstrap)
      row["position_delta_vs_range_sizing"] = {
        label: contrast(records, control, config.big_blind, bootstrap, seat=seat)
        for seat, label in enumerate(("button", "big_blind"))
      }
    rows.append(row)
    print(f"{stack // config.big_blind} BB · {profile} · {name}", flush=True)
  return rows


def contrast(records, control, big_blind, bootstrap, *, seat=None):
  indices = (0, 1) if seat is None else (seat,)
  # _interval normalizes by two hands per seed. Double single-seat totals
  # to express each estimate per 100 hands played in that position.
  factor = 2 // len(indices)
  deltas = [factor * sum(test["hands"][index]["net_chips"] - baseline["hands"][index]["net_chips"]
    for index in indices) for test, baseline in zip(records, control, strict=True)]
  return sum(deltas) * 100 / (len(deltas) * 2 * big_blind), _interval(
    deltas, big_blind, bootstrap, BOOTSTRAP_SEED)


def evaluate(start, pairs, shallow_pairs, bootstrap, workers, output):
  depths = [(1000, start, pairs), (150, start + pairs, shallow_pairs)]
  jobs = [(profile, stack, seed, count, bootstrap) for stack, seed, count in depths for profile in OPPONENTS]
  if workers == 1:
    completed = list(map(matchup, jobs))
  else:
    with ProcessPoolExecutor(max_workers=workers) as pool:
      completed = list(pool.map(matchup, jobs))
  fixtures = fixture_decisions(LINE_FIXTURES, ("Value", "Range + Sizing", "Heads-up Preflop"))
  reports = [{"config": {"stack": stack, "small_blind": 5, "big_blind": 10,
    "seed_start": seed, "pairs_per_opponent": count, "bootstrap_samples": bootstrap,
    "decision_clock": "process CPU time", "rng": "independent stream per decision",
    "opponents": list(OPPONENTS)},
    "results": [row for group in completed[index * len(OPPONENTS):(index + 1) * len(OPPONENTS)]
      for row in group], "fixtures": fixtures}
    for index, (stack, seed, count) in enumerate(depths)]
  output.write_text(json.dumps(reports, indent=2) + "\n")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--seed-start", type=int, default=104000)
  parser.add_argument("--pairs", type=int, default=1200)
  parser.add_argument("--shallow-pairs", type=int, default=600)
  parser.add_argument("--bootstrap", type=int, default=3000)
  parser.add_argument("--workers", type=int, default=4)
  parser.add_argument("--output", type=Path, default=REPORT)
  args = parser.parse_args()
  if args.seed_start < 0 or min(args.pairs, args.shallow_pairs, args.bootstrap) < 2 or args.workers < 1:
    parser.error("Use a nonnegative seed start, at least two pairs and bootstrap draws, and a positive worker count")
  evaluate(args.seed_start, args.pairs, args.shallow_pairs, args.bootstrap, args.workers, args.output)


if __name__ == "__main__":
  main()
