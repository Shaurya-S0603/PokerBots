"""Choose the champion of one complete, seeded Equity-variant tournament."""

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from arena import BotArena, EquityProfile, apply_decision, equity_bot, observe
from poker_engine import start_game

CHAMPION_PATH = Path(__file__).resolve().parent / "training" / "champion.json"


def source_summary(raw):
  history = json.loads(raw)
  hands = history["hands"]
  final = hands[-1]["steps"][-1]["table"]
  winners = [p["player_id"] for p in final["players"] if p["stack"] > 0]
  styles = history["arena"]["styles"]
  if not final["game_over"] or len(winners) != 1 or not all(style == "Equity" for style in styles):
    raise ValueError("Expected a completed all-Equity Arena history")
  winner = winners[0]
  ratios = []
  for hand in hands:
    steps = hand["steps"]
    for previous, step in zip(steps, steps[1:]):
      action, pot = step["action"], previous["table"]["pot"]
      if action and action["player_id"] == winner and action["action"] == "raise" and pot:
        ratios.append(action["amount"] / pot)
  return {"sha256": sha256(raw).hexdigest(), "hands": len(hands), "winner_seat": winner,
    "seats": len(styles), "seed": history["arena"]["seed"], "winner_raises": len(ratios),
    "median_raise_fraction": round(median(ratios), 4) if ratios else None}


def train(source, seed):
  fraction = source["median_raise_fraction"] or 2 / 3
  fraction = min(0.9, max(0.4, fraction))
  candidates = {
    "Original Equity": EquityProfile(),
    "Patient Equity": EquityProfile(0.07, 0.20, 0.05, fraction),
    "Pressure Equity": EquityProfile(0.025, 0.14, 0.08, min(0.9, fraction + 0.12)),
    "Positional Equity": EquityProfile(0.04, 0.16, 0.12, fraction),
  }
  names = list(candidates)
  arena = BotArena(seed, names)
  stack, small, big = 100, 5, 10
  game = start_game(len(names), stack, small, big, deck_rng=arena.deck_rng)
  hands_played = [0] * len(names)
  hands_won = [0] * len(names)
  decisions = 0
  while True:
    if game.hand_number > 2000:
      raise RuntimeError("Training did not finish. Champion was not replaced.")
    if game.hand_over:
      for seat, player in enumerate(game.players):
        hands_played[seat] += int(player.in_hand)
        hands_won[seat] += int(player.player_id in game.winners)
      if game.game_over:
        break
      if not game.start_next_round():
        raise RuntimeError("Could not deal next training hand")
      continue
    player = game.players[game.current_player]
    seat = player.player_id - 1
    view = observe(game, player)
    action, target = equity_bot(view, arena.bot_rngs[seat], profile=candidates[names[seat]])
    if not apply_decision(game, player, view, action, target)[1]:
      raise RuntimeError(game.last_error)
    decisions += 1
    if sum(p.stack for p in game.players) + game.pot != stack * len(names):
      raise RuntimeError("Training failed chip conservation")
  results = [{"model": name, "seat": seat + 1, "final_chips": player.stack,
    "hands": hands_played[seat], "hands_won": hands_won[seat]}
    for seat, (name, player) in enumerate(zip(names, game.players))]
  champion, = (row["model"] for row in results if row["final_chips"] > 0)
  return {"source": source, "training": {"seed": seed, "hands": game.hand_number,
    "decisions": decisions, "starting_stack": stack, "small_blind": small, "big_blind": big,
    "results": results}, "champion": champion, "profile": asdict(candidates[champion])}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("history", type=Path)
  parser.add_argument("--seed", type=int, default=43)
  args = parser.parse_args()
  result = train(source_summary(args.history.read_bytes()), args.seed)
  CHAMPION_PATH.parent.mkdir(exist_ok=True)
  temporary = CHAMPION_PATH.with_suffix(".tmp")
  temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
  temporary.replace(CHAMPION_PATH)
  print(json.dumps(result, indent=2))


if __name__ == "__main__":
  main()
