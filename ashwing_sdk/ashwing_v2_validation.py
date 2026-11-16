"""Validate the defense and isolate the three offensive changes on fresh paired deals."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import json
from random import Random
from statistics import quantiles
import sys

from arena import BotArena, apply_decision, observe
from baseline_v4 import _has_draw, _postflop
from poker_engine import start_game
from pokerbots_sdk.hive_policy import hive_mind
from turn_barrel_experiment import PROFILES, sized_opponent


BIG_BLIND = 100
DEPTHS = (25, 50, 100)
DEFENSE_PROFILES = PROFILES[2:]
OFFENSE_TESTS = ("small flop sizing", "turn value", "turn semi-bluff")


def game_for(seed, depth):
  arena = BotArena(seed, ("Hero", "Opponent"))
  game = start_game(2, depth * BIG_BLIND, BIG_BLIND // 2, BIG_BLIND, deck_rng=arena.deck_rng)
  return game, arena.bot_rngs


def step(game, view, decision):
  player = game.players[game.current_player]
  total = sum(player.stack for player in game.players) + game.pot
  _, ok = apply_decision(game, player, view, *decision)
  if not ok:
    raise RuntimeError(game.last_error)
  if sum(player.stack for player in game.players) + game.pot != total:
    raise RuntimeError("Chip conservation failed")


def policy(view, seed, *, defense=False, offense=False, details=None):
  return hive_mind(view, Random(seed), bluff_catching=defense, turn_barrel=offense,
    diagnostics=details)


def finish(game, rngs, hero, depth, opponent, defense=False, value_streets=()):
  while not game.hand_over:
    seat = game.current_player
    view = observe(game, game.players[seat])
    seed = rngs[seat].getrandbits(64)
    action = (hive_mind(view, Random(seed), bluff_catching=defense, value_streets=value_streets)
      if seat == hero else opponent(view, Random(seed)))
    step(game, view, action)
  return game.players[hero].stack - depth * BIG_BLIND


def fork(game, rngs, view, control, change, hero, depth, opponent, *,
    defense=False, control_defense=False, value_streets=()):
  # The alternatives start with the exact same hole cards, board, deck,
  # stacks, betting history, and next RNG state for each seat.
  alternate, alternate_rngs = deepcopy(game), deepcopy(rngs)
  step(alternate, view, change)
  changed = finish(alternate, alternate_rngs, hero, depth, opponent, defense, value_streets)
  step(game, view, control)
  original = finish(game, rngs, hero, depth, opponent, control_defense)
  return changed - original


def defense_hand(seed, depth, hero, opponent, figures):
  game, rngs = game_for(seed, depth)
  while not game.hand_over:
    seat = game.current_player
    view = observe(game, game.players[seat])
    action_seed = rngs[seat].getrandbits(64)
    if seat != hero:
      step(game, view, opponent(view, Random(action_seed)))
      continue

    control = policy(view, action_seed)
    change = policy(view, action_seed, defense=True) if len(view.board) >= 4 else control
    if change == control:
      step(game, view, control)
      continue

    direction, category = "other action change", "other"
    call = view.legal["call_amount"]
    if {control[0], change[0]} == {"fold", "call"}:
      direction = "extra call" if change[0] == "call" else "avoided call"
      other = observe(game, game.players[1 - hero])
      strength = _postflop(other)
      category = {"strong": "value", "medium": "medium strength", "weak": "bluff"}[strength]
      if category == "bluff" and len(view.board) == 4 and _has_draw(other):
        category = "semi-bluff"
    delta = fork(game, rngs, view, control, change, hero, depth, opponent, defense=True)
    record = figures[direction][category]
    record.update(count=1, net_chips=delta, gross_gain_chips=max(delta, 0),
      gross_loss_chips=max(-delta, 0), call_price_chips=call)
    return delta
  return 0


def offense_hand(seed, depth, hero, opponent, test):
  game, rngs = game_for(seed, depth)
  while not game.hand_over:
    seat = game.current_player
    view = observe(game, game.players[seat])
    action_seed = rngs[seat].getrandbits(64)
    if seat != hero:
      step(game, view, opponent(view, Random(action_seed)))
      continue

    control = policy(view, action_seed)
    street = len(view.board)
    if street == 3 and view.legal["check"]:
      details = {}
      change = policy(view, action_seed, offense=True, details=details)
      if test == "small flop sizing":
        # Check/raise frequency is fixed. Switch only existing value raises
        # where the experiment wants a smaller size.
        if (control[0] == "raise" and details.get("decision_basis") == "Flop value"
            and change[1] < control[1]):
          return fork(game, rngs, view, control, change, hero, depth, opponent), 1, 1
      else:
        # Both turn arms use the same flop action and opponent response.
        control = change
    if street == 4 and test != "small flop sizing":
      flop = [action for action in view.betting_line if action.street == "flop"]
      if (view.legal["check"] and len(flop) == 2 and not flop[0].opponent
          and flop[0].action == "raise" and flop[0].amount * 2 <= flop[0].pot_before
          and flop[1].opponent and flop[1].action == "call"):
        details = {}
        change = policy(view, action_seed, offense=True, details=details)
        if details.get("decision_basis", "").lower() == test and change != control:
          return fork(game, rngs, view, control, change, hero, depth, opponent), 1, 1
        return 0, 1, 0
    step(game, view, control)
  return 0, 0, 0


def paired_summary(rows, seed):
  # Cluster outcome and opportunity counts by the original deal before resampling.
  rng = Random(seed)
  total, eligible, changed = map(sum, zip(*rows))
  per_hand = []
  per_spot = []
  for _ in range(1200):
    sample = rng.choices(rows, k=len(rows))
    delta, count, _ = map(sum, zip(*sample))
    per_hand.append(delta / (2 * len(rows)))
    if count:
      per_spot.append(delta / count)

  def interval(values):
    if len(values) < 2:
      return None
    cuts = quantiles(values, n=40, method="inclusive")
    return [cuts[0], cuts[-1]]

  return {"hands": len(rows) * 2, "eligible": eligible, "changed": changed,
    "net_bb": total / BIG_BLIND, "bb_per_100_hands": total / (2 * len(rows)),
    "interval_95": interval(per_hand),
    "bb_per_100_eligible": total / eligible if eligible else None,
    "eligible_interval_95": interval(per_spot)}


def run_cell(cell, pairs, start):
  group, depth, profile, test = cell
  opponent = sized_opponent(profile)
  figures = defaultdict(lambda: defaultdict(Counter))
  rows = []
  for seed in range(start, start + pairs):
    if group == "defense":
      delta = sum(defense_hand(seed, depth, seat, opponent, figures) for seat in (0, 1))
      rows.append((delta, 0, 0))
    else:
      results = [offense_hand(seed, depth, seat, opponent, test) for seat in (0, 1)]
      rows.append(tuple(map(sum, zip(*results))))
  return rows, {action: dict(categories) for action, categories in figures.items()}


def add_defense_attribution(report):
  by_depth = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
  for cell in report["cells"]:
    depth = str(cell["depth_bb"])
    for direction, categories in cell["call_attribution"].items():
      for category, counts in categories.items():
        by_depth[depth][direction][category].update(counts)
    cell["changed"] = sum(counts["count"] for categories in cell["call_attribution"].values()
      for counts in categories.values())
  for depth, summary in report["totals"].items():
    categories = by_depth[depth]
    summary["changed"] = sum(counts["count"] for group in categories.values() for counts in group.values())
    summary["call_attribution"] = categories
  for summary in [*report["cells"], *report["totals"].values()]:
    for field in ("eligible", "bb_per_100_eligible", "eligible_interval_95"):
      summary.pop(field, None)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("group", choices=("defense", "offense"))
  parser.add_argument("--pairs", type=int, default=350)
  args = parser.parse_args()
  if args.pairs < 2:
    parser.error("--pairs must be at least 2")

  if args.group == "defense":
    cells = [("defense", depth, profile, None) for depth in DEPTHS for profile in DEFENSE_PROFILES]
    starts = [200001 + index * args.pairs for index in range(len(cells))]
  else:
    cells = [("offense", 100, profile, test) for test in OFFENSE_TESTS for profile in PROFILES]
    starts = [500001 + PROFILES.index(cell[2]) * args.pairs for cell in cells]
  report = {"pairs_per_cell": args.pairs, "cells": [], "totals": {}}
  totals = defaultdict(list)
  with ProcessPoolExecutor(max_workers=5) as pool:
    jobs = [pool.submit(run_cell, cell, args.pairs, start) for cell, start in zip(cells, starts, strict=True)]
    for cell, start, job in zip(cells, starts, jobs, strict=True):
      _, depth, profile, test = cell
      rows, attribution = job.result()
      metrics = paired_summary(rows, start)
      report["cells"].append({"depth_bb": depth, "profile": profile, "test": test, "seed_start": start,
        **metrics, "call_attribution": attribution})
      totals[str(depth) if test is None else test].extend(rows)
      print(f"{depth} BB · {profile} · {test or 'defense'} complete", file=sys.stderr, flush=True)
  for key, rows in totals.items():
    report["totals"][key] = paired_summary(rows, 90481)
  if args.group == "defense":
    add_defense_attribution(report)
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
