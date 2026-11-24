"""Joint public-range equity, common-deal action EV and one-street potential."""
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from math import exp,sqrt
from equity import _known_cards
from fast_rank import rank_hand
from .betting_line import holding,preflop_strength,action_likelihood
SCENARIOS={'value':(12.,3.,.35),'balanced':(6.,5.,1.),'draw':(3.,10.,.6),'bluff':(4.,2.,5.)}
STREET={'preflop':0,'flop':3,'turn':4,'river':5}
@dataclass(frozen=True)
class PublicPlayer:
    player_id:object
    stack:int
    current_bet:int
    total_bet:int
    folded:bool=False
    all_in:bool=False
@lru_cache(maxsize=32000)
def feature(hand,board):return holding(hand,board) if board else None

def legal_targets(v,extras=()):
    if not v.legal['raise'] or v.legal['min_raise_total'] is None:return ()
    top=min(v.legal['max_raise_total'],v.effective_raise_total)
    low=min(v.legal['min_raise_total'],v.legal['max_raise_total'])
    if top<low:return ()
    pot=v.pot+v.legal['call_amount']
    choices={low,top,v.table_bet+int(.5*pot),v.table_bet+pot,*extras}
    return tuple(sorted({int(min(top,max(low,x))) for x in choices if x is not None}))

def payout(contributions,eligible,ranks,hero=0):
    value=0.;previous=0
    for level in sorted({c for c in contributions if c>0}):
        contributors=[i for i,c in enumerate(contributions) if c>=level]
        pot=(level-previous)*len(contributors);previous=level
        if len(contributors)==1:
            if contributors[0]==hero:value+=pot
            continue
        alive=[i for i in contributors if eligible[i]]
        if not alive:continue
        best=max(ranks[i] for i in alive);winners=[i for i in alive if ranks[i]==best]
        if hero in winners:value+=pot/len(winners)
    return value

def continue_probability(hand,board,price,pot,shift=0.,all_in=False):
    if all_in or price<=0:return 1.
    if len(board)==5:
        r=rank_hand(board)
        if (r[0]==8 and r[1]==14) or (r[0]==7 and (r[2]==14 or r[1:3]==(14,13))):return 1.
    f=feature(hand,board);strength=preflop_strength(hand) if f is None else f.strength+.16*f.draw
    threshold=.27+1.15*price/max(1,pot+price)+shift
    return max(.025,min(.99,1/(1+exp(-10*(strength-threshold)))))

def weight(v,pid,hand,name,aggressor,history):
    f=feature(hand,v.board)
    if f is None:w=.15+.85/(1+exp(-(preflop_strength(hand)-(.54 if v.late_position else .58))*14))
    else:
        kind=0 if f.strength>=.69 else 1 if f.draw else 2
        w=(SCENARIOS[name] if aggressor else (2.5,2.,1.))[kind]**(.8 if aggressor else .65)
    for step in v.public_line:
        if step.player_id!=pid or step.action not in ('call','raise') or STREET.get(step.street,99)>len(v.board):continue
        n=STREET[step.street];f0=feature(hand,v.board[:n]) if n else hand
        w*=max(.05,action_likelihood(step,f0,v.big_blind,not v.late_position))**.55
    if history is not None and f is not None and aggressor:
        aggression,count=history.aggression(pid)
        w*=max(.5,min(1.5,1+(aggression-.25)*(1-2*(f.strength+.15*f.draw))*min(1,count/20)))
    return max(1e-9,w)

def barrel_probability(hand,board,name):
    f=feature(hand,board)
    return .70 if f.strength>=.69 else .55 if f.draw else .12 if name=='value' else .45 if name=='bluff' else .25

