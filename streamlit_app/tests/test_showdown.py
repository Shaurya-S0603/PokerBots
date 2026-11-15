from poker_engine import highest_hand
from ui.showdown import best_five, pot_explanation


def test_best_five_plays_board_on_a_tie():
  board = [("A", "♥️"), ("K", "♥️"), ("Q", "♥️"), ("J", "♥️"), ("10", "♥️")]
  hole = [("A", "♣️"), ("A", "♠️")]
  assert best_five(board, hole, highest_hand(board + hole)) == tuple(board)


def test_pot_explanation_uses_only_eligible_hands_for_the_kicker():
  hands = {
    1: ("Pair", ["A", "K", "9", "7"]),
    2: ("Pair", ["A", "Q", "9", "7"]),
    3: ("Full House", ["K", "9"]),
  }
  assert pot_explanation({"eligible": [1, 2], "winners": [1]}, hands) == "The king kicker beats the queen kicker."
