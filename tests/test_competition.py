from random import Random

from equity import DECK
from fast_rank import rank_hand
from poker_engine import compare, highest_hand


def test_fast_evaluator_preserves_shared_board_winners():
  rng = Random(11)
  for _ in range(1000):
    cards = rng.sample(DECK, 9)
    board = cards[:5]
    hands = [board + cards[5:7], board + cards[7:]]
    ranked = [rank_hand(hand) for hand in hands]
    assert [i for i, score in enumerate(ranked) if score == max(ranked)] == compare(
      {i: highest_hand(hand) for i, hand in enumerate(hands)})


def test_fast_evaluator_handles_wheels_and_double_trips():
  wheel = [("A", "♥️"), ("2", "♣️"), ("3", "♥️"), ("4", "♦️"), ("5", "♠️"),
    ("Q", "♠️"), ("K", "♦️")]
  assert rank_hand(wheel) == (4, 5)
  assert rank_hand([("A", suit) for suit in ("♥️", "♠️", "♣️")]
    + [("K", suit) for suit in ("♥️", "♠️", "♣️")] + [("2", "♦️")]) == (6, 14, 13)
