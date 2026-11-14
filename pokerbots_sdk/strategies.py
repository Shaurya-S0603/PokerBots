"""Built-in strategies using only the public bot observation."""

from dataclasses import replace
import json
from pathlib import Path

from .equity_policy import EquityProfile, equity_bot

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "training" / "competition-policy.json"
VALUE_PROFILE = EquityProfile(**json.loads(DEFAULT_POLICY.read_text())["profile"])


def value(state, rng, *, diagnostics=None):
  return equity_bot(state, rng, profile=VALUE_PROFILE, diagnostics=diagnostics)


def button_pressure(state, rng, *, diagnostics=None):
  # Widen button opens and use a smaller size. Facing an existing raise or
  # playing postflop uses the same Value policy.
  unopened = (
    state.opponents == 1 and not state.board and state.late_position
    and state.table_bet == state.big_blind
  )
  profile = replace(VALUE_PROFILE, position_bonus=.22, pot_fraction=.50) if unopened else VALUE_PROFILE
  return equity_bot(state, rng, profile=profile, diagnostics=diagnostics)


def pot_guard(state, rng, *, diagnostics=None):
  """Demand a larger equity cushion against substantial postflop bets."""
  call = state.legal["call_amount"]
  under_pressure = state.opponents == 1 and state.board and call > 0 and call * 3 >= state.pot
  profile = replace(VALUE_PROFILE, call_cushion=.09, river_call_margin=.075) if under_pressure else VALUE_PROFILE
  return equity_bot(state, rng, profile=profile, diagnostics=diagnostics)


def weighted_river(state, rng, *, diagnostics=None):
  """Test range-weighted showdown equity on heads-up river calls."""
  weights = None
  if state.opponents == 1 and len(state.board) == 5 and state.legal["call"]:
    last_bet = next((bet for bet in reversed(state.opponent_bets) if bet.street == "river"), None)
    if last_bet and last_bet.pot_before > 0:
      size = min(last_bet.increment / last_bet.pot_before, 2)
      prior_streets = {bet.street for bet in state.opponent_bets if bet.street in {"flop", "turn"}}
      weights = (1.0, 1 / (1 + 2 * size + len(prior_streets)))
  return equity_bot(state, rng, profile=VALUE_PROFILE, diagnostics=diagnostics, river_weights=weights)


TOOLKIT_STRATEGIES = {"Value": value, "Button Pressure": button_pressure, "Pot Guard": pot_guard,
  "Weighted River": weighted_river}
