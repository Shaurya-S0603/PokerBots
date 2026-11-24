"""Tie-corrected preflop anchor, with a bounded correction to shallow range sampling."""
from functools import lru_cache
import json
from pathlib import Path
from random import Random

from equity import _known_cards
from .ashwing_v3 import decide as frozen
from .ashwing_policy import _decide, PROFILE, short_stack
from .equity_policy import equity_bot
from .search_policy import limp_bucket
from .strategies import VALUE_PROFILE

RANK='23456789TJQKA'


def hand_class(hole):
    _known_cards(hole,(),(0,))
    ranks=sorted(('T' if c[0]=='10' else c[0] for c in hole),key=RANK.index,reverse=True)
    return ''.join(ranks)+('' if ranks[0]==ranks[1] else 's' if hole[0][1]==hole[1][1] else 'o')


@lru_cache(maxsize=1)
def tables():
    path=Path(__file__).resolve().parents[1]/'training/masterstats.json'
    return json.loads(path.read_text())['tables']


def estimate(hole,opponents):
    if type(opponents) is not int or not 1<=opponents<=9:
        raise ValueError('Expected one through nine opponents')
    return tables()[str(opponents+1)][hand_class(hole)]


def experiment(view,rng,*,history=None,variant='combined',trace=None):
    if view.board:
        return frozen(view,rng,history=history)
    effective=min(view.stack+view.current_bet,view.effective_raise_total or view.table_bet)
    if (variant in ('shallow','combined') and len(view.stacks)==2 and view.opponents==1
            and effective<=10*view.big_blind and view.legal['call_amount']):
        starting_state=rng.getstate()
        anchor=estimate(view.hole,1)['equity']
        def corrected(v,r,control,details):
            return short_stack(v,r,control,details,uniform_equity=anchor)
        result=_decide(view,rng,history=history,profile=PROFILE,shallow_strategy=corrected)
        if trace is not None:
            audit_rng=Random()
            audit_rng.setstate(starting_state)
            trace.update(method='Shallow range control variate',anchor=anchor,baseline=frozen(view,audit_rng,history=history),selected=result)
        return result
    if (variant not in ('lookup','combined') or view.table_bet>view.big_blind or
            view.has_all_in_opponent or limp_bucket(view) is not None or
            (len(view.stacks)==2 and effective<=10*view.big_blind)):
        return frozen(view,rng,history=history)
    # Keep baseline RNG consumption so changing the estimate does not also
    # change later randomized decisions in callers that retain the generator.
    state=rng.getstate()
    baseline=frozen(view,rng,history=history)
    rng.setstate(state)
    anchor=estimate(view.hole,view.opponents)['equity']
    result=equity_bot(view,rng,profile=VALUE_PROFILE,arena_opening=view.opponents>1,preflop_equity=anchor)
    if trace is not None:trace.update(method='Uniform preflop anchor',anchor=anchor,baseline=baseline,selected=result)
    return result


def decide(view,rng,*,history=None,trace=None):
    return experiment(view,rng,history=history,trace=trace)
