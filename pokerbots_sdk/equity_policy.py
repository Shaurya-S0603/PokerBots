"""Equity-based policies and position-aware bet sizing."""

from dataclasses import dataclass

from baseline_v4 import RANKS, calling_station, tight
from equity import exact_river_equity, sample_equity


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


def _in_opening_range(hole, late):
  (rank_a, suit_a), (rank_b, suit_b) = hole
  high, low = sorted((RANKS[rank_a], RANKS[rank_b]), reverse=True)
  suited = suit_a == suit_b
  if high == low:
    return high >= (4 if late else 7)
  if high == 14:
    return low >= (10 if late else 11) or (suited and (late or low >= 10))
  if late:
    return (high == 13 and low == 12) or (suited and (low >= 10 or (low >= 5 and high - low == 1)))
  return suited and high == 13 and low == 12


def _sized_raise(view, increment):
  legal = view.legal
  if not legal["raise"]:
    return None
  minimum = legal["min_raise_total"]
  maximum = min(legal["max_raise_total"], view.effective_raise_total)
  # A short all-in remains a legal raise when the engine offers it.
  if minimum > legal["max_raise_total"]:
    minimum = legal["max_raise_total"]
  if minimum > maximum:
    return None
  return "raise", min(maximum, max(minimum, view.table_bet + increment))


def equity_bot(view, rng, *, profile=EquityProfile(), diagnostics=None, arena_opening=False):
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

  # Facing only the blind is an opening decision. Comparing a showdown against
  # every seated opponent to immediate pot odds folds too many multiway opens.
  if (arena_opening and not view.board and call and view.table_bet == view.big_blind
      and _in_opening_range(view.hole, view.late_position)):
    opening = _sized_raise(view, view.big_blind * 3 // 2)
    if opening:
      if diagnostics is not None:
        diagnostics["decision_basis"] = "Preflop opening range"
      return opening

  cushion = profile.call_cushion if len(view.board) < 5 else profile.river_call_margin
  if legal["call"] and share < call / (view.pot + call) + cushion:
    return "fold", None

  value_threshold = max(0.35, 1 / (view.opponents + 1) + profile.value_edge)
  if not view.board and view.late_position and view.table_bet == view.big_blind:
    value_threshold -= profile.position_bonus
    if view.stack + view.current_bet <= 12 * view.big_blind:
      value_threshold -= profile.shallow_open_bonus

  if share >= value_threshold:
    raise_size = max(view.big_blind, int((view.pot + call) * profile.pot_fraction))
    raise_action = _sized_raise(view, raise_size)
    if raise_action:
      return raise_action
  return calling_station(view, rng)

