"""Train and select an Equity profile using public Arena and human match exports."""

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median, quantiles
from random import Random

from arena import BotArena, EquityProfile, apply_decision, equity_bot, observe
from poker_engine import start_game
from train_equity import CHAMPION_PATH, source_summary


def human_summary(raw, seat=1):
  history = json.loads(raw)
  if history.get("arena") or not history.get("hands"):
    raise ValueError("Expected a Human vs Bots history")
  hands = history["hands"]
  final = hands[-1]["steps"][-1]["table"]
  if not final["game_over"] or seat not in {p["player_id"] for p in final["players"]}:
    raise ValueError("Expected a completed game containing the selected human seat")
  frequencies = {}
  ratios = []
  for hand in hands:
    for previous, step in zip(hand["steps"], hand["steps"][1:]):
      action = step["action"]
      if not action or action["player_id"] != seat:
        continue
      table = previous["table"]
      own = next(p for p in table["players"] if p["player_id"] == seat)
      facing = max(p["current_bet"] for p in table["players"] if p["in_hand"] and not p["folded"]) > own["current_bet"]
      name = action["action"]
      if name == "all_in":
        name = "raise" if action["raised"] else "call"
      context = f"{action['phase']}:{'facing' if facing else 'free'}"
      frequencies.setdefault(context, Counter())[name] += 1
      if name == "raise" and table["pot"]:
        ratios.append(action["amount"] / table["pot"])
  return {"sha256": sha256(raw).hexdigest(), "hands": len(hands), "human_seat": seat,
    "human_final_chips": next(p["stack"] for p in final["players"] if p["player_id"] == seat),
    "counts": {key: dict(count) for key, count in frequencies.items()},
    "median_raise_fraction": round(median(ratios), 4) if ratios else None}


def human_proxy(summary):
  def choose(view, rng):
    phase = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(view.board)]
    facing = bool(view.legal["call"])
    counts = summary["counts"].get(f"{phase}:{'facing' if facing else 'free'}", {})
    actions = [move for move in ("check", "call", "fold", "raise") if view.legal[move]]
    # Smooth sparse observations and let the engine enforce the legal action set.
    prior = {"check": 5, "call": 3, "fold": 2 if facing else 0, "raise": 1}
    action = rng.choices(actions, [prior[move] + counts.get(move, 0) for move in actions])[0]
    if action != "raise":
      return action, None
    maximum = view.legal["max_raise_total"]
    minimum = min(maximum, view.legal["min_raise_total"])
    increment = int(view.pot * (summary["median_raise_fraction"] or 2 / 3))
    return action, min(maximum, max(minimum, view.current_bet + increment))
  return choose


def profile_strategy(profile):
  def choose(view, rng):
    return equity_bot(view, rng, profile=profile)
  return choose


def play(strategies, seed, *, full_game, stack=100):
  arena = BotArena(seed, strategies)
  names = list(strategies)
  game = start_game(len(names), stack, 5, 10, deck_rng=arena.deck_rng)
  deal = tuple(tuple(player.hole_cards) for player in game.players), tuple(game.deck)
  hands = Counter()
  won = Counter()
  decisions = 0
  while game.hand_number <= 1000 and decisions < 100_000:
    if game.hand_over:
      for name, player in zip(names, game.players):
        hands[name] += int(player.in_hand)
        won[name] += int(player.player_id in game.winners)
      if not full_game or game.game_over:
        return {"seed": seed, "hands": game.hand_number, "decisions": decisions,
          "starting_stack": stack, "small_blind": 5, "big_blind": 10,
          "results": [{"model": name, "seat": player.player_id, "final_chips": player.stack,
            "hands": hands[name], "hands_won": won[name]} for name, player in zip(names, game.players)]}, deal
      if not game.start_next_round():
        raise RuntimeError("Could not deal next hand")
      continue
    player = game.players[game.current_player]
    name = names[player.player_id - 1]
    view = observe(game, player)
    action, target = strategies[name](view, arena.bot_rngs[player.player_id - 1])
    if not apply_decision(game, player, view, action, target)[1]:
      raise RuntimeError(game.last_error)
    if sum(p.stack for p in game.players) + game.pot != stack * len(names):
      raise RuntimeError("Chip conservation failed")
    decisions += 1
  raise RuntimeError("Training match exceeded its action or hand limit")


