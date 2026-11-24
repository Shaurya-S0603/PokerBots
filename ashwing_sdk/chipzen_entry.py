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
from pokerbots_sdk.adaptive_policy import TITLE as ASHWING_ADAPTIVE, ashwing_adaptive
from pokerbots_sdk.ashwing_policy import decide as ashwing_decide
from pokerbots_sdk.ashwing_v3 import decide as ashwing_v3_decide
from pokerbots_sdk.equity_policy import EquityProfile, equity_bot
from pokerbots_sdk.hive_policy import adaptive_river_value_pressure, hive_mind
from pokerbots_sdk.model import LineAction, OpponentBet, PublicAction
from pokerbots_sdk.v4_equity import PublicPlayer
from pokerbots_sdk.v4_history import PublicHistory
from pokerbots_sdk.river_calls import RiverCallHistory, RiverCallProfile
from pokerbots_sdk.search_policy import TITLE as ASHWING_SEARCH, ashwing_search

SUITS = {"h": "♥️", "d": "♦️", "c": "♣️", "s": "♠️"}
DEFAULT_POLICY = Path(__file__).resolve().parent / "training" / "competition-policy.json"

ASHWING = "Ashwing"
ASHWING_V2 = "Ashwing v2"


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
  # SDK calls/blinds are increments; raises are street raise-to totals.
  # Keep folded contributions for side pots. A mismatch makes V4 use its frozen expert.
  total, paid, public, phase, running_pot = {}, {}, [], None, 0
  for entry in state.action_history:
    actor, action, amount = entry['seat'], entry['action'], entry['amount']
    if entry['phase'] != phase:
      phase, paid = entry['phase'], {}
    public.append(PublicAction(actor, phase, action, amount, running_pot))
    increment = amount-paid.get(actor,0) if action == 'raise' else amount if action in ('call','post_small_blind','post_big_blind','post_ante') else 0
    total[actor] = total.get(actor,0)+increment
    running_pot += increment
    if action == 'raise': paid[actor] = amount
    elif action in ('call','post_small_blind','post_big_blind'): paid[actor] = paid.get(actor,0)+amount
  current = paid if phase == street else {}
  people = tuple(PublicPlayer(seat, stack, current.get(seat,0), total.get(seat,0), seat in folded,
    stack == 0 and seat not in folded) for seat,stack in sorted(seated.items()))
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
    opponent_bets=bets, betting_line=line, public_players=people, public_line=tuple(public),
    player_id=state.your_seat, dealer_id=state.dealer_seat,
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

  def choose(self, view):
    return self.strategy(view, self.rng)

  def decide(self, state):
    if len(state.hole_cards) != 2:
      raise ValueError("This policy requires two Hold’em hole cards")
    view = observation(state, self.big_blind)
    action, target = self.choose(view)
    validate_decision(view, action, target)
    if action == "raise":
      return Action.raise_to(target)
    return {"check": Action.check, "call": Action.call, "fold": Action.fold, "all_in": Action.all_in}[action]()


class AshwingV2Bot(CompetitionBot):
  def river_strategy(self, view, history):
    return adaptive_river_value_pressure(view, self.rng, history)

  def __init__(self, *, seed=None):
    super().__init__(seed=seed, strategy=hive_mind)
    profile = DEFAULT_POLICY.with_name("streamlit-river-gate.json")
    self.profile = RiverCallProfile(**json.loads(profile.read_text()))
    self.histories = {}
    self.completed = set()
    self.match_id = None
    self.own_seat = None

  def on_match_start(self, message):
    super().on_match_start(message)
    self.match_id = message.get("match_id")
    self.histories.clear()
    self.completed.clear()
    self.own_seat = next((seat["seat"] for seat in message.get("seats", ()) if seat["is_self"]), None)

  def on_reconnected(self, message):
    if message.get("match_id") != self.match_id or self.own_seat is None:
      self.on_match_start(message)
    else:
      super().on_match_start(message)

  def choose(self, view):
    if self.own_seat is None or len(view.stacks) != 2 or len(view.board) != 5:
      return super().choose(view)
    opponent = next(seat for seat, _ in view.stacks if seat != self.own_seat)
    return self.river_strategy(view, self._history(opponent))

  def _history(self, seat):
    if seat not in self.histories:
      self.histories[seat] = RiverCallHistory(self.profile)
    return self.histories[seat]

  def on_hand_result(self, result):
    actions = result.get("action_history", ())
    seats = {entry["seat"] for entry in actions}
    hand = result.get("round_id") or result.get("hand_number")
    if hand is None or hand in self.completed or len(seats) != 2 or self.own_seat not in seats:
      return
    self.completed.add(hand)
    for index, entry in enumerate(actions):
      if entry["phase"] == "river" and entry["action"] == "raise":
        break
    else:
      return
    if entry["seat"] != self.own_seat or entry.get("is_timeout"):
      return
    opponent = next(iter(seats - {self.own_seat}))
    response = next((move for move in actions[index + 1:]
      if move["phase"] == "river" and move["seat"] == opponent), None)
    if response is None or response.get("is_timeout") or response["action"] not in {"fold", "call", "raise"}:
      return
    _, line, _ = public_betting(actions[:index + 1], self.own_seat, {opponent})
    bet = line[-1]
    if bet.amount > 0 and bet.pot_before > 0:
      self._history(opponent).record(bet.amount, bet.pot_before, response["action"])


