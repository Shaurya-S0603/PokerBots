"""Run the selected heads-up Equity policy through Chipzen's Python SDK."""

import argparse
import asyncio
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
from random import Random

from chipzen import Action, Bot, run_external_bot

from pokerbots_sdk import Observation, load_strategy, validate_decision, value
from pokerbots_sdk.equity_policy import EquityProfile, equity_bot

SUITS = {"h": "♥️", "d": "♦️", "c": "♣️", "s": "♠️"}
DEFAULT_POLICY = Path(__file__).resolve().parent / "training" / "competition-policy.json"


def _cards(cards):
  return tuple(("10" if card.rank == "T" else card.rank, SUITS[card.suit]) for card in cards)


def observation(state, default_big_blind):
  big_blind = max(default_big_blind, next((entry["amount"] for entry in state.action_history
    if entry["action"] == "post_big_blind"), default_big_blind))
  own_bet = state.max_raise - state.your_stack
  opponent_stack, = state.opponent_stacks
  table_bet = own_bet + state.to_call
  valid = state.valid_actions
  return Observation(
    hole=_cards(state.hole_cards), board=_cards(state.board), stack=state.your_stack,
    stacks=((state.your_seat, state.your_stack), (1 - state.your_seat, opponent_stack)),
    current_bet=own_bet, table_bet=max(table_bet, big_blind) if not state.board else table_bet,
    big_blind=big_blind, pot=state.pot, late_position=state.your_seat == state.dealer_seat,
    opponents=1, legal={**{name: name in valid for name in ("fold", "call", "check", "raise")},
      "call_amount": min(state.to_call, state.your_stack), "min_raise_total": state.min_raise,
      "max_raise_total": state.max_raise},
    effective_raise_total=min(state.max_raise, table_bet + opponent_stack),
    has_all_in_opponent=opponent_stack == 0,
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
    if len(state.opponent_stacks) != 1 or len(state.hole_cards) != 2:
      raise ValueError("This policy supports heads-up Hold'em")
    view = observation(state, self.big_blind)
    # Preserve the reported call when a short blind changes the nominal bring-in.
    if not state.board and view.table_bet - view.current_bet > state.to_call:
      view = replace(view, table_bet=view.current_bet + state.to_call)
    action, target = self.strategy(view, self.rng)
    validate_decision(view, action, target)
    if action == "raise":
      return Action.raise_to(target)
    return {"check": Action.check, "call": Action.call, "fold": Action.fold}[action]()


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
