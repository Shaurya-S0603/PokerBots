"""Rank the best five of seven cards as a comparable tuple."""

from collections import Counter

RANK = dict(zip("2 3 4 5 6 7 8 9 10 J Q K A".split(), range(2, 15)))


def straight_high(values):
  mask = 0
  for rank in values:
    mask |= 1 << rank
  if mask & (1 << 14):
    mask |= 2
  runs = mask & (mask << 1) & (mask << 2) & (mask << 3) & (mask << 4)
  return runs.bit_length() - 1 if runs else 0


def rank_hand(cards):
  counts = Counter()
  suits = {}
  for rank, suit in cards:
    value = RANK[rank]
    counts[value] += 1
    suits.setdefault(suit, []).append(value)
  order = sorted(counts, reverse=True)
  flush = next((sorted(values, reverse=True) for values in suits.values() if len(values) >= 5), [])
  if flush and (high := straight_high(flush)):
    return (8, high)
  quads = next((rank for rank in order if counts[rank] == 4), None)
  if quads:
    return (7, quads, next(rank for rank in order if rank != quads))
  trips = [rank for rank in order if counts[rank] >= 3]
  pairs = [rank for rank in order if counts[rank] >= 2]
  if trips:
    side = next((rank for rank in pairs if rank != trips[0]), None)
    if side:
      return (6, trips[0], side)
  if flush:
    return (5, *flush[:5])
  if high := straight_high(order):
    return (4, high)
  if trips:
    return (3, trips[0], *[rank for rank in order if rank != trips[0]][:2])
  if len(pairs) >= 2:
    return (2, *pairs[:2], next(rank for rank in order if rank not in pairs[:2]))
  if pairs:
    return (1, pairs[0], *[rank for rank in order if rank != pairs[0]][:3])
  return (0, *order[:5])
