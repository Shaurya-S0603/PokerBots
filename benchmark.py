"""Offline, paired heads-up benchmark for the PokerRoom strategies."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import median, quantiles
import subprocess
import sys
from time import perf_counter_ns

from arena import (EQUITY_TRIALS_LARGE_TABLE, EQUITY_TRIALS_SMALL_TABLE,
  BotArena, apply_decision, equity_bot, observe)
from baseline_v4 import BASELINES
from poker_engine import start_game

BASELINE_VERSION = "219a70131509a2eab6f6c9fd4a8f4fff83f6f8ff"


@dataclass(frozen=True)
class Config:
  stack: int = 1000
  small_blind: int = 5
  big_blind: int = 10

  def __post_init__(self):
    if not 0 < self.small_blind < self.big_blind <= self.stack:
      raise ValueError("Require 0 < small blind < big blind <= starting stack")


def play_hand(seed, equity_seat, opponent, config):
  arena = BotArena(seed, ("Equity", opponent))
  game = start_game(2, config.stack, config.small_blind, config.big_blind, deck_rng=arena.deck_rng)
  # Hash the hole cards by seat and the remaining deck before either bot acts.
  deal = [*[p.hole_cards for p in game.players], game.deck]
  deal_hash = sha256(json.dumps(deal).encode()).hexdigest()
  strategies = {equity_seat: equity_bot, 3 - equity_seat: BASELINES[opponent]}
  times = []
  vpip = pfr = False
  for _ in range(500):
    if game.hand_over:
      return {"equity_seat": equity_seat, "net_chips": game.players[equity_seat - 1].stack - config.stack,
        "deal_hash": deal_hash, "vpip": vpip, "pfr": pfr, "illegal_actions": 0}, times
    player = game.players[game.current_player]
    view = observe(game, player)
    rng = arena.bot_rngs[player.player_id - 1]
    action_started = perf_counter_ns()
    action, target = strategies[player.player_id](view, rng)
    if player.player_id == equity_seat:
      times.append((perf_counter_ns() - action_started) / 1_000_000)
      if not view.board:
        vpip |= action in {"call", "raise", "all_in"}
        pfr |= action == "raise" or (action == "all_in" and view.current_bet + view.stack > view.table_bet)
    try:
      _, ok = apply_decision(game, player, view, action, target)
      if not ok:
        raise ValueError(game.last_error)
    except ValueError as error:
      return {"equity_seat": equity_seat, "net_chips": None, "deal_hash": deal_hash,
        "illegal_actions": 1, "error": f"Seat {player.player_id}: {error}"}, times
    if sum(p.stack for p in game.players) + game.pot != 2 * config.stack:
      raise RuntimeError("Chip conservation failed")
  raise RuntimeError("Hand exceeded the benchmark action limit")


def play_pair(seed, opponent, config):
  first, times_first = play_hand(seed, 1, opponent, config)
  second, times_second = play_hand(seed, 2, opponent, config)
  if first["deal_hash"] != second["deal_hash"]:
    raise RuntimeError("Seat swap changed the deal")
  return {"pair_id": seed, "hands": [first, second]}, times_first + times_second


def _interval(pair_totals, big_blind, samples, seed):
  if len(pair_totals) < 2:
    return None
  rng = Random(seed)
  scale = 100 / (2 * len(pair_totals) * big_blind)
  distribution = [sum(rng.choices(pair_totals, k=len(pair_totals))) * scale for _ in range(samples)]
  cuts = quantiles(distribution, n=40, method="inclusive")
  return [cuts[0], cuts[-1]]


def summarize(pairs, times, big_blind, bootstrap, seed):
  outcomes = [hand for pair in pairs for hand in pair["hands"]]
  valid = [pair for pair in pairs if all(hand["net_chips"] is not None for hand in pair["hands"])]
  hands = [hand for pair in valid for hand in pair["hands"]]
  totals = [sum(hand["net_chips"] for hand in pair["hands"]) for pair in valid]
  return {
    "attempted_hands": len(outcomes), "hands": len(hands), "pairs": len(valid),
    "net_chips": sum(totals),
    "bb_per_100": 100 * sum(totals) / (len(hands) * big_blind) if hands else None,
    "interval_95": _interval(totals, big_blind, bootstrap, seed),
    "illegal_actions": sum(hand["illegal_actions"] for hand in outcomes),
    "vpip": sum(hand["vpip"] for hand in hands) / len(hands) if hands else None,
    "pfr": sum(hand["pfr"] for hand in hands) / len(hands) if hands else None,
    "decision_ms_median": median(times) if times else None,
    "decision_ms_p95": quantiles(times, n=20, method="inclusive")[-1] if len(times) > 1 else next(iter(times), None),
  }


def benchmark(opponents, config, *, start, pairs, split, bootstrap, version, include_pairs=False):
  if split not in {"tuning", "evaluation"} or start < 0 or pairs < 1 or bootstrap < 2:
    raise ValueError("Use a valid split, nonnegative seed start, positive pair count and at least two bootstrap samples")
  seeds = range(2 * start + (split == "evaluation"), 2 * (start + pairs), 2)
  report = {"schema_version": 1, "config": {
    "code_version": version, "baseline_version": BASELINE_VERSION, "python": sys.version.split()[0],
    "split": split, "seed_start": start, "pair_count": pairs, "bootstrap_samples": bootstrap,
    "stack": config.stack, "small_blind": config.small_blind, "big_blind": config.big_blind,
    "equity_trials": [EQUITY_TRIALS_SMALL_TABLE, EQUITY_TRIALS_LARGE_TABLE],
  }, "results": []}
  for index, opponent in enumerate(opponents):
    records, times = [], []
    for seed in seeds:
      record, elapsed = play_pair(seed, opponent, config)
      records.append(record)
      times.extend(elapsed)
    row = {"opponent": opponent, **summarize(records, times, config.big_blind, bootstrap, start + index)}
    if include_pairs:
      row["pair_results"] = records
    report["results"].append(row)
  return report


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--opponent", choices=list(BASELINES), action="append")
  parser.add_argument("--pairs", type=int, default=100)
  parser.add_argument("--seed-start", type=int, default=0)
  parser.add_argument("--split", choices=["tuning", "evaluation"], default="evaluation")
  parser.add_argument("--stack", type=int, default=1000)
  parser.add_argument("--small-blind", type=int, default=5)
  parser.add_argument("--big-blind", type=int, default=10)
  parser.add_argument("--bootstrap", type=int, default=2000)
  parser.add_argument("--output", type=Path)
  parser.add_argument("--include-pairs", action="store_true")
  parser.add_argument("--code-version", help="Override the Git commit for a source archive")
  args = parser.parse_args()
  try:
    version = args.code_version or subprocess.check_output(
      ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent, text=True).strip()
    report = benchmark(args.opponent or list(BASELINES), Config(args.stack, args.small_blind, args.big_blind),
      start=args.seed_start, pairs=args.pairs, split=args.split, bootstrap=args.bootstrap,
      version=version, include_pairs=args.include_pairs or args.pairs == 1)
  except (ValueError, subprocess.CalledProcessError) as error:
    parser.error(str(error))
  data = json.dumps(report, indent=2) + "\n"
  if args.output:
    args.output.write_text(data, encoding="utf-8")
  else:
    print(data, end="")
  return int(any(row["illegal_actions"] for row in report["results"]))


if __name__ == "__main__":
  raise SystemExit(main())
