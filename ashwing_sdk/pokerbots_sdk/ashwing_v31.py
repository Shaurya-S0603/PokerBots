"""Range-aware commitment check for Ashwing. All inputs are public or hero cards."""
from functools import lru_cache
from itertools import combinations

from equity import DECK
from fast_rank import rank_hand
from .ashwing_v3 import decide as frozen
from .betting_line import preflop_strength


@lru_cache(maxsize=512)
def value_range(hole, tight):
    unseen = tuple(c for c in DECK if c not in hole)
    pairs = []
    for a, b in combinations(unseen, 2):
        ranks = {a[0], b[0]}
        pair = len(ranks) == 1
        if (pair and ranks <= (set('QKA') if tight else {'9','10','J','Q','K','A'})) or (
                not tight and 'A' in ranks and ranks & {'Q','K'}):
            pairs.append((a, b))
    return unseen, tuple(pairs)


def range_check(view, rng, action, *, multiway=True, trace=None):
    price = view.legal['call_amount']
    if (view.board or action[0] == 'fold' or not view.legal['call'] or not price
            or view.table_bet <= view.big_blind or view.hole[0][0] == view.hole[1][0] in ('A','K')):
        return action
    multi = view.opponents > 1
    effective = min(view.stack + view.current_bet, view.effective_raise_total or view.table_bet)
    if multi:
        if not multiway or view.has_all_in_opponent or price < 2 * view.big_blind:
            return action
    elif len(view.stacks) != 2 or effective <= 10 * view.big_blind or price < max(
            3 * view.big_blind, .25 * effective):
        return action
    raises = [s for s in view.betting_line if s.action == 'raise']
    if not raises or not raises[-1].opponent:
        return action
    tight = len(raises) >= 2 or price >= .70 * effective
    unseen, value = value_range(view.hole, tight)
    total = 0.
    for _ in range(48):
        strong = rng.random() < (.75 if tight else .60)
        villain = rng.choice(value) if strong else tuple(rng.sample(unseen, 2))
        deck = [c for c in unseen if c not in villain]
        run = rng.sample(deck, 5 + 2 * (view.opponents - 1))
        board = tuple(run[:5])
        hero = rank_hand(view.hole + board)
        others = [rank_hand(villain + board)] + [
            rank_hand(tuple(run[i:i+2]) + board) for i in range(5,len(run),2)]
        if hero >= max(others):
            total += 1 / (1 + others.count(hero))
    equity = total / 48
    pot = view.pot - max(0, view.table_bet - view.current_bet - price)
    realization = 1. if price == view.stack or (not multi and view.has_all_in_opponent) else (
        .85 if multi and not view.late_position else .92)
    ev = equity * realization * (pot + price) - price
    if trace is not None:
        trace.update(equity=equity, call_ev=ev, matched_pot=pot, call=price,
                     realization=realization, value_weight=.75 if tight else .60)
    if ev < -.03 * (pot + price) and view.legal['fold']:
        return 'fold', None
    if action[0] in ('raise','all_in') and equity < .58:
        return 'call', None
    return action


def small_open(view, action):
    if (view.board or not view.late_position or len(view.stacks) != 2 or view.opponents != 1
            or view.table_bet != view.big_blind or view.betting_line or action[0] in ('raise','all_in')
            or view.effective_raise_total < 16 * view.big_blind or not view.legal['raise']):
        return action
    target = 2 * view.big_blind
    if (preflop_strength(view.hole) >= .54
            and view.legal['min_raise_total'] <= target <= min(view.effective_raise_total,view.legal['max_raise_total'])):
        return 'raise', target
    return action


def experiment(view, rng, *, history=None, variant='range', trace=None):
    base = frozen(view, rng, history=history)
    if variant in ('range','heads','combined'):
        result = range_check(view, rng, base, multiway=variant != 'heads', trace=trace)
    else:
        result = base
    return small_open(view, result) if variant in ('open','combined') else result


def decide(view, rng, *, history=None):
    return small_open(view, frozen(view, rng, history=history))
