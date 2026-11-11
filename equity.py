"""Showdown equity against uniformly distributed unknown cards."""

from dataclasses import dataclass
from itertools import combinations

from poker_engine import compare, highest_hand
from pokerroom import ranks, suits

DECK = tuple((rank, suit) for rank in ranks for suit in suits)
DECK_SET = frozenset(DECK)


@dataclass(frozen=True)
class EquityResult:
  wins: int
  ties: int
  losses: int
  equity: float


def _known_cards(hole, board, board_sizes):
  hole, board = tuple(hole), tuple(board)
  if len(hole) != 2 or len(board) not in board_sizes:
    raise ValueError("Expected two hole cards and a board of the required size")
  known = hole + board
  if any(not isinstance(card, tuple) or len(card) != 2
      or not all(isinstance(part, str) for part in card) or card not in DECK_SET for card in known):
    raise ValueError("Every card must belong to the PokerRoom deck")
  if len(set(known)) != len(known):
    raise ValueError("Known cards must be distinct")
  seen = set(known)
  return hole, board, tuple(card for card in DECK if card not in seen)


def exact_river_equity(hole, board):
  hole, board, unseen = _known_cards(hole, board, (5,))
  hero = highest_hand(hole + board)
  wins = ties = losses = 0
  for opponent in combinations(unseen, 2):
    winners = compare({0: hero, 1: highest_hand(opponent + board)})
    if len(winners) == 2:
      ties += 1
    elif winners[0] == 0:
      wins += 1
    else:
      losses += 1
  return EquityResult(wins, ties, losses, (wins + ties / 2) / (wins + ties + losses))


def sample_equity(hole, board, opponents, trials, rng, *, checkpoints=None):
  hole, board, unseen = _known_cards(hole, board, (0, 3, 4, 5))
  if type(opponents) is not int or not 1 <= opponents <= 9:
    raise ValueError("Expected between one and nine opponents")
  if type(trials) is not int or trials < 1:
    raise ValueError("Expected a positive trial count")
  missing = 5 - len(board)
  hero_on_river = highest_hand(hole + board) if missing == 0 else None
  wins = ties = losses = 0
  shares = 0.0
  for completed in range(1, trials + 1):
    dealt = rng.sample(unseen, missing + 2 * opponents)
    runout = board + tuple(dealt[:missing])
    hands = {0: hero_on_river if hero_on_river is not None else highest_hand(hole + runout)}
    for seat in range(1, opponents + 1):
      start = missing + 2 * (seat - 1)
      hands[seat] = highest_hand(tuple(dealt[start:start + 2]) + runout)
    winners = compare(hands)
    if 0 not in winners:
      losses += 1
    elif len(winners) == 1:
      wins += 1
      shares += 1
    else:
      ties += 1
      shares += 1 / len(winners)
    if checkpoints is not None and (completed % 16 == 0 or completed == trials):
      checkpoints.append({"Trials": completed, "Equity": shares / completed, "Win rate": wins / completed})
  return EquityResult(wins, ties, losses, shares / trials)