def paired(candidate, opponent, seeds):
  totals = []
  for seed in seeds:
    first, deal_a = play({"Candidate": candidate, "Opponent": opponent}, seed, full_game=False)
    second, deal_b = play({"Opponent": opponent, "Candidate": candidate}, seed, full_game=False)
    if deal_a != deal_b:
      raise RuntimeError("Mirrored training deal changed")
    totals.append(first["results"][0]["final_chips"] + second["results"][1]["final_chips"] - 200)
  return totals


def paired_report(totals):
  scale = 100 / (20 * len(totals))
  rng = Random(2842)
  bootstrap = [sum(rng.choices(totals, k=len(totals))) * scale for _ in range(2000)]
  bounds = quantiles(bootstrap, n=40, method="inclusive")
  return {"pairs": len(totals), "bb_per_100": round(sum(totals) * scale, 2),
    "interval_95": [round(bounds[0], 2), round(bounds[-1], 2)]}


def run(arena_source, human_source, incumbent):
  fraction = min(0.9, max(0.4, arena_source["median_raise_fraction"] or 2 / 3))
  profiles = {
    "Positional Equity (incumbent)": incumbent,
    "Short-Stack Equity": EquityProfile(0.02, 0.15, 0.08, fraction, 0.0, 0.06),
    "River Defense Equity": EquityProfile(0.04, 0.17, 0.12, fraction, -0.06, 0.01),
    "Selective Equity": EquityProfile(0.06, 0.20, 0.07, fraction, 0.03, 0.02),
    "Pressure Equity": EquityProfile(0.03, 0.13, 0.10, min(0.9, fraction + 0.1), -0.02, 0.04),
  }
  strategies = {name: profile_strategy(profile) for name, profile in profiles.items()}
  names = list(profiles)
  wins = Counter()
  training_matches = []
  # Rotate all five candidates once through each starting seat.
  for i in range(5):
    order = names[i:] + names[:i]
    match, _ = play({name: strategies[name] for name in order}, 1000 + i, full_game=True)
    winner, = (row["model"] for row in match["results"] if row["final_chips"])
    wins[winner] += 1
    training_matches.append({"seed": match["seed"], "hands": match["hands"], "winner": winner})
  proxy = human_proxy(human_source)
  against_proxy = {name: paired_report(paired(strategy, proxy, range(2000, 2012)))
    for name, strategy in strategies.items()}
  proxy_order = sorted(names, key=lambda name: against_proxy[name]["bb_per_100"], reverse=True)
  finalists = sorted(names, key=lambda name: wins[name] / 5 + (4 - proxy_order.index(name)) / 4, reverse=True)[:3]
  # An independent tournament seed decides the latest training winner.
  final, _ = play({name: strategies[name] for name in finalists}, 3000, full_game=True)
  champion, = (row["model"] for row in final["results"] if row["final_chips"])
  holdout = range(4000, 4016)
  evaluation = {
    "against_incumbent": paired_report(paired(strategies[champion], profile_strategy(incumbent), holdout)),
    "against_human_style_proxy": paired_report(paired(strategies[champion], proxy, holdout)),
    "seed_start": holdout.start,
  }
  return {"generation": 2, "source": arena_source, "human_source": human_source,
    "candidate_profiles": {name: asdict(profile) for name, profile in profiles.items()},
    "screening": {"self_play": training_matches, "proxy_seed_start": 2000, "proxy_results": against_proxy},
    "training": final, "evaluation": evaluation, "champion": champion, "profile": asdict(profiles[champion])}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("arena_history", type=Path)
  parser.add_argument("human_history", type=Path)
  parser.add_argument("--human-seat", type=int, default=1)
  parser.add_argument("--output", type=Path, default=CHAMPION_PATH)
  args = parser.parse_args()
  incumbent_record = json.loads(CHAMPION_PATH.with_name("generation-1.json").read_text())
  result = run(source_summary(args.arena_history.read_bytes()),
    human_summary(args.human_history.read_bytes(), args.human_seat), EquityProfile(**incumbent_record["profile"]))
  temporary = args.output.with_suffix(".tmp")
  temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
  temporary.replace(args.output)
  print(result["champion"], result["training"]["hands"], result["evaluation"])


if __name__ == "__main__":
  main()
