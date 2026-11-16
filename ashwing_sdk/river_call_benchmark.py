"""Replay matched streams of hands and gate river sizing on past public actions."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import json
from random import Random
from statistics import quantiles
import sys

from arena import observe
from ashwing_v2_validation import BIG_BLIND, DEPTHS, game_for, step
from pokerbots_sdk import load_strategy
from pokerbots_sdk.hive_policy import hive_mind, river_value_pressure
from pokerbots_sdk.river_calls import RiverCallHistory, size_bucket
from turn_barrel_experiment import sized_opponent


PROFILES = ("Calling Station", "Bluff-heavy barreling", "Aggressive barreling",
  "Frequent overbetting", "Range + Sizing")
PRIMARY = PROFILES[:2]
COLD_HANDS = 50


def tail(game, rngs, hero, opponent):
  while not game.hand_over:
    seat = game.current_player
    view = observe(game, game.players[seat])
    rng = Random(rngs[seat].getrandbits(64))
    action = hive_mind(view, rng) if seat == hero else opponent(view, rng)
    step(game, view, action)
  return game.players[hero].stack


def settle_open(game, rngs, hero, opponent, view, action):
  """Play through one public opening river bet and capture its first response."""
  step(game, view, action)
  event = None
  if action[0] == "raise" and not game.hand_over and game.current_player != hero:
    seat = game.current_player
    response_view = observe(game, game.players[seat])
    response = opponent(response_view, Random(rngs[seat].getrandbits(64)))
    amount = action[1] - view.current_bet
    name = response[0]
    if name == "all_in" and response_view.legal["call_amount"] == response_view.stack:
      name = "call"
    event = (amount, view.pot, name)
    step(game, response_view, response)
  return tail(game, rngs, hero, opponent), event


def hand_branches(seed, depth, hero, opponent):
  game, rngs = game_for(seed, depth)
  while not game.hand_over:
    seat = game.current_player
    view = observe(game, game.players[seat])
    rng = Random(rngs[seat].getrandbits(64))
    if seat != hero:
      step(game, view, opponent(view, rng))
      continue
    if len(view.board) != 5 or not view.legal["check"]:
      step(game, view, hive_mind(view, rng))
      continue

    details = {}
    candidate = river_value_pressure(view, rng, diagnostics=details)
    control = details.get("baseline_value_action")
    if control is None:
      _, event = settle_open(game, rngs, hero, opponent, view, candidate)
      return 0, event, None, None
    alternate, alternate_rngs = deepcopy(game), deepcopy(rngs)
    changed, candidate_event = settle_open(alternate, alternate_rngs, hero, opponent, view, candidate)
    original, control_event = settle_open(game, rngs, hero, opponent, view, control)
    delta = changed - original
    return delta, control_event, candidate_event, (candidate[1] - view.current_bet, view.pot)
  return 0, None, None, None


def compare_hand(seed, depth, hero, opponent, history):
  delta, control_event, candidate_event, offer = hand_branches(seed, depth, hero, opponent)
  permitted = bool(offer and history.allows(*offer))
  return delta if permitted else 0, delta, candidate_event if permitted else control_event, bool(offer), permitted


def run_cell(job):
  profile, depth, start, pairs, hands = job
  opponent = load_strategy(profile) if profile == "Range + Sizing" else sized_opponent(profile)
  rows = []
  observations = Counter()
  for match in range(pairs):
    histories = (RiverCallHistory(), RiverCallHistory())
    pair = Counter()
    for index in range(hands):
      seed = start + match * hands + index
      for seat, history in enumerate(histories):
        gated, ungated, event, offered, fired = compare_hand(seed, depth, seat, opponent, history)
        pair.update(gated=gated, ungated=ungated, offered=offered, fired=fired)
        if index < COLD_HANDS:
          pair.update(cold_gated=gated, cold_ungated=ungated, cold_offered=offered, cold_fired=fired)
        if event:
          amount, pot, response = event
          history.record(amount, pot, response)
          observations[f"{size_bucket(amount, pot)} {response}"] += 1
    rows.append(dict(pair))
  print(f"{profile} · {depth} BB · {pairs} session pairs complete", file=sys.stderr, flush=True)
  return rows, dict(observations)


def summarize(rows, hands):
  rng = Random(986514)
  scale = 100 / (len(rows) * 2 * hands * BIG_BLIND)
  stats = {}
  for period, prefix, modifier in (("full", "", 1.), ("first_50", "cold_", hands / COLD_HANDS)):
    edges = [(row[prefix + "gated"], row[prefix + "ungated"]) for row in rows]
    variants = {"gated": [a for a, _ in edges], "ungated": [b for _, b in edges],
      "gated_minus_ungated": [a - b for a, b in edges]}
    period_stats = {key: sum(row[prefix + key] for row in rows) for key in ("offered", "fired")}
    for label, results in variants.items():
      point = sum(results) * scale * modifier
      draws = [sum(rng.choices(results, k=len(rows))) * scale * modifier for _ in range(1600)]
      cuts = quantiles(draws, n=40, method="inclusive")
      period_stats[label] = {"bb_per_100": point, "interval_95": [cuts[0], cuts[-1]]}
    stats[period] = period_stats
  return {"session_pairs": len(rows), "hands": len(rows) * 2 * hands, **stats}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--pairs", type=int, default=4, help="Mirrored session pairs in each control cell")
  parser.add_argument("--primary-pairs", type=int, default=8)
  parser.add_argument("--hands", type=int, default=120, help="Chronological hands per session")
  args = parser.parse_args()
  if min(args.pairs, args.primary_pairs) < 2 or args.hands < COLD_HANDS:
    parser.error("require two session pairs and at least 50 hands per session")
  report = {"hands_per_session": args.hands, "cells": [], "profiles": {}}
  groups = defaultdict(list)
  jobs = []
  start = 1600001
  for depth in DEPTHS:
    for profile in PROFILES:
      pairs = args.primary_pairs if profile in PRIMARY else args.pairs
      jobs.append((profile, depth, start, pairs, args.hands))
      start += pairs * args.hands
  with ProcessPoolExecutor(max_workers=7) as pool:
    for job, result in zip(jobs, pool.map(run_cell, jobs), strict=True):
      profile, depth, start, _, hands = job
      rows, observations = result
      report["cells"].append({"profile": profile, "depth_bb": depth, "first_seed": start,
        "observations": observations, **summarize(rows, hands)})
      groups[profile].extend(rows)
  for profile, rows in groups.items():
    report["profiles"][profile] = summarize(rows, args.hands)
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
