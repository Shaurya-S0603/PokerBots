"""Evaluate heads-up river challengers on replay fixtures and fresh paired seeds."""

import argparse
import json
from pathlib import Path
from random import Random


from baseline_v4 import _has_draw, _postflop, _preflop
from benchmark import Config, _interval, play_pair, summarize
from pokerbots_sdk import Observation, TOOLKIT_STRATEGIES, validate_decision
from pokerbots_sdk.equity_policy import _sized_raise
from pokerbots_sdk.model import LineAction, OpponentBet

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "benchmarks" / "chipzen-river-fixtures.json"
REPORT = ROOT / "benchmarks" / "river-experiment.json"
STRATEGIES = ("Value", "Pot Guard", "Weighted River")
PROFILES = ("Aggressive barreling", "Frequent overbetting", "Passive folding")
LINE_REPORT = ROOT / "benchmarks" / "betting-line-experiment.json"
LINE_FIXTURES = ROOT / "benchmarks" / "chipzen-betting-line-fixtures.json"
LINE_STRATEGIES = ("Value", "Weighted River", "Line Range", "Range + Sizing", "Heads-up Preflop")


def opponent_policy(profile):
  def decide(view, rng):
    legal = view.legal
    street = len(view.board)
    strength = _postflop(view) if street else _preflop(view, loose=True)
    if profile == "Passive folding":
      if legal["check"]:
        return "check", None
      if strength == "strong" or (strength == "medium" and legal["call_amount"] * 4 <= view.pot):
        return "call", None
      return "fold", None

    draw = street in {3, 4} and _has_draw(view)
    if not street:
      frequency = 1 if strength == "strong" else (0.65 if view.late_position else 0.20)
      fraction = 1.1 if profile == "Frequent overbetting" else .75
    elif profile in {"Aggressive barreling", "Bluff-heavy barreling"}:
      frequency = {"strong": .95, "medium": .52, "weak": .62 if profile == "Bluff-heavy barreling" else .22}[strength]
      frequency = max(frequency, .72) if draw else frequency
      fraction = .70
    else:
      frequency = {"strong": .95, "medium": .22, "weak": .18}[strength]
      frequency = max(frequency, .55) if draw else frequency
      fraction = 1.5

    if legal["raise"] and (legal["check"] or view.table_bet == view.big_blind and not street
        or strength == "strong") and rng.random() < frequency:
      raise_action = _sized_raise(view, max(view.big_blind, int(view.pot * fraction)))
      if raise_action:
        return raise_action
    if legal["check"]:
      return "check", None
    call = legal["call_amount"]
    if strength == "strong" or (strength == "medium" and call <= view.pot / 2) or (
        draw and call <= view.pot / 3) or (not street and call <= view.big_blind):
      return "call", None
    return "fold", None
  return decide


def cards(raw):
  suits = {"c": "♣️", "d": "♦️", "h": "♥️", "s": "♠️"}
  return tuple(("10" if card[0] == "T" else card[0], suits[card[1]]) for card in raw.split())


def fixture_decisions(path=FIXTURES, strategies=STRATEGIES):
  results = []
  for fixture in json.loads(path.read_text()):
    stack, opposing_stack = fixture["stacks"]
    current = fixture["current_bet"]
    call = fixture["call"]
    table = current + call
    maximum = current + stack
    effective = min(maximum, table + opposing_stack)
    view = Observation(
      hole=cards(fixture["hole"]), board=cards(fixture["board"]), stack=stack,
      stacks=((1, stack), (2, opposing_stack)), current_bet=current, table_bet=table,
      big_blind=fixture["big_blind"], pot=fixture["pot"], late_position=fixture["button"],
      opponents=1, effective_raise_total=effective, has_all_in_opponent=opposing_stack == 0,
      opponent_bets=tuple(OpponentBet(*bet) for bet in fixture["opponent_bets"]),
      betting_line=tuple(LineAction(*step) for step in fixture.get("betting_line", ())),
      legal={"call": bool(call), "call_amount": min(call, stack), "fold": True, "check": not call,
        "raise": bool(opposing_stack and maximum > table),
        "min_raise_total": table + fixture["min_increment"], "max_raise_total": maximum})
    decisions = {}
    for name in strategies:
      diagnostics = {}
      action, target = TOOLKIT_STRATEGIES[name](view, Random(0), diagnostics=diagnostics)
      validate_decision(view, action, target)
      decisions[name] = {"action": action, "raise_to": target, "pot_odds": diagnostics.get("pot_odds"),
        "bet_options": diagnostics.get("bet_options"),
        "uniform_equity": diagnostics.get("equity"), "weighted_equity": diagnostics.get("weighted_equity"),
        "call_threshold": diagnostics.get("call_threshold"), "basis": diagnostics.get("decision_basis")}
    results.append({**fixture, "decisions": decisions})
  return results


