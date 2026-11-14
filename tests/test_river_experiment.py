import pytest

from equity import exact_river_equity, river_range_equities
from river_experiment import cards, fixture_decisions


def test_weighted_enumeration_preserves_uniform_result_and_board_ties():
  hole = cards("Ks 7s")
  board = cards("9c 6h Ac 8h 4c")
  uniform, weighted = river_range_equities(hole, board, 1, .25)
  assert uniform == exact_river_equity(hole, board)
  assert 0 < weighted < uniform.equity
  uniform, weighted = river_range_equities(hole, board, 1, 1)
  assert weighted == pytest.approx(uniform.equity)
  board = cards("Ah Kh Qh Jh Th")
  assert river_range_equities(hole, board, 1, .25)[1] == pytest.approx(.5)


def test_weighted_river_changes_calls_and_preserves_raises():
  fixtures = {(row["opponent"], row["hand"]): row["decisions"] for row in fixture_decisions()}
  weak_call = fixtures["Plodder8", 2]
  assert weak_call["Value"]["action"] == "call"
  weighted = weak_call["Weighted River"]
  assert weighted["action"] == "fold"
  assert weighted["weighted_equity"] < weighted["pot_odds"] < weighted["uniform_equity"]
  for key in [("pebble", 87), ("Plodder8", 26)]:
    decisions = fixtures[key]
    assert decisions["Weighted River"]["action"] == decisions["Value"]["action"] == "raise"
    assert decisions["Weighted River"]["raise_to"] == decisions["Value"]["raise_to"]
  assert fixtures["PluriBot", 9]["Weighted River"] == fixtures["PluriBot", 9]["Value"]
