"""Opponent-conditioned river sizing for heads-up no-limit Hold'em."""

from .betting_line import evaluate_range
from .equity_policy import _sized_raise
from .hive_policy import adaptive_river_value_pressure, hive_mind
from .strategies import VALUE_PROFILE


TITLE = "Ashwing Adaptive"


def wager_ev(outcomes, pot, amount, call_rate):
  """Evaluate a river wager with fold, call, and raise branches.

  The weighted mean of the per-combo call probabilities matches the given
  call rate. Stronger holdings are more likely to continue or raise.
  A fold to a raise supplies a conservative branch value.
  """
  total = sum(weight for _, _, weight in outcomes)
  mean_strength = sum(item.strength * weight for item, _, weight in outcomes) / total
  slope = min(call_rate, 1 - call_rate)
  ev = 0.
  for item, share, weight in outcomes:
    call = call_rate + slope * (item.strength - mean_strength)
    raise_back = .18 * (1 - call) * item.strength ** 4
    fold = 1 - call - raise_back
    ev += weight * (fold * pot + call * (share * (pot + 2 * amount) - amount) - raise_back * amount)
  return ev / total


def ashwing_adaptive(view, rng, *, history=None, diagnostics=None):
  """Escalate river value sizing once public responses support it."""
  if history is None or len(view.stacks) != 2 or len(view.board) != 5 or not view.legal["check"]:
    return hive_mind(view, rng, diagnostics=diagnostics)

  baseline = adaptive_river_value_pressure(view, rng, history)
  if not view.legal["raise"] or view.pot <= 0 or not history.allows(view.pot, view.pot):
    return baseline

  _, equity, outcomes = evaluate_range(view, rng, 0)  # Exact on the river.
  if equity < .74:
    return baseline

  baseline_amount = baseline[1] - view.current_bet if baseline[0] == "raise" else 0
  best, best_edge = baseline, .02 * view.pot
  def call_estimate(size, shift):
    rate, _ = history.estimate(size, view.pot)
    # Extrapolate conservatively when our candidate exceeds the usual size.
    premium = .20 * max(0., size / view.pot - VALUE_PROFILE.pot_fraction)
    return min(.99, max(.01, rate - premium + shift))

  shifts = (-.12, 0., .12)
  control = [wager_ev(outcomes, view.pot, baseline_amount, call_estimate(baseline_amount, shift))
    if baseline_amount else equity * view.pot for shift in shifts]
  options = {}
  for fraction in (VALUE_PROFILE.pot_fraction, 1.0, 1.5):
    sized = _sized_raise(view, max(1, int(view.pot * fraction)))
    if sized is None:
      continue
    amount = sized[1] - view.current_bet
    if amount <= baseline_amount or amount > int(view.pot * fraction) or amount in options:
      continue
    if not history.allows(amount, view.pot):
      continue

    edges = [wager_ev(outcomes, view.pot, amount, call_estimate(amount, shift)) - ev
      for shift, ev in zip(shifts, control, strict=True)]
    options[amount] = min(edges)
    if options[amount] > best_edge:
      best, best_edge = sized, options[amount]
  if diagnostics is not None:
    diagnostics.update(method=TITLE, equity=equity, baseline=baseline, conservative_edges_chips=options)
  return best
