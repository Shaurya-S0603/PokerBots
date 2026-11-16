"""Hold’em ensemble with heads-up range inference and multiway equity."""

from .betting_line import evaluate_range, holding, opening_bet_values
from .equity_policy import EQUITY_TRIALS_SMALL_TABLE, _sized_raise, equity_bot
from .strategies import VALUE_PROFILE, value


def hive_mind(view, rng, *, diagnostics=None, bluff_catching=True, turn_barrel=False,
    value_streets=()):
  """Blend equity models and gate aggression on the range that continues."""
  if view.opponents > 1:
    return equity_bot(view, rng, profile=VALUE_PROFILE, arena_opening=True, diagnostics=diagnostics)
  if not view.board:
    return value(view, rng, diagnostics=diagnostics)

  legal = view.legal
  call = legal["call_amount"]
  river = len(view.board) == 5
  street = {3: "flop", 4: "turn", 5: "river"}[len(view.board)]
  pot = view.pot - max(0, view.table_bet - view.current_bet - call)
  current_raises = sum(
    step.street == street and step.action == "raise" for step in view.betting_line
  )
  pressure = call > 0 and (current_raises >= 2 or call * 3 >= pot)
  trials = EQUITY_TRIALS_SMALL_TABLE
  if bluff_catching and street == "turn" and pressure:
    trials *= 4
  result, weighted, outcomes = evaluate_range(view, rng, trials, polarize_turn=bluff_catching)
  made = holding(view.hole, view.board)
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
  experimental = _barrel_size(view, street, small_raise) if turn_barrel else None
  sizes = sorted({action[1] - view.current_bet for action in
    (small_raise, opening_raise, experimental) if action})
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
    if (bet["amount"] <= opening_raise[1] - view.current_bet
        and made.strength >= .45 and continuing_wins > continuing_losses
        and bet["ev_chips"] > check["ev_chips"] + margin):
      eligible.append(bet)

  if diagnostics is not None:
    diagnostics.update(decision_basis="Value against the calling range", bet_options=options)
  if street in value_streets:
    robust = robust_value_bet(view, made, weighted, outcomes, eligible, opening_raise)
    if robust is not None:
      if diagnostics is not None:
        diagnostics.update(decision_basis="Value sizing across response models",
          baseline_value_action=regular_value_action(view, eligible))
      return robust
  if experimental:
    option = next(bet for bet in bets if bet["amount"] == experimental[1] - view.current_bet)
    kind = _barrel_kind(street, made, weighted, pot, check, eligible, option)
    if kind == "value" or (kind == "semi-bluff" and rng.random() < .50):
      if diagnostics is not None:
        diagnostics.update(decision_basis=f"{street.title()} {kind}", experimental_bet=True)
      return experimental
  return regular_value_action(view, eligible)


def regular_value_action(view, eligible):
  if not eligible:
    return "check", None
  best = max(eligible, key=lambda option: option["ev_chips"])
  return "raise", view.current_bet + best["amount"]


def robust_value_bet(view, made, equity, outcomes, eligible, opening_raise):
  if made.strength < .69 or equity < .75:
    return None
  baseline = max(eligible, key=lambda row: row["ev_chips"])["amount"] if eligible else 0
  amounts = {baseline, opening_raise[1] - view.current_bet}
  for chips in (view.pot, view.pot * 3 // 2):
    sized = _sized_raise(view, chips)
    if sized:
      amounts.add(sized[1] - view.current_bet)
  total = sum(weight for _, _, weight in outcomes)
  # Reuse the same sampled runouts for each action and each response model.
  # A larger size must beat the normal action across tighter and looser
  # estimates of how often the opponent continues.
  def returns(amount):
    if amount == 0:
      payout = sum(weight * share for _, share, weight in outcomes) * view.pot / total
      return (payout, payout, payout)
    price = amount / (view.pot + 2 * amount)
    totals = [0., 0., 0.]
    for item, share, weight in outcomes:
      strength = item.strength + .19 * item.draw
      called = share * (view.pot + 2 * amount) - amount
      for index, shift in enumerate((-.12, 0., .18)):
        continues = max(.04, min(.98, .5 + 2.3 * (strength - (.30 + 1.5 * price)) + shift))
        totals[index] += weight * (view.pot + continues * (called - view.pot))
    return tuple(value / total for value in totals)

  control = returns(baseline)
  best = None
  best_edge = .025 * view.pot
  for amount in sorted(amounts):
    if amount <= baseline:
      continue
    edge = min(after - before for after, before in zip(returns(amount), control, strict=True))
    if edge > best_edge:
      best, best_edge = amount, edge
  return ("raise", view.current_bet + best) if best is not None else None


def value_pressure_experiment(view, rng, *, diagnostics=None):
  """Try larger postflop value bets on top of Hive Mind."""
  return hive_mind(view, rng, diagnostics=diagnostics, value_streets=("turn", "river"))


def river_value_pressure(view, rng, *, diagnostics=None):
  """Try larger river value bets after a passive caller reaches the river."""
  postflop = {step.action for step in view.betting_line
    if len(view.board) == 5 and step.opponent and step.street != "preflop"}
  streets = ("river",) if "call" in postflop and "raise" not in postflop else ()
  return hive_mind(view, rng, diagnostics=diagnostics, value_streets=streets)


def adaptive_river_value_pressure(view, rng, history):
  """Use the larger size when prior public responses support it."""
  if len(view.stacks) != 2 or len(view.board) != 5 or not view.legal["check"]:
    return hive_mind(view, rng)
  details = {}
  action = river_value_pressure(view, rng, diagnostics=details)
  baseline = details.get("baseline_value_action")
  if baseline is not None and not history.allows(action[1] - view.current_bet, view.pot):
    return baseline
  return action


def _barrel_size(view, street, small_raise):
  if street == "flop":
    if (small_raise and (small_raise[1] - view.current_bet) * 2 <= view.pot
        and view.effective_raise_total - view.current_bet >= 3 * view.pot):
      return small_raise
  if street == "turn":
    flop = [step for step in view.betting_line if step.street == "flop"]
    if (len(flop) == 2 and not flop[0].opponent and flop[0].action == "raise"
        and flop[0].amount * 2 <= flop[0].pot_before and flop[1].opponent
        and flop[1].action == "call"):
      large = _sized_raise(view, view.pot * 3 // 2)
      if large and (large[1] - view.current_bet) * 4 >= view.pot * 5:
        return large
  return None


def _barrel_kind(street, made, equity, pot, check, eligible, option):
  best = max((bet["ev_chips"] for bet in eligible), default=check["ev_chips"])
  edge = option["ev_chips"] - best
  if option["worse_call_mass"] > option["better_call_mass"]:
    if (street == "flop" and made.strength >= .69 and option["ev_chips"] > check["ev_chips"] + .035 * pot
        and edge >= -.03 * pot):
      return "value"
    if street == "turn" and made.strength >= .69 and equity >= .72 and edge > .05 * pot:
      return "value"
  if (made.draw and made.strength < .45 and .20 <= equity <= .50
      and option["better_fold_mass"] >= (.18 if street == "flop" else .27)
      and edge > (.06 if street == "flop" else .10) * pot):
    return "semi-bluff"
  return None


def turn_barrel_experiment(view, rng, *, diagnostics=None):
  """Run the offensive experiment against the original Hive Mind defense."""
  return hive_mind(view, rng, diagnostics=diagnostics, bluff_catching=False, turn_barrel=True)
