"""Select a river-call gate on training matches and score it on disjoint matches."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import sys

from pokerbots_sdk import load_strategy
from pokerbots_sdk.river_calls import RiverCallHistory, RiverCallProfile
from river_call_benchmark import COLD_HANDS, PROFILES, hand_branches, summarize
from turn_barrel_experiment import sized_opponent
from ashwing_v2_validation import DEPTHS


CONFIGS = {"original": RiverCallProfile(), "balanced": RiverCallProfile(3, .67),
  "fast": RiverCallProfile(2.5, .64), "stronger size transfer": RiverCallProfile(3, .67, .80)}
STATION = "Calling Station"
BLUFF = "Bluff-heavy barreling"


def run_cell(job):
  profile, depth, first, pairs, hands, names = job
  opponent = load_strategy(profile) if profile == "Range + Sizing" else sized_opponent(profile)
  rows = defaultdict(list)
  for pair in range(pairs):
    histories = {name: [RiverCallHistory(CONFIGS[name]) for _ in range(2)] for name in names}
    totals = {name: Counter() for name in names}
    for index in range(hands):
      for seat in (0, 1):
        seed = first + pair * hands + index
        delta, control, alternative, offer = hand_branches(seed, depth, seat, opponent)
        for name in names:
          history = histories[name][seat]
          fired = bool(offer and history.allows(*offer))
          fields = dict(gated=delta if fired else 0, ungated=delta, offered=bool(offer), fired=fired)
          totals[name].update(fields)
          if index < COLD_HANDS:
            totals[name].update({f"cold_{key}": value for key, value in fields.items()})
          response = alternative if fired else control
          if response:
            history.record(*response)
    for name, row in totals.items():
      rows[name].append(dict(row))
  print(f"{profile} · {depth} BB · {pairs} pairs", file=sys.stderr, flush=True)
  return rows


def evaluate(split, names, pairs, hands):
  profiles = (STATION, BLUFF, "Frequent overbetting") if split == "train" else (*PROFILES, "Loose-Aggressive", "Tight")
  first = 2200001 if split == "train" else 2500001
  jobs = []
  for depth in DEPTHS:
    for profile in profiles:
      count = pairs if profile in (STATION, BLUFF) else max(2, pairs // 2)
      jobs.append((profile, depth, first, count, hands, names))
      first += count * hands
  report = {"split": split, "hands_per_match": hands, "cells": [], "profiles": {}}
  grouped = defaultdict(list)
  with ProcessPoolExecutor(max_workers=7) as pool:
    for job, results in zip(jobs, pool.map(run_cell, jobs), strict=True):
      profile, depth, seed, _, _, _ = job
      cell = {"profile": profile, "depth_bb": depth, "first_seed": seed, "results": {}}
      for name, rows in results.items():
        grouped[name, profile].extend(rows)
        cell["results"][name] = summarize(rows, hands)
      report["cells"].append(cell)
  for (name, profile), rows in grouped.items():
    report["profiles"].setdefault(name, {})[profile] = summarize(rows, hands)
  return report


def select(training):
  def score(name):
    profiles = training["profiles"][name]
    risk = sum(period["fired"] for profile, stats in profiles.items()
      if profile != STATION for period in (stats["full"],))
    return -risk, profiles[STATION]["first_50"]["gated"]["bb_per_100"]
  return max(CONFIGS, key=score)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("split", choices=("train", "holdout"))
  parser.add_argument("--pairs", type=int, required=True)
  parser.add_argument("--hands", type=int, required=True)
  parser.add_argument("--training-report", type=Path)
  args = parser.parse_args()
  if args.pairs < 2 or args.hands < COLD_HANDS:
    parser.error("require two pairs and at least 50 hands")
  if args.split == "train":
    report = evaluate(args.split, tuple(CONFIGS), args.pairs, args.hands)
    selected = select(report)
  else:
    if not args.training_report:
      parser.error("provide the training report to freeze the selected profile")
    training = json.loads(args.training_report.read_text())
    selected = training["selected"]
    if asdict(CONFIGS[selected]) != training["selected_profile"]:
      parser.error("selected profile differs from the frozen training report")
    report = evaluate(args.split, tuple(dict.fromkeys((selected, "original"))), args.pairs, args.hands)
  report.update(selected=selected, selected_profile=asdict(CONFIGS[selected]))
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
