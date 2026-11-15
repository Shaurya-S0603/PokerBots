"""Frozen Update 4 benchmark strategies."""

from collections import Counter

from poker_engine import highest_hand


def calling_station(view, rng):
  if view.legal["check"]:
    return "check", None
  if view.legal["call"]:
    return "call", None
  raise ValueError("Calling Station requires a legal check or call")


def _min_raise(view):
  return "raise", min(view.legal["min_raise_total"], view.legal["max_raise_total"])


def random_bot(view, rng):
  actions = [action for action in ("check", "call", "fold", "raise", "all_in")
    if view.legal[action]]
  action = rng.choice(actions)
  return _min_raise(view) if action == "raise" else (action, None)


RANKS = {rank: value for value, rank in enumerate("2 3 4 5 6 7 8 9 10 J Q K A".split(), 2)}


def _preflop(view, loose):
  high, low = sorted((RANKS[rank] for rank, _ in view.hole), reverse=True)
  suited = view.hole[0][1] == view.hole[1][1]
  if high == low >= 10 or (high == 14 and (low >= 12 or (low == 11 and suited))):
    return "strong"
  if loose and view.late_position and view.table_bet == view.big_blind:
    if (high == low and high >= 6) or (suited and (high == 14 or (low >= 6 and high - low == 1))):
      return "strong"
  return "weak"


def _postflop(view):
  category, score = highest_hand(list(view.hole + view.board))
  if len(view.board) == 5 and highest_hand(list(view.board)) == (category, score):
    return "weak"
  counts = Counter(rank for rank, _ in view.board)
  hole_ranks = {rank for rank, _ in view.hole}
  if category == "High Card":
    return "weak"
  if category == "Pair":
    return "medium" if score[0] in hole_ranks else "weak"
  if category in ("2 Pair", "3 of a kind", "4 of a kind"):
    required = {"2 Pair": (2, 2), "3 of a kind": (3,), "4 of a kind": (4,)}[category]
    return "strong" if any(counts[rank] < size for rank, size in zip(score, required)) else "medium"
  return "strong"


def _has_draw(view):
  cards = view.hole + view.board
  suits = Counter(suit for _, suit in cards)
  if any(suits[suit] == 4 for _, suit in view.hole):
    return True
  board_ranks = {RANKS[rank] for rank, _ in view.board}
  all_ranks = {RANKS[rank] for rank, _ in cards}
  for low in range(1, 11):
    window = {14, 2, 3, 4, 5} if low == 1 else set(range(low, low + 5))
    if len(window & all_ranks) == 4 and window & (all_ranks - board_ranks):
      return True
  return False


def _value_strategy(view, rng, loose):
  strength = _postflop(view) if view.board else _preflop(view, loose)
  can_raise = view.legal["raise"]
  if strength == "strong" and can_raise:
    return _min_raise(view)
  if loose and can_raise and view.board and view.legal["check"] and view.opponents == 1:
    draw = len(view.board) < 5 and _has_draw(view)
    if rng.random() < (0.45 if draw else 0.08):
      return _min_raise(view)
  if view.legal["check"]:
    return "check", None
  affordable = view.legal["call_amount"] <= min(view.stack // 4, view.pot // 3)
  if view.legal["call"] and (strength == "strong" or (strength == "medium" and affordable)):
    return "call", None
  return "fold", None


def tight(view, rng):
  return _value_strategy(view, rng, loose=False)


def loose_aggressive(view, rng):
  return _value_strategy(view, rng, loose=True)


BASELINES = {
  "Calling Station": calling_station,
  "Random": random_bot,
  "Tight": tight,
  "Loose-Aggressive": loose_aggressive,
}
