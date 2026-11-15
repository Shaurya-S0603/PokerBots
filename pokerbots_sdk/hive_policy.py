"""Heads-up ensemble using public betting history and shared equity samples."""

from .betting_line import evaluate_range, holding, opening_bet_values
from .equity_policy import EQUITY_TRIALS_SMALL_TABLE, _sized_raise
from .strategies import VALUE_PROFILE, value


def hive_mind(view, rng, *, diagnostics=None):
  """Blend equity models and gate aggression on the range that continues."""
  if view.opponents != 1 or not view.board:
    return value(view, rng, diagnostics=diagnostics)

  legal = view.legal
  call = legal["call_amount"]
  river = len(view.board) == 5
  street = {3: "flop", 4: "turn", 5: "river"}[len(view.board)]
  pot = view.pot - max(0, view.table_bet - view.current_bet - call)
  result, weighted, outcomes = evaluate_range(view, rng, EQUITY_TRIALS_SMALL_TABLE)
  made = holding(view.hole, view.board)
  current_raises = sum(
    step.street == street and step.action == "raise" for step in view.betting_line
  )
  pressure = call > 0 and (current_raises >= 2 or call * 3 >= pot)
  disagreement = abs(result.equity - weighted)
  equity = (.10 if pressure else .25) * (result.equity - weighted) + weighted
  if pressure and disagreement >= .12:
    equity = min(equity, weighted)

  opening_raise = _sized_raise(view, max(view.big_blind,
    int((pot + call) * VALUE_PROFILE.pot_fraction)))
  if diagnostics is not None:
    diagnostics.update(method="Hive Mind", equity=result.equity, weighted_equity=weighted,
      blended_equity=equity, model_disagreement=disagreement, raise_pressure=pressure)

  if call and legal["call"]:
    terminal = river or view.has_all_in_opponent or call == view.stack
    odds = call / (pot + call)
    call_ev = equity * (pot + call) - call
    realization_margin = 0 if terminal else pot * (.02 if pressure else .01)
    if diagnostics is not None:
      diagnostics.update(pot_odds=odds, modeled_call_ev_bb=call_ev / view.big_blind,
        decision_basis="Range-weighted call price")
    if legal["fold"] and call_ev <= realization_margin:
      return "fold", None

    # A raise after sustained pressure commits chips against a stronger range.
    # With high disagreement, preserve the call when it clears its price.
    threshold = .82 if pressure else .72
    if (opening_raise and disagreement < .12 and made.strength >= .74
        and min(equity, weighted) >= threshold):
      return opening_raise
    return "call", None

  if not legal["check"]:
    return value(view, rng, diagnostics=diagnostics)
  if not opening_raise:
    return "check", None

  small_raise = _sized_raise(view, max(view.big_blind, pot // 3))
  sizes = sorted({action[1] - view.current_bet for action in (small_raise, opening_raise) if action})
  options = opening_bet_values(view, outcomes, sizes)
  check, *bets = options
  eligible = []
  for bet in bets:
    amount = bet["amount"]
    continuing_wins = bet["worse_call_mass"]
    continuing_losses = bet["better_call_mass"]
    # Low SPR makes even a small absolute bet consequential. Demand extra
    # modeled edge when committing a large share of the effective stack.
    effective = view.effective_raise_total - view.current_bet
    commits_stack = effective <= pot * 1.5 and amount * 2 >= effective
    margin = pot * (.07 if commits_stack or disagreement >= .12 else .035)
    if (made.strength >= .45 and continuing_wins > continuing_losses
        and bet["ev_chips"] > check["ev_chips"] + margin):
      eligible.append(bet)

  if diagnostics is not None:
    diagnostics.update(decision_basis="Value against the calling range", bet_options=options)
  if not eligible:
    return "check", None
  best = max(eligible, key=lambda option: option["ev_chips"])
  return "raise", view.current_bet + best["amount"]
