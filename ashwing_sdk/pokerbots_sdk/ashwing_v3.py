"""Heads-up range adjustments around the released Search and short-stack policy."""
from equity import _known_cards
from fast_rank import rank_hand

from .ashwing_policy import decide as baseline
from .betting_line import evaluate_range, preflop_strength


def reraised_preflop(view, rng, action):
    price = view.legal["call_amount"]
    depth = min(view.stack + view.current_bet, view.effective_raise_total or view.table_bet)
    if depth <= 10 * view.big_blind or price <= 0 or not view.legal["call"]:
        return action
    raises = [step for step in view.betting_line if step.action == "raise"]
    if not raises or not raises[-1].opponent:
        return action
    # Pressure a deep opening or reraising range with the top two pocket pairs.
    # Use the legal effective target so a covering stack never prices side chips.
    ranks = tuple(card[0] for card in view.hole)
    if ranks in (("A", "A"), ("K", "K")) and view.legal["raise"]:
        target = min(view.effective_raise_total, view.legal["max_raise_total"])
        if view.legal["min_raise_total"] <= target:
            return "raise", target
    if len(raises) < 2:
        return action
    hero, _, unseen = _known_cards(view.hole, (), (0,))
    # Sample plausible three-bet and four-bet ranges. The uniform component
    # retains light reraises, even with hands outside the value range.
    threshold = .64 if len(raises) == 2 else .72
    total = share = 0.
    for _ in range(128):
        deal = rng.sample(unseen, 7)
        opponent, board = tuple(deal[:2]), tuple(deal[2:])
        strength = preflop_strength(opponent)
        weight = .07 + .93 * min(1., max(0., (strength - threshold) / .15))
        own_rank, other_rank = rank_hand(hero + board), rank_hand(opponent + board)
        share += weight * ((own_rank > other_rank) + .5 * (own_rank == other_rank))
        total += weight
    matched = view.pot - max(0, view.table_bet - view.current_bet - price)
    equity = share / total
    if equity < price / (price + matched) and view.legal["fold"]:
        return "fold", None
    if action[0] in ("raise", "all_in") and equity < .63:
        return "call", None
    return action


def experimental(view, rng, *, history=None):
    action = baseline(view, rng, history=history)
    if not view.board and len(view.stacks) == 2 and view.opponents == 1:
        return reraised_preflop(view, rng, action)
    if (len(view.stacks) != 2 or view.opponents != 1 or len(view.board) not in (3, 4)
            or view.current_bet or action[0] not in ("fold", "call")):
        return action
    price = view.legal["call_amount"]
    pot_before = view.pot - view.table_bet
    if price <= 0 or pot_before <= 0 or price < pot_before:
        return action

    # Excess chips from a covering shove are returned to the bettor.
    matched_pot = pot_before + 2 * price
    raw, weighted, outcomes = evaluate_range(view, rng, 96)
    required = price / matched_pot
    # Require agreement under both an unweighted and a line-weighted range.
    margin = .10 if price < view.stack else .07
    if max(raw.equity, weighted) < required - margin and view.legal["fold"]:
        return "fold", None
    if min(raw.equity, weighted) > required + margin and view.legal["call"]:
        # Compare a value shove with calling to showdown under two assumed
        # continuation ranges. Only use it when the remaining risk is bounded.
        target = min(view.effective_raise_total, view.stack)
        extra = target - price
        if (view.legal["raise"] and view.legal["min_raise_total"] <= target <= view.legal["max_raise_total"]
                and 0 < extra <= matched_pot and weighted > .70):
            total = sum(weight for _, _, weight in outcomes)
            for cutoff in (.55, .75):
                gain = 0.
                for hand, share, weight in outcomes:
                    continues = hand.strength + .15 * hand.draw >= cutoff
                    gain += weight * (extra * (2 * share - 1) if continues else (1 - share) * matched_pot)
                if gain / total <= .07 * matched_pot:
                    break
            else:
                return "raise", target
        return "call", None
    return action


def decide(view, rng, *, history=None):
    """Isolate the premium preflop change, using exactly the baseline RNG otherwise."""
    action = baseline(view, rng, history=history)
    if (view.board or len(view.stacks) != 2 or view.opponents != 1 or not view.legal["raise"]
            or tuple(card[0] for card in view.hole) not in (("A", "A"), ("K", "K"))):
        return action
    effective = min(view.stack + view.current_bet, view.effective_raise_total)
    if (effective <= 10 * view.big_blind or not view.legal["call_amount"]
            or not view.betting_line or not view.betting_line[-1].opponent
            or view.betting_line[-1].action != "raise"):
        return action
    target = min(effective, view.legal["max_raise_total"])
    if view.legal["min_raise_total"] <= target:
        return "raise", target
    return action
