from dataclasses import replace,fields
from random import Random
import pytest
from arena import observe
from poker_engine import start_game
from pokerbots_sdk import load_strategy
from pokerbots_sdk.model import PublicAction,validate_decision
from pokerbots_sdk.v4_equity import PublicPlayer,payout,analyse,legal_targets
from pokerbots_sdk.v4_history import PublicHistory
from pokerbots_sdk import ashwing_v4

def view(n=2):
    g=start_game(n,1000,5,10,deck_rng=Random(712));return observe(g,g.players[g.current_player])

def test_pot_tiers_ties_dead_money_uncalled():
    assert payout([50,100,200],[1,1,1],{0:3,1:2,2:1})==150
    assert payout([200,100,50],[1,1,1],{0:1,1:3,2:2})==100
    assert payout([100]*3,[1]*3,{0:1,1:1,2:1})==100
    assert payout([100]*3,[1,0,1],{0:2,1:3,2:1})==300
    assert payout([100]*2,[1,0],{0:1,1:2})==200

@pytest.mark.parametrize('n',[2,3,6])
def test_joint_tie_shares(n):
    v=view(n);board=tuple((r,'♠️') for r in ('10','J','Q','K','A'))
    people=tuple(PublicPlayer(i,900,0,100) for i in range(n));own=people[0]
    v=replace(v,hole=(('2','♣️'),('3','♦️')),board=board,public_players=people,player_id=0,
      current_bet=0,table_bet=0,pot=100*n,stack=900,opponents=n-1,effective_raise_total=900,
      legal={'fold':False,'check':True,'call':False,'raise':True,'all_in':True,'call_amount':0,'min_raise_total':10,'max_raise_total':900})
    result=analyse(v,Random(91),trials=48)
    assert all(abs(e-1/n)<1e-10 for e in result['equity'].values())
    assert all(abs(r['score']-100)<1e-8 for r in result['actions'])

def test_partial_call_without_raise_target():
    v=replace(view(),hole=(('2','♣️'),('3','♦️')),board=(('K','♥️'),('J','♥️'),('8','♠️')),
      stack=50,current_bet=0,table_bet=100,pot=140,opponents=1,player_id=1,
      public_players=(PublicPlayer(1,50,0,20),PublicPlayer(2,860,100,120)),
      public_line=(PublicAction(2,'flop','raise',100,40),),effective_raise_total=50,
      legal={'fold':True,'call':True,'check':False,'raise':False,'all_in':True,'call_amount':50,'min_raise_total':None,'max_raise_total':None})
    assert legal_targets(v)==()
    a=ashwing_v4.decide(v,Random(9));validate_decision(v,*a)
    assert a[0] in ('fold','call','all_in')

def test_observation_excludes_private_simulator_cards():
    g=start_game(2,1000,5,10,deck_rng=Random(727));p=g.players[g.current_player];a=observe(g,p)
    other=next(x for x in g.players if x!=p)
    # Public metadata has no hole-card field. Changing simulator cards cannot affect observation.
    assert 'hole' not in {f.name for f in fields(PublicPlayer)}
    other.hole_cards=list(reversed(other.hole_cards))
    b=observe(g,p);assert a==b
    assert ashwing_v4.decide(a,Random(14))==ashwing_v4.decide(b,Random(14))

def test_public_history_dedup_and_match_scope():
    h=PublicHistory();h.start('a');assert h.aggression(4)==(.25,0)
    events=[dict(seat=4,phase='flop',action='raise')]
    h.record(1,events);h.record(1,events);assert h.aggression(4)==(3/9,1)
    h.start('a');assert h.aggression(4)[1]==1
    h.start('b');assert h.aggression(4)==(.25,0)

def test_stack_router_and_metadata_fallback():
    v=view();assert ashwing_v4.specialist(v)[1]==100
    assert load_strategy('Ashwing_V4') is ashwing_v4.decide
    a,b=Random(73),Random(73);v=replace(v,public_players=())
    name,_=ashwing_v4.specialist(v)
    assert ashwing_v4.decide(v,a)==ashwing_v4.expert(name,v,b,None)

def test_bad_commitments_refuse_model():
    v=view();people=list(v.public_players);people[0]=replace(people[0],total_bet=people[0].total_bet+1)
    assert analyse(replace(v,public_players=tuple(people)),Random(71))=={'supported':False,'reason':'commitment_mismatch'}
