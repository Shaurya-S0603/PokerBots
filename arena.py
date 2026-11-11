from dataclasses import dataclass
from random import Random

from equity import exact_river_equity, sample_equity
from baseline_v4 import BASELINES, calling_station, loose_aggressive, random_bot, tight


@dataclass(frozen=True)
class Observation:
  hole: tuple
  board: tuple
  stack: int
  stacks: tuple
  current_bet: int
  table_bet: int
  big_blind: int
  pot: int
  late_position: bool
  opponents: int
  legal: dict
  effective_raise_total: int
  has_all_in_opponent: bool


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
  def __init__(self, seed, styles):
    self.seed = seed
    self.styles = tuple(styles)
    seeds = Random(seed)
    self.deck_rng = Random(seeds.getrandbits(64))
    self.bot_rngs = [Random(seeds.getrandbits(64)) for _ in self.styles]

  def act(self, game, player, *, diagnostics=None):
    seat = player.player_id - 1
    view = observe(game, player)
    style = self.styles[seat]
    if style == "Equity":
      action, target = equity_bot(view, self.bot_rngs[seat], diagnostics=diagnostics)
    else:
      action, target = STRATEGIES[style](view, self.bot_rngs[seat])
    return apply_decision(game, player, view, action, target)


def apply_decision(game, player, view, action, target):
  if not view.legal.get(action):
    raise ValueError(f"Bot selected an illegal action: {action}")
  if action == "raise":
    minimum = min(view.legal["min_raise_total"], view.legal["max_raise_total"])
    if type(target) is not int or not minimum <= target <= view.legal["max_raise_total"]:
      raise ValueError("Bot selected an illegal raise target")
    return action, game.raise_bet(player, target - view.current_bet)
  return action, getattr(game, action)(player)



EQUITY_TRIALS_SMALL_TABLE = 256
EQUITY_TRIALS_LARGE_TABLE = 128


@dataclass(frozen=True)
class EquityProfile:
  call_cushion: float = 0.04
  value_edge: float = 0.17
  position_bonus: float = 0.06
  pot_fraction: float = 2 / 3
  river_call_margin: float = 0.0
  shallow_open_bonus: float = 0.0


def equity_bot(view, rng, *, profile=EquityProfile(), diagnostics=None):
  legal = view.legal
  call = legal["call_amount"]
  # A partial call or multiway all-in can expose less than the displayed pot.
  if call < view.table_bet - view.current_bet or (view.opponents > 1 and view.has_all_in_opponent):
    if diagnostics is not None:
      diagnostics.update(method="Tight fallback")
    return tight(view, rng)

  curve = [] if diagnostics is not None else None
  if len(view.board) == 5 and view.opponents == 1:
    result = exact_river_equity(view.hole, view.board)
    method = "Exact enumeration"
  else:
    trials = EQUITY_TRIALS_SMALL_TABLE if view.opponents <= 3 else EQUITY_TRIALS_LARGE_TABLE
    result = sample_equity(view.hole, view.board, view.opponents, trials, rng, checkpoints=curve)
    method = "Monte Carlo"
  share = result.equity
  if diagnostics is not None:
    diagnostics.update(method=method, opponents=view.opponents, wins=result.wins,
      ties=result.ties, losses=result.losses, equity=share, curve=curve)

  cushion = profile.call_cushion if len(view.board) < 5 else profile.river_call_margin
  if legal["call"] and share < call / (view.pot + call) + cushion:
    return "fold", None

  value_threshold = max(0.35, 1 / (view.opponents + 1) + profile.value_edge)
  if not view.board and view.late_position and view.table_bet == view.big_blind:
    value_threshold -= profile.position_bonus
    if view.stack + view.current_bet <= 12 * view.big_blind:
      value_threshold -= profile.shallow_open_bonus

  if legal["raise"] and share >= value_threshold:
    minimum = min(legal["min_raise_total"], legal["max_raise_total"])
    maximum = min(legal["max_raise_total"], view.effective_raise_total)
    if minimum <= maximum:
      raise_size = max(view.big_blind, int((view.pot + call) * profile.pot_fraction))
      return "raise", min(maximum, max(minimum, view.table_bet + raise_size))
  return calling_station(view, rng)


STRATEGIES = {**BASELINES, "Equity": equity_bot}
