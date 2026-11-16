from dataclasses import replace
from random import Random

from pokerbots_sdk import Observation, load_strategy, validate_decision
from pokerbots_sdk.model import LineAction
from river_experiment import LINE_FIXTURES, cards, fixture_decisions


def test_hive_does_not_reraise_top_pair_under_turn_pressure():
  view = Observation(
    hole=cards("Ad Qc"), board=cards("7d Jd 6c Ah"), stack=6167,
    stacks=((0, 6167), (1, 1656)), current_bet=2945, table_bet=8042,
    big_blind=100, pot=12177, late_position=True, opponents=1,
    legal={"call": True, "fold": True, "raise": True, "check": False, "all_in": True,
      "call_amount": 5097, "min_raise_total": 13139, "max_raise_total": 9112},
    effective_raise_total=9112, has_all_in_opponent=False,
    betting_line=(
      LineAction(False, "preflop", "raise", 244, 150),
      LineAction(True, "preflop", "call", 144, 344),
      LineAction(True, "flop", "raise", 351, 488),
      LineAction(False, "flop", "call", 351, 839),
      LineAction(True, "turn", "raise", 856, 1190),
      LineAction(False, "turn", "raise", 2945, 2046),
      LineAction(True, "turn", "raise", 8042, 4991),
    ))
  diagnostics = {}
  action, target = load_strategy("Hive Mind")(view, Random(0), diagnostics=diagnostics)
  validate_decision(view, action, target)
  assert action in {"call", "fold"}
  assert diagnostics["raise_pressure"]
  assert diagnostics["pot_odds"] == 5097 / 17274


def test_hive_checks_medium_value_river_bets_and_keeps_flush_value():
  fixtures = fixture_decisions(LINE_FIXTURES, strategies=("Hive Mind",))
  by_id = {(fixture["opponent"], fixture["hand"]): fixture["decisions"]["Hive Mind"] for fixture in fixtures}
  assert by_id[("Plodder8", 26)]["action"] == "check"
  assert by_id[("pebble", 87)]["action"] == "raise"


def test_hive_catches_turn_overbet_after_small_flop_bet():
  view = Observation(
    hole=cards("8c 2s"), board=cards("8d Ts 7h Kh"), stack=5000,
    stacks=((0, 5000), (1, 6500)), current_bet=0, table_bet=600,
    big_blind=100, pot=1000, late_position=True, opponents=1,
    legal={"call": True, "fold": True, "raise": True, "check": False, "all_in": True,
      "call_amount": 600, "min_raise_total": 1200, "max_raise_total": 5000},
    effective_raise_total=5000, has_all_in_opponent=False,
    betting_line=(
      LineAction(False, "preflop", "call", 50, 150),
      LineAction(True, "flop", "raise", 100, 200),
      LineAction(False, "flop", "call", 100, 300),
      LineAction(True, "turn", "raise", 600, 400),
    ))
  for seed in (0, 7, 12, 19):
    diagnostics = {}
    action, target = load_strategy("Hive Mind")(view, Random(seed), diagnostics=diagnostics)
    validate_decision(view, action, target)
    assert action == "call"
    assert diagnostics["pot_odds"] == .375


def test_experimental_barrel_sizes_value_and_selected_draws_after_small_flop_bet():
  experimental = load_strategy("pokerbots_sdk.hive_policy:turn_barrel_experiment")
  flop_bet = LineAction(False, "flop", "raise", 100, 300)
  flop_call = LineAction(True, "flop", "call", 100, 400)
  view = Observation(
    hole=cards("Jc Tc"), board=cards("9c 6c 2d Kh"), stack=9750,
    stacks=((0, 9750), (1, 9750)), current_bet=0, table_bet=0,
    big_blind=100, pot=500, late_position=True, opponents=1,
    legal={"check": True, "call": False, "fold": False, "raise": True,
      "call_amount": 0, "min_raise_total": 100, "max_raise_total": 9750},
    effective_raise_total=9750, has_all_in_opponent=False,
    betting_line=(flop_bet, flop_call))
  flop = replace(view, hole=cards("Ac Ah"), board=cards("As 7d 2c"), pot=300, betting_line=())
  turn_value = replace(view, hole=cards("Qc Kc"), board=cards("8c 9c Tc Jd"))
  for spot, target, kind in ((flop, 100, "Flop value"), (view, 750, "Turn semi-bluff"),
                            (turn_value, 750, "Turn value")):
    diagnostics = {}
    action, amount = experimental(spot, Random(0), diagnostics=diagnostics)
    validate_decision(spot, action, amount)
    assert (action, amount) == ("raise", target)
    assert diagnostics["decision_basis"] == kind

  for spot in (replace(view, betting_line=()), replace(view, hole=cards("Qd Js")),
               replace(view, effective_raise_total=400)):
    diagnostics = {}
    action, amount = experimental(spot, Random(0), diagnostics=diagnostics)
    validate_decision(spot, action, amount)
    assert not diagnostics.get("experimental_bet")


def test_value_pressure_sizes_a_full_house_and_preserves_the_control_action():
  control = load_strategy("Hive Mind")
  candidate = load_strategy("pokerbots_sdk.hive_policy:value_pressure_experiment")
  view = Observation(
    hole=cards("Ac Ah"), board=cards("As 7d 2c 7h 2d"), stack=9500,
    stacks=((0, 9500), (1, 9500)), current_bet=0, table_bet=0,
    big_blind=100, pot=1000, late_position=True, opponents=1,
    legal={"check": True, "call": False, "fold": False, "raise": True,
      "call_amount": 0, "min_raise_total": 100, "max_raise_total": 9500},
    effective_raise_total=9500, has_all_in_opponent=False)
  details = {}
  change = candidate(view, Random(0), diagnostics=details)
  validate_decision(view, *change)
  assert change == ("raise", 1500)
  assert details["baseline_value_action"] == control(view, Random(0)) == ("raise", 720)

  for spot in (replace(view, hole=cards("Jc 3h")), replace(view, effective_raise_total=600)):
    action = candidate(spot, Random(0))
    validate_decision(spot, *action)
    assert action == control(spot, Random(0))

  river_candidate = load_strategy("pokerbots_sdk.hive_policy:river_value_pressure")
  called = replace(view, betting_line=(LineAction(True, "flop", "call", 100, 400),))
  aggressive = replace(called, betting_line=called.betting_line +
    (LineAction(True, "turn", "raise", 150, 600),))
  assert river_candidate(called, Random(0)) == ("raise", 1500)
  for spot in (view, aggressive):
    assert river_candidate(spot, Random(0)) == control(spot, Random(0))
