from itertools import combinations

from poker_engine import compare, highest_hand

RANK_LABELS = {"A": "ace", "K": "king", "Q": "queen", "J": "jack"}
KICKER_START = {"Pair": 1, "2 Pair": 2, "3 of a kind": 1, "4 of a kind": 1}


def best_five(board, hole_cards, score):
  # Board-first order prefers playing the board when it already makes the same hand.
  return next(cards for cards in combinations([*board, *hole_cards], 5)
    if highest_hand(cards) == score)


def pot_explanation(pot, hands):
  winners = pot["winners"]
  if len(winners) > 1:
    return "Split pot · the winning five-card hands tie."
  if len(pot["eligible"]) == 1:
    return "Only one player was eligible for this pot."
  winner = winners[0]
  runners_up = {pid: hands[pid] for pid in pot["eligible"] if pid != winner}
  runner_up = compare(runners_up)[0]
  category, ranks = hands[winner]
  other_category, other_ranks = hands[runner_up]
  if category != other_category:
    return f"{category} beats {other_category.lower()}."
  index = next(i for i, (left, right) in enumerate(zip(ranks, other_ranks)) if left != right)
  high = RANK_LABELS.get(ranks[index], ranks[index])
  low = RANK_LABELS.get(other_ranks[index], other_ranks[index])
  if category in KICKER_START and index >= KICKER_START[category]:
    return f"The {high} kicker beats the {low} kicker."
  if category in {"Straight", "Straight Flush"}:
    return f"The {high}-high hand beats the {low}-high hand."
  return f"{category} · {high.capitalize()} beats {low} at the first differing rank."
