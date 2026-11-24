"""Ashwing_V4: validated stack specialists plus public-range action evaluation."""
from functools import lru_cache
from math import log,sqrt
from pathlib import Path
from random import Random
import json
from . import ashwing_v3,ashwing_policy,ashwing_v31,masterstats_policy
from .model import validate_decision
from .v4_equity import analyse
TITLE='Ashwing_V4';ANCHORS=(5,10,25,50,100)
@lru_cache(maxsize=1)
def routing():
    p=Path(__file__).resolve().parents[1]/'training/ashwing-v4-router.json'
    return json.loads(p.read_text()) if p.exists() else {'mapping':{}}
def depth_bb(v):
    other=max((p.stack+p.current_bet for p in v.public_players if p.player_id!=v.player_id and not p.folded),default=0) if v.public_players else v.effective_raise_total or v.table_bet
    return min(v.stack+v.current_bet,other)/v.big_blind
def specialist(v):
    anchor=min(ANCHORS,key=lambda x:abs(log(max(.1,depth_bb(v))/x)))
    return routing()['mapping'].get(f'{"heads" if v.opponents==1 else "mixed6"}/{anchor}','v3'),anchor
def expert(name,v,rng,history):
    if name=='monarch':
        from archives.monarch.pokerbots_sdk.hive_policy import hive_mind
        return hive_mind(v,rng)
    return {'v3':ashwing_v3.decide,'v2':ashwing_policy.decide,'v3.1':ashwing_v31.decide,'masterstats':masterstats_policy.decide}[name](v,rng,history=history)
def canonical(v,decision):
    action,target=decision
    return (('call',None) if v.stack+v.current_bet<=v.table_bet else ('raise',v.stack+v.current_bet)) if action=='all_in' else (action,target)
def decide(v,rng,*,history=None,public_history=None,variant='guarded',trace=None):
    name,anchor=specialist(v)
    if variant in ('no_router','guarded'):name='v3'
    original=rng.getstate();base=expert(name,v,rng,history);validate_decision(v,*base)
    street={0:'preflop',3:'flop',4:'turn',5:'river'}[len(v.board)]
    def done(action,reason,**details):
        validate_decision(v,*action)
        if trace is not None:trace.update(expert=name,anchor=anchor,street=street,reason=reason,baseline=base,changed=action!=base,**details)
        return action
    if variant=='router':return done(base,'router_only')
    if variant=='guarded':
        if v.opponents!=1 or len(v.board) not in (3,4) or v.legal['call_amount']<.4*v.pot:
            return done(base,'outside_large_bet_guard')
        if canonical(v,base)[0] not in ('fold','call'):
            return done(base,'preserve_value_reraise')
    if not v.public_players:return done(base,'public_metadata_missing')
    if (v.legal['call_amount'] and not v.legal['call']) or (not v.legal['call_amount'] and not v.legal['check']):return done(base,'unabstracted_legal_menu')
    if not v.board and depth_bb(v)>10:return done(base,'deep_preflop_specialist')
    branch=Random();branch.setstate(original);advisers=[base]
    if name!='v3':advisers.append(ashwing_v3.decide(v,branch))
    targets=[t for a,t in [canonical(v,d) for d in advisers] if a=='raise']
    model=analyse(v,rng,trials=256 if v.opponents==1 else 192,targets=targets,future=variant!='range',history=public_history)
    if not model['supported']:return done(base,model['reason'])
    if min(model['ess'].values())<max(16,.10*model['trials']):return done(base,'low_effective_samples')
    options={(x['action'],x['target']):x for x in model['actions']};control=canonical(v,base)
    if control not in options and control[0]=='raise':control=('raise',min(control[1],v.effective_raise_total))
    if control not in options:return done(base,'baseline_outside_abstraction')
    if variant=='guarded':options={a:r for a,r in options.items() if a[0] in ('fold','call')}
    best=max(options,key=lambda a:options[a]['score']);chosen=options[best];ref=options[control]
    margin=.05*v.big_blind+sqrt(chosen['se']**2+ref['se']**2)
    result=best if chosen['score']>ref['score']+margin else base
    if variant=='guarded' and result!=base:
        if any(chosen['scenarios'][s]['future']<=ref['scenarios'][s]['future']+margin for s in chosen['scenarios']):
            result=base
        if best[0]=='call' and min(model['equity'].values())<v.legal['call_amount']/(v.pot+v.legal['call_amount'])+.03:
            result=base
    return done(result,'range_ev_switch' if result!=base else 'range_ev_preserve',equity=model['equity'],ess=model['ess'],model_ev=chosen['score'],control_ev=ref['score'],margin=margin,potential=model['potential'],options=model['actions'])
