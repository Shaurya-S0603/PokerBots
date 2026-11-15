"""Crown One Above All with a seeded Arena tournament and fresh confirmation."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations
import json
from pathlib import Path
from random import Random

from arena import BotArena, apply_decision, observe
from benchmark import Config, _interval, play_pair
from poker_engine import start_game
from pokerbots_sdk.champion_policy import SELECTION, TITLE, roster

INCUMBENT = {"heads_up": "Value", "multiway": "Position Pressure Equity"}
DEPTHS = (15, 100)
SEED = 126000
MULTIWAY_ROUNDS = 32


def duel(job):
  first, second, depth, seed, pairs = job
  entrants = roster()
  config = Config(stack=depth * 10)
  totals = []
  for current in range(seed, seed + pairs):
    record, _ = play_pair(current, second, config, candidate=entrants[first],
      opponent_policy=entrants[second], independent_decisions=True)
    if any(hand["illegal_actions"] for hand in record["hands"]):
      raise RuntimeError(f"Illegal action in {first} vs {second}, seed {current}: {record}")
    totals.append(sum(hand["net_chips"] for hand in record["hands"]))
  return first, second, depth, totals


def arena_hand(job):
  names, seed = job
  arena = BotArena(seed, names)
  game = start_game(len(names), 1000, 5, 10, deck_rng=arena.deck_rng)
  entrants = roster()
  for _ in range(500):
    if game.hand_over:
      return [player.stack - 1000 for player in game.players]
    player = game.players[game.current_player]
    seat = player.player_id - 1
    view = observe(game, player)
    rng = Random(arena.bot_rngs[seat].getrandbits(64))
    action, target = entrants[names[seat]](view, rng)
    if not apply_decision(game, player, view, action, target)[1]:
      raise RuntimeError(f"{names[seat]} rejected at seed {seed}: {game.last_error}")
    if sum(p.stack for p in game.players) + game.pot != len(names) * 1000:
      raise RuntimeError("Chip conservation failed")
  raise RuntimeError("Multiway hand exceeded the action limit")


def score(totals):
  return sum(totals) * 5 / len(totals)


def result(totals):
  return {"bb_per_100": score(totals), "interval_95": _interval(totals, 10, 3000, 93541)}


def rank(rows):
  return sorted(rows, key=lambda row: (-row["bb_per_100"], row["name"]))


def run(output, pairs, holdout, workers):
  names = tuple(roster())
  print(f"Screening {len(names)} entrants in heads-up and multiway Arena play", flush=True)
  with ProcessPoolExecutor(max_workers=workers) as pool:
    totals = {name: {depth: [] for depth in DEPTHS} for name in names}
    pairings = [(a, b, depth, SEED + i * pairs, pairs)
      for i, (a, b, depth) in enumerate((a, b, depth) for a, b in combinations(names, 2) for depth in DEPTHS)]
    for index, (a, b, depth, values) in enumerate(pool.map(duel, pairings, chunksize=1), 1):
      totals[a][depth].extend(values)
      totals[b][depth].extend(-value for value in values)
      if index % 100 == 0:
        print(f"Heads-up screening {index}/{len(pairings)} matchups", flush=True)
    heads_up = rank([{"name": name, "bb_per_100": sum(score(totals[name][d]) for d in DEPTHS) / len(DEPTHS),
      "by_depth": {str(d): score(totals[name][d]) for d in DEPTHS}} for name in names])

    pods = []
    rng = Random(SEED)
    for _ in range(MULTIWAY_ROUNDS):
      order = list(names)
      rng.shuffle(order)
      for start in range(0, len(order), 5):
        pod = tuple(order[start:start + 5])
        seed = 180000 + len(pods)
        pods.append((pod, seed))
    hands = [(pod[i:] + pod[:i], seed) for pod, seed in pods for i in range(len(pod))]
    multi_totals = {name: [] for name in names}
    for (table, _), chips in zip(hands, pool.map(arena_hand, hands), strict=True):
      for name, amount in zip(table, chips, strict=True):
        multi_totals[name].append(amount)
    multiway = rank([{"name": name, "bb_per_100": sum(chips) * 10 / len(chips), "hands": len(chips)}
      for name, chips in multi_totals.items()])
    print(f"Screen winners: heads-up {heads_up[0]['name']}; multiway {multiway[0]['name']}", flush=True)

    heads = heads_up[0]["name"]
    old_heads = INCUMBENT["heads_up"]
    rivals = dict.fromkeys([old_heads, *(row["name"] for row in heads_up[1:4])])
    jobs = [(heads, rival, depth, 200000 + i * holdout, holdout)
      for i, (rival, depth) in enumerate((rival, depth) for rival in rivals if rival != heads for depth in DEPTHS)]
    confirmed = {}
    incumbent_totals = []
    for _, rival, depth, values in pool.map(duel, jobs):
      confirmed.setdefault(rival, {})[str(depth)] = result(values)
      if rival == old_heads:
        incumbent_totals.extend(values)
    edge = result(incumbent_totals) if incumbent_totals else None
    chosen_heads = heads if edge and edge["interval_95"][0] > 0 else old_heads

    multi = multiway[0]["name"]
    old_multi = INCUMBENT["multiway"]
    lineup = tuple(row["name"] for row in multiway if row["name"] not in {multi, old_multi})[:3]
    table = (multi, old_multi, *lineup)
    outcomes = []
    if multi != old_multi:
      # Both finalists occupy every seat once in each common deal.
      eval_hands = [(table[i:] + table[:i], seed)
        for seed in range(220000, 220000 + holdout // 2) for i in range(len(table))]
      group = 0
      for index, ((seats, _), chips) in enumerate(zip(eval_hands, pool.map(arena_hand, eval_hands), strict=True), 1):
        group += chips[seats.index(multi)] - chips[seats.index(old_multi)]
        if index % len(table) == 0:
          outcomes.append(2 * group / len(table))
          group = 0
    multi_edge = result(outcomes) if outcomes else None
    chosen_multi = multi if multi_edge and multi_edge["interval_95"][0] > 0 else old_multi

  report = {"name": TITLE, "config": {"screen_pairs_per_depth": pairs, "heads_up_holdout_pairs_per_depth": holdout,
    "heads_up_depths": list(DEPTHS), "screen_seed_start": SEED, "multiway_screen_seed_start": 180000,
    "heads_up_holdout_seed_start": 200000, "multiway_holdout_seed_start": 220000,
    "multiway_starting_bb": 100, "multiway_screen_rounds": MULTIWAY_ROUNDS, "entrants": len(names)},
    "heads_up": {"selected": chosen_heads, "finalist": heads, "incumbent": old_heads,
      "leaderboard": heads_up, "holdout": confirmed, "incumbent_edge": edge},
    "multiway": {"selected": chosen_multi, "finalist": multi, "incumbent": old_multi,
      "leaderboard": multiway, "holdout_seed_blocks": len(outcomes), "holdout_opponents": list(lineup),
      "incumbent_edge": multi_edge}}
  output.write_text(json.dumps(report, indent=2) + "\n")
  print(f"{TITLE}: {chosen_heads} heads-up; {chosen_multi} multiway", flush=True)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--pairs", type=int, default=20)
  parser.add_argument("--holdout", type=int, default=320)
  parser.add_argument("--workers", type=int, default=8)
  parser.add_argument("--output", type=Path, default=SELECTION)
  args = parser.parse_args()
  if not 2 <= args.pairs <= 64 or not 8 <= args.holdout <= 2000 or args.workers < 1:
    parser.error("Use 2–64 screen pairs, 8–2,000 holdout pairs, and at least one worker")
  run(args.output, args.pairs, args.holdout, args.workers)


if __name__ == "__main__":
  main()
