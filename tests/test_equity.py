import pytest

from equity import exact_river_equity


@pytest.mark.parametrize("hole,board,counts", [
  ([("A", "♥️"), ("K", "♥️")], [("Q", "♥️"), ("J", "♥️"), ("10", "♥️"), ("2", "♣️"), ("3", "♦️")], (990, 0, 0)),
  ([("2", "♣️"), ("3", "♦️")], [("A", "♥️"), ("K", "♥️"), ("Q", "♥️"), ("J", "♥️"), ("10", "♥️")], (0, 990, 0)),
  ([("K", "♣️"), ("Q", "♦️")], [("A", "♣️"), ("A", "♦️"), ("A", "♥️"), ("A", "♠️"), ("2", "♣️")], (861, 129, 0)),
  ([("Q", "♣️"), ("J", "♦️")], [("A", "♥️"), ("K", "♥️"), ("Q", "♥️"), ("J", "♥️"), ("2", "♠️")], None),
])
def test_exact_river_fixtures(hole, board, counts):
  result = exact_river_equity(hole, board)
  assert result.wins + result.ties + result.losses == 990
  assert result.equity == pytest.approx((result.wins + result.ties / 2) / 990)
  if counts is None:
    assert result.losses > 0
    assert result.equity < 1
  else:
    assert (result.wins, result.ties, result.losses) == counts


def test_river_rejects_duplicate_and_invalid_cards():
  board = [("A", "♣️"), ("A", "♦️"), ("A", "♥️"), ("A", "♠️"), ("2", "♣️")]
  with pytest.raises(ValueError, match="distinct"):
    exact_river_equity([board[0], ("Q", "♦️")], board)
  with pytest.raises(ValueError, match="deck"):
    exact_river_equity([("1", "♣️"), ("Q", "♦️")], board)


def test_sampling_tracks_the_exact_reference_and_is_seeded():
  from random import Random

  from equity import sample_equity

  hole = [("K", "♣️"), ("Q", "♦️")]
  board = [("A", "♣️"), ("A", "♦️"), ("A", "♥️"), ("A", "♠️"), ("2", "♣️")]
  sampled = sample_equity(hole, board, 1, 2000, Random(23))
  assert sampled == sample_equity(hole, board, 1, 2000, Random(23))
  assert sampled.equity == pytest.approx(exact_river_equity(hole, board).equity, abs=0.015)
  royal = [("A", "♥️"), ("K", "♥️"), ("Q", "♥️"), ("J", "♥️"), ("10", "♥️")]
  split = sample_equity([("2", "♣️"), ("3", "♦️")], royal, 3, 64, Random(1))
  assert (split.wins, split.ties, split.losses, split.equity) == (0, 64, 0, 0.25)
