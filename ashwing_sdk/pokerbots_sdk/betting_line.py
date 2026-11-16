"""Heads-up range inference from cards and public commitments."""

from dataclasses import dataclass
from itertools import combinations

from equity import EquityResult, _known_cards
from fast_rank import RANK, rank_hand, straight_high


def preflop_strength(hole):
  (first, suit_a), (second, suit_b) = hole
  high, low = sorted((RANK[first], RANK[second]), reverse=True)
  if high == low:
    return .51 + .035 * (high - 2)
  return .20 + .038 * (high - 2) + .013 * (low - 2) + .055 * (suit_a == suit_b) + (
    .035 if high - low <= 2 else 0)


@dataclass(frozen=True)
class Holding:
  cards: tuple
  rank: tuple
  strength: float
  draw: bool


def holding(hole, board):
  score = rank_hand(hole + board)
  category = score[0]
  hole_ranks = {RANK[rank] for rank, _ in hole}
  board_ranks = [RANK[rank] for rank, _ in board]
  if category < 3:
    own_pairs = [rank for rank in score[1:1 + category] if rank in hole_ranks]
    strength = .13 + .012 * max(hole_ranks)
    if own_pairs:
      strength = .47 + .22 * (max(own_pairs) >= max(board_ranks)) + .12 * (len(own_pairs) == 2)
    elif category:
      strength += .07
  elif len(board) == 5 and score == rank_hand(board):
    strength = .28
  elif category == 3 and board_ranks.count(score[1]) >= 3:
    strength = .50
  else:
    strength = min(.74 + .055 * (category - 3), 1)
  draw = False
  if len(board) < 5:
    cards = hole + board
    draw = any(sum(card[1] == suit for card in cards) == 4 for _, suit in hole)
    ranks = hole_ranks | set(board_ranks)
    if not draw and category < 4:
      draw = sum(bool(straight_high(ranks | {rank})) for rank in range(2, 15) if rank not in ranks) >= 2
  return Holding(hole, score, strength, draw)


def action_likelihood(line, hand, big_blind, late, *, polarized=False):
  if line.street == "preflop":
    strength = preflop_strength(hand)
    if line.action == "raise":
      threshold = (.51 if late else .57) + .025 * max(0, min(line.amount / big_blind - 3, 6))
      return .20 + .80 * min(1, max(0, (strength - threshold + .18) / .36))
    return .40 + .60 * min(1, strength / .62)

  size = min(line.amount / max(big_blind, line.pot_before), 2)
  strength = min(1, hand.strength + (.20 if hand.draw else 0))
  if line.action == "raise":
    weight = (.30 - .08 * size) + (.68 + .08 * size) * strength ** 2
    if polarized:
      # A large turn bet after a small flop bet can come from air or value.
      air = max(0, (.47 - hand.strength) / .47)
      weight += .25 * air * min(1, size)
    return weight
  return (.42 - .12 * size) + (.56 + .12 * size) * strength


def evaluate_range(view, rng, trials, curve=None, *, polarize_turn=False):
  """Reweight each combo on the board visible at each recorded action."""
  hole, board, unseen = _known_cards(view.hole, view.board, (3, 4, 5))
  street_size = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
  line = [step for step in view.betting_line if step.opponent and street_size[step.street] <= len(board)]
  polarized_turn = None
  if polarize_turn:
    raises = [step for step in view.betting_line if step.street == "turn" and step.action == "raise"]
    flop_raises = [step for step in view.betting_line if step.street == "flop" and step.action == "raise"]
    if (len(raises) == 1 and raises[0].opponent and raises[0].amount * 3 >= raises[0].pot_before * 2
        and len(flop_raises) == 1 and flop_raises[0].opponent
        and flop_raises[0].amount * 2 <= flop_raises[0].pot_before):
      polarized_turn = raises[0]

  def scored(opponent):
    by_street = {len(board): holding(opponent, board)}
    weight = 1.0
    for step in line:
      length = street_size[step.street]
      if length and length not in by_street:
        by_street[length] = holding(opponent, board[:length])
      weight *= action_likelihood(step, by_street[length] if length else opponent,
        view.big_blind, late=not view.late_position, polarized=step is polarized_turn)
    return by_street[len(board)], weight

  if len(board) == 5:
    candidates, weights = zip(*(scored(opponent) for opponent in combinations(unseen, 2)))
    hero = rank_hand(hole + board)
    outcomes = [((hero > item.rank) - (hero < item.rank) + 1) / 2 for item in candidates]
    result = EquityResult(outcomes.count(1), outcomes.count(.5), outcomes.count(0),
      sum(outcomes) / len(outcomes))
    weighted = sum(outcome * weight for outcome, weight in zip(outcomes, weights)) / sum(weights)
    return result, weighted, list(zip(candidates, outcomes, weights))

  # Importance-weight the same uniformly sampled combinations for a direct
  # comparison. Runouts draw only from cards remaining after that holding.
  wins = ties = losses = 0
  weight_total = weighted_share = 0.0
  outcomes = []
  cached = {}
  order = {card: index for index, card in enumerate(unseen)}
  missing = 5 - len(board)
  for index in range(1, trials + 1):
    dealt = rng.sample(unseen, missing + 2)
    opponent = tuple(sorted(dealt[missing:], key=order.__getitem__))
    if opponent not in cached:
      cached[opponent] = scored(opponent)
    item, weight = cached[opponent]
    runout = board + tuple(dealt[:missing])
    hero, other = rank_hand(hole + runout), rank_hand(item.cards + runout)
    share = ((hero > other) - (hero < other) + 1) / 2
    wins += share == 1
    ties += share == .5
    losses += share == 0
    weighted_share += weight * share
    weight_total += weight
    outcomes.append((item, share, weight))
    if curve is not None and (index % 16 == 0 or index == trials):
      curve.append({"Trials": index, "Equity": (wins + ties / 2) / index, "Win rate": wins / index,
        "Weighted equity": weighted_share / weight_total})
  return EquityResult(wins, ties, losses, (wins + ties / 2) / trials), weighted_share / weight_total, outcomes


def opening_bet_values(view, outcomes, amounts):
  """Chip EV from now under a fold-or-call and check-to-showdown model."""
  total = sum(weight for _, _, weight in outcomes)
  result = [{"action": "check", "amount": 0,
    "ev_chips": sum(weight * share * view.pot for _, share, weight in outcomes) / total}]
  for amount in amounts:
    price = amount / (view.pot + 2 * amount)
    ev = worse_calls = better_folds = better_calls = 0.0
    for item, share, weight in outcomes:
      strength = item.strength + (.19 if item.draw else 0)
      continues = max(.04, min(.98, .5 + 2.3 * (strength - (.30 + 1.5 * price))))
      ev += weight * ((1 - continues) * view.pot + continues * (share * (view.pot + 2 * amount) - amount))
      worse_calls += weight * share * continues if share == 1 else 0
      better_folds += weight * (1 - continues) if share == 0 else 0
      better_calls += weight * continues if share == 0 else 0
    result.append({"action": "raise", "amount": amount, "ev_chips": ev / total,
      "worse_call_mass": worse_calls / total, "better_fold_mass": better_folds / total,
      "better_call_mass": better_calls / total})
  return result