def analyse(v,rng,*,trials=256,targets=(),future=True,history=None,scenarios=None):
    if not v.public_players:return {'supported':False,'reason':'public_metadata_missing'}
    own=next(p for p in v.public_players if p.player_id==v.player_id)
    people=(own,)+tuple(p for p in v.public_players if p.player_id!=v.player_id)
    if sum(p.total_bet for p in people)!=v.pot:return {'supported':False,'reason':'commitment_mismatch'}
    active=[i for i,p in enumerate(people) if i and not p.folded]
    if len(active)!=v.opponents:return {'supported':False,'reason':'opponent_count_mismatch'}
    hole,board,deck=_known_cards(v.hole,v.board,(0,3,4,5));missing=5-len(board)
    last=next((x.player_id for x in reversed(v.public_line) if x.action=='raise'),None)
    aggressor=next((i for i,p in enumerate(people) if p.player_id==last),active[0] if len(active)==1 else None)
    call=v.legal['call_amount'];names=tuple(scenarios or SCENARIOS)
    actions=([('fold',None)] if call and v.legal['fold'] else [])+[('call',None) if call else ('check',None)]+[('raise',x) for x in legal_targets(v,targets)]
    samples=[];weights={name:[] for name in names}
    for j in range(trials):
        cards=rng.sample(deck,2*len(active)+missing);hands={i:tuple(cards[2*k:2*k+2]) for k,i in enumerate(active)}
        runout=board+tuple(cards[2*len(active):]);ranks={0:rank_hand(hole+runout)}
        ranks.update({i:rank_hand(hand+runout) for i,hand in hands.items()});best=max(ranks.values());winners=[i for i,r in ranks.items() if r==best]
        share=1/len(winners) if 0 in winners else 0.;uniforms={i:rng.random() for i in active};ws={name:1. for name in names}
        for i,hand in hands.items():
            for name in names:ws[name]*=weight(v,people[i].player_id,hand,name,i==aggressor,history)
        for name in names:weights[name].append(ws[name])
        samples.append((hands,runout,ranks,share,uniforms,ws))
    equity={};ess={};potential={};future_info={}
    for name in names:
        ws=weights[name];total=sum(ws);ess[name]=total*total/sum(w*w for w in ws)
        equity[name]=sum(w*s[3] for w,s in zip(ws,samples))/total
        halves=[defaultdict(lambda:[0.,0.]),defaultdict(lambda:[0.,0.])];global_sums=[[0.,0.],[0.,0.]];qs=[];bycard=defaultdict(lambda:[0.,0.])
        for j,s in enumerate(samples):
            hands,runout,ranks,share,uniforms,w=s
            q=barrel_probability(hands[active[0]],board+(runout[len(board)],),name) if missing and len(active)==1 else 0.;qs.append(q)
            key=runout[len(board)] if missing else None;bycard[key][0]+=w[name]*share;bycard[key][1]+=w[name]
            if missing:
                x=w[name]*q;halves[j%2][key][0]+=x*share;halves[j%2][key][1]+=x;global_sums[j%2][0]+=x*share;global_sums[j%2][1]+=x
        global_e=[a/b if b else .5 for a,b in global_sums];scale=trials/total
        conditional=[{k:(a*scale+4*global_e[h])/(b*scale+4) for k,(a,b) in halves[h].items()} for h in (0,1)]
        future_info[name]=(qs,conditional,global_e)
        bins=[0.]*10
        for k,(a,b) in bycard.items():bins[min(9,int(10*a/b))]+=b/total
        potential[name]={'bins':bins,'mean':equity[name],'next_card_equity':{str(k):a/b for k,(a,b) in bycard.items()}}
    rows=[]
    for action,target in actions:
        values={name:[[],[]] for name in names}
        for j,(hands,runout,ranks,share,uniforms,ws) in enumerate(samples):
            if action=='fold':
                for name in names:values[name][0].append(0.);values[name][1].append(0.)
                continue
            cost=call if action=='call' else target-v.current_bet if action=='raise' else 0;target_bet=v.current_bet+cost
            returns=[]
            for shift in (-.07,0.,.10):
                contrib=[p.total_bet for p in people];contrib[0]+=cost;eligible=[not p.folded for p in people]
                for i in active:
                    p=people[i];extra=min(p.stack,max(0,target_bet-p.current_bet))
                    q=continue_probability(hands[i],board,extra,v.pot+cost,shift,p.all_in);eligible[i]=p.all_in or uniforms[i]<q
                    if eligible[i]:contrib[i]+=extra
                returns.append(payout(contrib,eligible,ranks)-cost)
            static=sum(returns)/3
            for name in names:
                value=static
                if future and action=='call' and missing and len(active)==1 and not v.has_all_in_opponent and call<v.stack:
                    other=people[active[0]]
                    if other.current_bet==v.current_bet+call:
                        pot=v.pot+call;bet=min(v.stack-call,other.stack,int(.75*pot));qs,conditional,prior=future_info[name]
                        e=conditional[1-j%2].get(runout[len(board)],prior[1-j%2]);calls=e*(pot+2*bet)>=bet
                        continuation=share*(pot+2*bet)-call-bet if calls else -call
                        value=(1-qs[j])*(share*pot-call)+qs[j]*continuation
                values[name][0].append(static);values[name][1].append(value)
        scenario_values={}
        for name in names:
            ws=weights[name];total=sum(ws);means=[];errors=[]
            for ys in values[name]:
                mean=sum(w*y for w,y in zip(ws,ys))/total;means.append(mean);errors.append(sqrt(sum((w/total)**2*(y-mean)**2 for w,y in zip(ws,ys))))
            scenario_values[name]={'passive':means[0],'future':means[1],'se':max(errors)}
        evs=[x['future'] for x in scenario_values.values()]
        rows.append({'action':action,'target':target,'score':sum(evs)/len(evs)-.20*(max(evs)-min(evs)),'se':max(x['se'] for x in scenario_values.values()),'scenarios':scenario_values})
    return {'supported':True,'equity':equity,'ess':ess,'potential':potential,'trials':trials,'actions':rows,'method':'one-barrel-cross-fit' if future else 'check-to-showdown'}