def call_losses(records):
  results = {street: {"calls": 0, "calls_on_lost_hands": 0, "chips_paid_on_lost_hands": 0}
    for street in ("turn", "river")}
  for pair in records:
    for hand in pair["hands"]:
      for street, amount in hand["large_calls"]:
        row = results[street]
        row["calls"] += 1
        if hand["lost_pot"]:
          row["calls_on_lost_hands"] += 1
          row["chips_paid_on_lost_hands"] += amount
  return results


def position_metrics(records, big_blind):
  button, blind = zip(*(pair["hands"] for pair in records))
  faced = sum(hand["faced_limp_raise"] for hand in button)
  return {
    "button_limp_rate": sum(hand["button_limp"] for hand in button) / len(button),
    "button_open_raise_rate": sum(hand["button_open"] for hand in button) / len(button),
    "faced_raise_after_limp": faced,
    "fold_after_limp_raise_rate": sum(hand["folded_after_limp_raise"] for hand in button) / faced if faced else None,
    "button_bb_per_100": sum(hand["net_chips"] for hand in button) * 100 / (len(button) * big_blind),
    "big_blind_bb_per_100": sum(hand["net_chips"] for hand in blind) * 100 / (len(blind) * big_blind),
  }


def evaluate(start, pairs, bootstrap, output, *, strategies=STRATEGIES, profiles=PROFILES,
    fixture_path=FIXTURES, stack=1000):
  config = Config(stack=stack)
  rows = []
  for profile in profiles:
    opponent = opponent_policy(profile)
    control_totals = previous_totals = None
    for name in strategies:
      print(f"{profile} · {name}", flush=True)
      records, times = [], []
      for seed in range(start, start + pairs):
        record, elapsed = play_pair(seed, profile, config, candidate=TOOLKIT_STRATEGIES[name],
          opponent_policy=opponent, track_calls=True)
        records.append(record)
        times.extend(elapsed)
      report = summarize(records, times, config.big_blind, bootstrap, 1738)
      if report["illegal_actions"]:
        raise RuntimeError(f"{profile} · {name} produced an illegal action")
      totals = [sum(hand["net_chips"] for hand in pair["hands"]) for pair in records]
      if control_totals is None:
        control_totals = totals
      deltas = [test - control for test, control in zip(totals, control_totals)]
      change = [test - control for test, control in zip(totals, previous_totals or totals)]
      previous_totals = totals
      rows.append({"opponent": profile, "strategy": name, **report, "large_call_losses": call_losses(records),
        "position": position_metrics(records, config.big_blind),
        "delta_vs_previous": sum(change) * 100 / (2 * pairs * config.big_blind),
        "delta_previous_interval_95": _interval(change, config.big_blind, bootstrap, 1738),
        "delta_vs_value": sum(deltas) * 100 / (2 * pairs * config.big_blind),
        "delta_interval_95": _interval(deltas, config.big_blind, bootstrap, 1738)})
  data = {"config": {"seed_start": start, "pairs_per_opponent": pairs, "stack": config.stack,
    "small_blind": config.small_blind, "big_blind": config.big_blind, "bootstrap_samples": bootstrap},
    "results": rows, "fixtures": fixture_decisions(fixture_path, strategies)}
  output.write_text(json.dumps(data, indent=2) + "\n")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--seed-start", type=int, default=84000)
  parser.add_argument("--pairs", type=int, default=400)
  parser.add_argument("--bootstrap", type=int, default=3000)
  parser.add_argument("--output", type=Path)
  parser.add_argument("--stack", type=int, default=1000)
  parser.add_argument("--betting-line", action="store_true")
  args = parser.parse_args()
  if args.seed_start < 0 or args.pairs < 2 or args.bootstrap < 2:
    parser.error("Use a nonnegative seed start, at least two pairs and at least two bootstrap samples")
  if args.betting_line:
    evaluate(args.seed_start, args.pairs, args.bootstrap, args.output or LINE_REPORT,
      strategies=LINE_STRATEGIES, profiles=(*PROFILES, "Bluff-heavy barreling"),
      fixture_path=LINE_FIXTURES, stack=args.stack)
  else:
    evaluate(args.seed_start, args.pairs, args.bootstrap, args.output or REPORT, stack=args.stack)


if __name__ == "__main__":
  main()
