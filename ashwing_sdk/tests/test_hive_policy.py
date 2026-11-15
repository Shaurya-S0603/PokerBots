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
