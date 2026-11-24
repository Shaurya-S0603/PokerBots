from chipzen import Card,GameState
from chipzen_entry import observation,bot_for_strategy
def entry(seat,action,amount=0,phase='preflop'):
    return dict(seat=seat,action=action,amount=amount,phase=phase,is_timeout=False)
def state():
    return GameState(hole_cards=[Card.from_str(c) for c in ('Ah','Qh')],board=[Card.from_str(c) for c in ('Kh','8h','2s')],phase='flop',pot=170,your_stack=950,your_seat=0,dealer_seat=0,opponent_stacks=[880],to_call=70,min_raise=140,max_raise=950,valid_actions=['fold','call','raise'],action_history=[entry(0,'post_small_blind',5),entry(1,'post_big_blind',10),entry(0,'raise',50),entry(1,'call',40),entry(1,'raise',70,'flop')])
def test_hosted_commitments_and_legal_decision():
    v=observation(state(),10)
    assert [p.total_bet for p in v.public_players]==[50,120]
    assert [p.current_bet for p in v.public_players]==[0,70]
    assert v.public_line[-1].pot_before==100
    bot=bot_for_strategy('Ashwing_V4',seed=819);bot.on_match_start({'match_id':'a','seats':[{'seat':0,'is_self':True}]})
    assert bot.decide(state()).action in state().valid_actions
def test_v4_reconnect_results_dedup_and_scope():
    bot=bot_for_strategy('Ashwing_V4',seed=8);match={'match_id':'a','seats':[{'seat':0,'is_self':True}]};bot.on_match_start(match)
    result={'round_id':'r1','result':{'action_history':[entry(1,'raise',70,'flop')]}}
    bot.on_round_result(result);bot.on_round_result(result)
    assert bot.public_history.aggression(1)[1]==1
    bot.on_reconnected(match);assert bot.public_history.aggression(1)[1]==1
    bot.on_match_start({**match,'match_id':'b'});assert bot.public_history.aggression(1)[1]==0
