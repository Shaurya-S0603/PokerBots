from random import Random

from baseline_v4 import BASELINES, calling_station, loose_aggressive, random_bot, tight
from pokerbots_sdk import Observation, TOOLKIT_STRATEGIES, validate_decision
from pokerbots_sdk.equity_policy import (
  EQUITY_TRIALS_LARGE_TABLE, EQUITY_TRIALS_SMALL_TABLE, EquityProfile, equity_bot,
)


def observe(game, player):
  state = game.get_state(player.player_id)
  seats = [seat for seat in state["players"] if seat["in_hand"]]
  ids = [seat["player_id"] for seat in seats]
  dealer_index = ids.index(state["dealer"])
  late_seats = {state["dealer"]}
  if len(ids) >= 4:
    late_seats.add(ids[dealer_index - 1])
  own = next(seat for seat in seats if seat["player_id"] == player.player_id)
  opponents = [seat for seat in seats if not seat["folded"] and seat["player_id"] != player.player_id]
  respond_to = max((seat["current_bet"] + seat["stack"]
    for seat in opponents if not seat["all_in"]), default=0)
  return Observation(
    hole=tuple(own["hole_cards"]), board=tuple(state["board"]), stack=own["stack"],
    stacks=tuple((seat["player_id"], seat["stack"]) for seat in seats),
    current_bet=own["current_bet"], table_bet=state["table_bet"],
    big_blind=state["big_blind"], pot=state["pot"], late_position=player.player_id in late_seats,
    opponents=len(opponents), legal=game.legal_actions(player),
    effective_raise_total=min(own["current_bet"] + own["stack"], respond_to),
    has_all_in_opponent=any(seat["all_in"] for seat in opponents),
  )


class BotArena:
  def __init__(self, seed, styles, *, strategies=None):
    self.seed = seed
    self.styles = tuple(styles)
    self.custom_strategies = dict(strategies or {})
    seeds = Random(seed)
    self.deck_rng = Random(seeds.getrandbits(64))
    self.bot_rngs = [Random(seeds.getrandbits(64)) for _ in self.styles]

  def act(self, game, player, *, diagnostics=None):
    seat = player.player_id - 1
    view = observe(game, player)
    style = self.styles[seat]
    if style in self.custom_strategies:
      action, target = self.custom_strategies[style](view, self.bot_rngs[seat])
    elif style == "Equity":
      action, target = equity_bot(view, self.bot_rngs[seat], diagnostics=diagnostics, arena_opening=True)
    elif style in TOOLKIT_STRATEGIES:
      action, target = TOOLKIT_STRATEGIES[style](view, self.bot_rngs[seat], diagnostics=diagnostics)
    else:
      action, target = STRATEGIES[style](view, self.bot_rngs[seat])
    return apply_decision(game, player, view, action, target)


def apply_decision(game, player, view, action, target):
  validate_decision(view, action, target)
  if action == "raise":
    return action, game.raise_bet(player, target - view.current_bet)
  return action, getattr(game, action)(player)



STRATEGIES = {**BASELINES, "Equity": equity_bot, **TOOLKIT_STRATEGIES}
