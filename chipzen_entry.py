"""Run Hold'em policies through Chipzen's Python SDK."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from random import Random

from chipzen import Action, Bot, run_external_bot

from pokerbots_sdk import Observation, load_strategy, validate_decision, value
from pokerbots_sdk.equity_policy import EquityProfile, equity_bot
from pokerbots_sdk.model import LineAction, OpponentBet

SUITS = {"h": "♥️", "d": "♦️", "c": "♣️", "s": "♠️"}
DEFAULT_POLICY = Path(__file__).resolve().parent / "training" / "competition-policy.json"


def _cards(cards):
  return tuple(("10" if card.rank == "T" else card.rank, SUITS[card.suit]) for card in cards)


def public_betting(history, own_seat, active_opponents):
  pot = 0
  street = None
  committed = {}
  bets = []
  line = []
  for entry in history:
    phase, seat, action, amount = (entry[key] for key in ("phase", "seat", "action", "amount"))
    if phase != street:
      street = phase
      committed.clear()
    already_paid = committed.get(seat, 0)
    if action in {"call", "raise"} and (seat == own_seat or seat in active_opponents):
      line.append(LineAction(seat != own_seat, street, action, amount, pot))
    if action == "raise":
      increment = amount - max(committed.values(), default=0)
      if seat in active_opponents and increment > 0:
        bets.append(OpponentBet(street, increment, pot))
      pot += amount - already_paid
      committed[seat] = amount
    elif action in {"post_small_blind", "post_big_blind", "call"}:
      pot += amount
      committed[seat] = already_paid + amount
    elif action == "post_ante":
      pot += amount
  return tuple(bets), tuple(line), committed


def observation(state, default_big_blind):
  big_blind = max(default_big_blind, next((entry["amount"] for entry in state.action_history
    if entry["action"] == "post_big_blind"), default_big_blind))
  own_bet = state.max_raise - state.your_stack
  table_bet = own_bet + state.to_call
  valid = state.valid_actions
  other_seats = (seat for seat in range(len(state.opponent_stacks) + 1) if seat != state.your_seat)
  acted = {entry["seat"] for entry in state.action_history}
  folded = {entry["seat"] for entry in state.action_history if entry["action"] == "fold"}
  seated = {seat: stack for seat, stack in zip(other_seats, state.opponent_stacks, strict=True)
    if stack > 0 or seat in acted or seat == state.dealer_seat}
  seated[state.your_seat] = state.your_stack
  opponents = {seat: stack for seat, stack in seated.items()
    if seat != state.your_seat and seat not in folded}
  bets, line, committed = public_betting(state.action_history, state.your_seat, opponents)

  # No action from the current street means the last historical commitment was
  # on a previous street. Use the board to distinguish this from a new bet.
  street = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(state.board)]
  if not state.action_history or state.action_history[-1]["phase"] != street:
    committed = {}
  effective_total = max((committed.get(seat, 0) + stack for seat, stack in opponents.items()
    if stack > 0), default=0)
  seats = sorted(seated)
  button_index = seats.index(state.dealer_seat)
  late = state.your_seat == state.dealer_seat or (len(seats) >= 4 and state.your_seat == seats[button_index - 1])
  return Observation(
    hole=_cards(state.hole_cards), board=_cards(state.board), stack=state.your_stack,
    stacks=tuple(sorted(seated.items())),
    current_bet=own_bet, table_bet=table_bet,
    big_blind=big_blind, pot=state.pot, late_position=late,
    opponents=len(opponents), legal={**{name: name in valid for name in ("fold", "call", "check", "raise", "all_in")},
      "call_amount": min(state.to_call, state.your_stack), "min_raise_total": state.min_raise,
      "max_raise_total": state.max_raise},
    effective_raise_total=min(state.max_raise, effective_total),
    has_all_in_opponent=any(stack == 0 for stack in opponents.values()),
    opponent_bets=bets, betting_line=line,
  )


class CompetitionBot(Bot):
  def __init__(self, profile=None, seed=None, *, strategy=None):
    if profile is not None and strategy is not None:
      raise ValueError("Choose a strategy or a policy profile")
    if profile is not None:
      def configured_policy(state, rng):
        return equity_bot(state, rng, profile=profile)
      strategy = configured_policy
    self.strategy = strategy or value
    self.rng = Random(seed)
    self.big_blind = 10

  def on_match_start(self, match_info):
    self.big_blind = match_info.get("game_config", {}).get("big_blind", 10)

  def on_reconnected(self, message):
    self.on_match_start(message)

  def decide(self, state):
    if len(state.hole_cards) != 2:
      raise ValueError("This policy requires two Hold’em hole cards")
    view = observation(state, self.big_blind)
    action, target = self.strategy(view, self.rng)
    validate_decision(view, action, target)
    if action == "raise":
      return Action.raise_to(target)
    return {"check": Action.check, "call": Action.call, "fold": Action.fold, "all_in": Action.all_in}[action]()


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  selection = parser.add_mutually_exclusive_group()
  selection.add_argument("--policy", type=Path)
  selection.add_argument("--strategy", default="Value", help="Built-in name or module:callable")
  parser.add_argument("--env", choices=("prod", "staging"), default="prod")
  parser.add_argument("--matches", type=int, default=1)
  args = parser.parse_args()
  bot_id = os.environ.get("CHIPZEN_BOT_ID")
  token = os.environ.get("CHIPZEN_EXTBOT_TOKEN")
  if not bot_id or not token or args.matches < 1:
    parser.error("Set CHIPZEN_BOT_ID and CHIPZEN_EXTBOT_TOKEN and use a positive match limit")
  profile = EquityProfile(**json.loads(args.policy.read_text())["profile"]) if args.policy else None
  strategy = None if profile is not None else load_strategy(args.strategy)
  logging.basicConfig(level=logging.INFO)
  asyncio.run(run_external_bot(lambda: CompetitionBot(profile, strategy=strategy), bot_id=bot_id, env=args.env,
    token=token, max_matches=args.matches))


if __name__ == "__main__":
  main()
