"""Ashwing research candidate selected on the 100-hand development suite."""
from equity import _known_cards
from fast_rank import rank_hand
from pokerbots_sdk.betting_line import action_likelihood, preflop_strength
from pokerbots_sdk.equity_policy import _sized_raise
from pokerbots_sdk.hive_policy import adaptive_river_value_pressure, hive_mind
from pokerbots_sdk.search_policy import ashwing_search

def _decide(view, rng, *, history, profile, shallow_strategy):
    use_search, shallow_mode, opening, multiway = profile
    if not view.board and view.legal["raise"]:
        strength = preflop_strength(view.hole)
        if len(view.stacks) == 2 and view.opponents == 1 and opening:
            effective = min(view.stack+view.current_bet,view.effective_raise_total)
            if view.table_bet == view.big_blind and effective >= 8*view.big_blind:
                threshold = {"tight": .56, "wide": .44}[opening]
                if strength >= threshold + (.045 if not view.late_position else 0):
                    action = _sized_raise(view, view.big_blind)
                    if action:
                        return action
        if view.opponents > 1 and multiway and view.table_bet == view.big_blind:
            if strength >= (.60 if view.late_position else .67):
                action = _sized_raise(view,max(view.big_blind,view.pot // 2))
                if action:
                    return action
    if use_search:
        baseline = ashwing_search(view,rng,history=history)
    elif history is not None:
        baseline = adaptive_river_value_pressure(view,rng,history)
    else:
        baseline = hive_mind(view,rng)
    if shallow_mode != "none" and not view.board and len(view.stacks)==2 and view.opponents==1:
        effective = min(view.stack+view.current_bet,view.effective_raise_total or view.table_bet)
        limit = 5 if shallow_mode == "5bb" else 10
        if 0 < effective <= limit*view.big_blind and view.legal["call_amount"]:
            return shallow_strategy(view,rng,baseline,{})
    return baseline


def short_stack(view, rng, control, details, *, uniform_equity=None):
    if view.board or view.opponents != 1 or len(view.stacks) != 2:
        return control
    price = view.legal["call_amount"]
    opponent_total = view.effective_raise_total or view.table_bet
    effective = min(view.stack + view.current_bet, opponent_total)
    if not price or effective > 10 * view.big_blind:
        return control
    raised = [step for step in view.betting_line if step.opponent and step.action == "raise"]
    if not raised and view.table_bet != view.big_blind:
        return control
    hole, _, unseen = _known_cards(view.hole, (), (0,))
    total = share = answered = answered_share = unweighted = 0.
    for _ in range(72):
        deal = rng.sample(unseen, 7)
        other = tuple(deal[:2])
        board = tuple(deal[2:])
        score, opposing = rank_hand(hole + board), rank_hand(other + board)
        equity = (1 + (score > opposing) - (score < opposing)) / 2
        unweighted += equity
        weight = action_likelihood(raised[-1], other, view.big_blind, not view.late_position) if raised else 1.
        call_weight = (.18 if raised else .08) + .75 / (1 + 2.71828 ** (-(preflop_strength(other) - .56) * 16))
        total += weight
        share += equity * weight
        answered += weight * call_weight
        answered_share += equity * weight * call_weight
    pot = view.pot - max(0, view.table_bet - view.current_bet - price)
    facing_all_in = price == view.stack or view.has_all_in_opponent
    adjustment = 0. if uniform_equity is None else max(-.08, min(.08, uniform_equity - unweighted / 72))
    call_equity = min(1., max(0., share / total + adjustment))
    call_ev = call_equity * (pot + price) * (1 if facing_all_in else .84) - price
    best = ("call", None) if call_ev > 0 else ("fold", None)
    stack_risk = effective - view.current_bet
    if view.legal["all_in"] and not facing_all_in and stack_risk > price:
        call_rate = answered / total
        matched_extra = max(0, effective - view.table_bet)
        jam_ev = (1 - call_rate) * pot + call_rate * (
            min(1., max(0., answered_share / answered + adjustment)) * (pot + stack_risk + matched_extra) - stack_risk)
        if jam_ev > max(0, call_ev) + .12 * view.big_blind:
            best = ("all_in", None)
    return best

PROFILE = (True, '10bb', None, False)


def decide(view, rng, *, history=None):
    return _decide(view, rng, history=history, profile=PROFILE, shallow_strategy=short_stack)