class AshwingAdaptiveBot(AshwingV2Bot):
  def river_strategy(self, view, history):
    return ashwing_adaptive(view, self.rng, history=history)


class AshwingSearchBot(AshwingAdaptiveBot):
  def __init__(self, *, seed=None):
    super().__init__(seed=seed)
    self.strategy = ashwing_search


class AshwingBot(AshwingV2Bot):
  def __init__(self, *, seed=None):
    super().__init__(seed=seed)
    self.strategy = ashwing_decide

  def river_strategy(self, view, history):
    return ashwing_decide(view, self.rng, history=history)


class AshwingV31Bot(AshwingBot):
  def __init__(self, *, seed=None):
    super().__init__(seed=seed)
    self.strategy = load_strategy("Ashwing v3.1")

  def river_strategy(self, view, history):
    return self.strategy(view, self.rng, history=history)


class AshwingMasterstatsBot(AshwingV31Bot):
  def __init__(self, *, seed=None):
    super().__init__(seed=seed)
    self.strategy = load_strategy("Ashwing Masterstats")


class AshwingV4Bot(AshwingV31Bot):
  def __init__(self, *, seed=None):
    super().__init__(seed=seed)
    self.strategy = load_strategy('Ashwing_V4')
    self.public_history = PublicHistory()

  def on_match_start(self, message):
    super().on_match_start(message)
    self.public_history.start(message.get('match_id'))

  def choose(self, view):
    opponent = next((seat for seat,_ in view.stacks if seat != self.own_seat),None) if len(view.stacks)==2 else None
    return self.strategy(view,self.rng,history=self._history(opponent) if opponent is not None else None,
      public_history=self.public_history)

  def on_hand_result(self, result):
    super().on_hand_result(result)
    self.public_history.record(result.get('round_id') or result.get('hand_number'),result.get('action_history',()))


def bot_for_strategy(name, *, seed=None):
  if name in ('Ashwing_V4','Ashwing v4'):
    return AshwingV4Bot(seed=seed)
  if name == "Ashwing Masterstats":
    return AshwingMasterstatsBot(seed=seed)
  if name == "Ashwing v3.1":
    return AshwingV31Bot(seed=seed)
  if name == "Ashwing v3":
    bot = AshwingBot(seed=seed)
    bot.strategy = ashwing_v3_decide
    return bot
  if name == ASHWING:
    return AshwingBot(seed=seed)
  if name == ASHWING_V2:
    return AshwingV2Bot(seed=seed)
  if name == ASHWING_ADAPTIVE:
    return AshwingAdaptiveBot(seed=seed)
  if name == ASHWING_SEARCH:
    return AshwingSearchBot(seed=seed)
  return CompetitionBot(strategy=load_strategy(name), seed=seed)


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
  factory = (lambda: CompetitionBot(profile)) if profile is not None else (lambda: bot_for_strategy(args.strategy))
  logging.basicConfig(level=logging.INFO)
  asyncio.run(run_external_bot(factory, bot_id=bot_id, env=args.env,
    token=token, max_matches=args.matches))


if __name__ == "__main__":
  main()
