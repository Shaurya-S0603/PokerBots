"""Built-in strategies using only the public bot observation."""

from dataclasses import replace
import json
from pathlib import Path

from baseline_v4 import calling_station

from .betting_line import evaluate_range, holding, opening_bet_values, preflop_strength
from .equity_policy import EQUITY_TRIALS_SMALL_TABLE, EquityProfile, _sized_raise, equity_bot

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


def line_range(state, rng, *, diagnostics=None, price_bets=False):
  """Test action-conditioned postflop equity, keeping Value's raise threshold."""
  if state.opponents != 1 or not state.board:
    return value(state, rng, diagnostics=diagnostics)
  call = state.legal["call_amount"]
  # A heads-up overbet above the remaining stack will be returned.
  pot = state.pot - max(0, state.table_bet - state.current_bet - call)
  curve = [] if diagnostics is not None else None
  result, weighted, outcomes = evaluate_range(state, rng, EQUITY_TRIALS_SMALL_TABLE, curve)
  share = result.equity
  river = len(state.board) == 5
  odds = call / (pot + call) if call else None
  threshold = odds + (VALUE_PROFILE.river_call_margin if river else VALUE_PROFILE.call_cushion) if call else None
  if diagnostics is not None:
    diagnostics.update(method="Exact enumeration" if river else "Monte Carlo",
      opponents=1, equity=share, weighted_equity=weighted, curve=curve, wins=result.wins,
      ties=result.ties, losses=result.losses, decision_basis="Opponent betting line")
    if call:
      diagnostics.update(pot_odds=odds, call_threshold=threshold)
  if call and weighted < threshold:
    return "fold", None

  large = _sized_raise(state, max(state.big_blind, int((state.pot + call) * VALUE_PROFILE.pot_fraction)))
  if price_bets and not call and large and len(state.board) >= 4:
    small = _sized_raise(state, max(state.big_blind, state.pot // 3))
    sizes = sorted({action[1] - state.current_bet for action in (small, large) if action})
    values = opening_bet_values(state, outcomes, sizes)
    # Require a made hand to value-bet. Thin pairs need a margin over checking
    # because this one-step comparison omits raises and future betting.
    made = holding(state.hole, state.board)
    margin = state.pot * (.05 if made.strength < .70 else .015)
    thin_value = made.strength < .55
    eligible = [values[0], *(row for row in values[1:]
      if not thin_value or row["worse_call_mass"] > row["better_call_mass"])]
    best = max(eligible, key=lambda row: row["ev_chips"])
    if diagnostics is not None:
      diagnostics.update(decision_basis="Bet EV against continuing range", bet_options=values,
        made_hand_strength=made.strength, bet_ev_margin=margin)
    if made.strength >= .45 and best["amount"] and best["ev_chips"] > values[0]["ev_chips"] + margin:
      return "raise", state.current_bet + best["amount"]
    return "check", None

  if share >= .5 + VALUE_PROFILE.value_edge and large:
    return large
  return calling_station(state, rng)


def range_and_sizing(state, rng, *, diagnostics=None):
  return line_range(state, rng, diagnostics=diagnostics, price_bets=True)


def heads_up_preflop(state, rng, *, diagnostics=None):
  if state.opponents != 1 or state.board:
    return range_and_sizing(state, rng, diagnostics=diagnostics)

  call = state.legal["call_amount"]
  depth = state.effective_raise_total / state.big_blind
  strength = preflop_strength(state.hole)
  prior = [step for step in state.betting_line if step.street == "preflop"]
  raises = [step for step in prior if step.action == "raise"]
  if state.late_position and not prior and call and state.table_bet <= state.big_blind:
    basis = "Button open"
    opening = _sized_raise(state, state.big_blind if depth <= 15 else state.big_blind * 3 // 2)
    threshold = .48 if depth <= 15 else .43
    action = (opening or ("call", None)) if strength >= threshold else ("fold", None)
  elif not call:
    threshold = .62
    basis = "Big blind versus limp"
    raise_action = _sized_raise(state, state.big_blind * 2)
    action = raise_action if strength >= threshold and raise_action else ("check", None)
  else:
    limped = state.late_position and any(not step.opponent and step.action == "call" for step in prior)
    if limped:
      basis = "Button facing raise after limp"
    elif not state.late_position and len(raises) <= 1:
      basis = "Big blind defense"
    else:
      basis = "Facing preflop re-raise"
    effective_pot = state.pot - max(0, state.table_bet - state.current_bet - call)
    price = call / (effective_pot + call)
    raise_size = state.table_bet / state.big_blind
    premium = .08 if limped else (.10 if len(raises) > 1 else 0)
    threshold = .35 + .45 * price + .024 * min(max(raise_size - 2.5, 0), 8) + premium
    if depth <= 15:
      threshold += .025
    raise_action = _sized_raise(state, max(state.big_blind, int(state.table_bet * 1.4)))
    if strength >= max(.69, threshold + .10) and raise_action:
      action = raise_action
    else:
      action = ("call" if strength >= threshold else "fold", None)
  if diagnostics is not None:
    diagnostics.update(method="Preflop range", decision_basis=basis,
      effective_stack_bb=depth, preflop_strength=strength, preflop_strength_threshold=threshold)
    if call:
      effective_pot = state.pot - max(0, state.table_bet - state.current_bet - call)
      diagnostics["pot_odds"] = call / (effective_pot + call)
  return action


TOOLKIT_STRATEGIES = {"Value": value, "Button Pressure": button_pressure, "Pot Guard": pot_guard,
  "Weighted River": weighted_river, "Line Range": line_range, "Range + Sizing": range_and_sizing,
  "Heads-up Preflop": heads_up_preflop}
