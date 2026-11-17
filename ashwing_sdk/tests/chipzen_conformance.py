import asyncio
import json
from pathlib import Path
import sys

from chipzen import Card, GameState
from chipzen.conformance import (
  _drive_session, _match_end, _match_start, _round_start, _server_hello, _turn_request,
  run_conformance_checks,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chipzen_entry import ASHWING, ASHWING_SEARCH, ASHWING_V2, CompetitionBot, bot_for_strategy, observation
from pokerbots_sdk.ashwing_policy import decide as ashwing_decide
from pokerbots_sdk.hive_policy import hive_mind
from pokerbots_sdk import TOOLKIT_STRATEGIES



def entry(seat, action, amount=0, phase="preflop"):
  return dict(seat=seat, action=action, amount=amount, phase=phase, is_timeout=False)


async def check_holdem_tables(name):
  for size in range(2, 7):
    match = _match_start()
    match["seats"] = [
      dict(seat=seat, participant_id=f"p{seat}", display_name=f"Seat {seat}", is_self=seat == 0)
      for seat in range(size)
    ]
    match["game_config"]["num_players"] = size
    hand = _round_start()
    turn = _turn_request()
    if size == 2:
      dealer, stacks = 0, [995, 990]
      history = [entry(0, "post_small_blind", 5), entry(1, "post_big_blind", 10)]
    else:
      dealer = size - 3
      sb, bb = size - 2, size - 1
      stacks = [1000] * size
      stacks[sb], stacks[bb] = 995, 990
      history = [entry(sb, "post_small_blind", 5), entry(bb, "post_big_blind", 10)]
    hand["state"].update(dealer_seat=dealer, stacks=stacks, your_hole_cards=["Ah", "Ad"])
    turn["state"].update(your_hole_cards=["Ah", "Ad"], your_stack=stacks[0],
      opponent_stacks=stacks[1:], to_call=5 if size == 2 else 10, max_raise=1000, action_history=history)
    end = _match_end(seq=5)
    script = [_server_hello(), match, hand, turn, end]
    socket, error = await _drive_session(bot_for_strategy(name, seed=42), script, timeout_s=3)
    assert error is None, f"{size}-max session failed: {error}"
    actions = [message for raw in socket.sent if (message := json.loads(raw))["type"] == "turn_action"]
    assert len(actions) == 1, (size, actions)
    action = actions[0]
    assert action["request_id"] == turn["request_id"]
    assert action["action"] == "raise" and 20 <= action["params"]["amount"] <= 1000, (size, action)
    print(f"{name}: pass: {size}-max hosted protocol raises with pocket aces")


def check_multiway_observation(strategy, method="Hive Mind"):
  state = GameState(
    hole_cards=[Card.from_str(raw) for raw in ("Ah", "Ad")],
    board=[Card.from_str(raw) for raw in ("Ac", "7d", "2s")],
    phase="flop", pot=105, your_stack=970, your_seat=3, dealer_seat=4,
    opponent_stacks=[0, 2000, 65, 80, 5000], to_call=20, min_raise=40, max_raise=970,
    valid_actions=["fold", "call", "raise"],
    action_history=[
      entry(5, "post_small_blind", 5), entry(1, "post_big_blind", 10),
      entry(2, "call", 10), entry(3, "raise", 30), entry(4, "call", 30),
      entry(5, "fold"), entry(1, "fold"), entry(2, "fold"),
      entry(4, "raise", 20, "flop"),
    ],
  )
  view = observation(state, 10)
  assert view.opponents == 1 and not view.has_all_in_opponent
  assert view.late_position and view.effective_raise_total == 100
  assert len(view.stacks) == 5
  assert [step.amount for step in view.betting_line if step.opponent] == [30, 20]
  if method is not None:
    diagnostics = {}
    strategy(view, CompetitionBot(seed=42).rng, diagnostics=diagnostics)
    assert diagnostics["method"] == method
  else:
    result = CompetitionBot(seed=42, strategy=strategy).decide(state)
    assert result.action in state.valid_actions, result
  state.opponent_stacks[2] = 0
  state.action_history.pop(-2)  # Seat 2 is still contesting the pot all-in.
  view = observation(state, 10)
  assert view.opponents == 2 and view.has_all_in_opponent and view.effective_raise_total == 100
  result = CompetitionBot(seed=42, strategy=strategy).decide(state)
  assert result.action in state.valid_actions, result
  print(f"{method or ASHWING}: pass: folded and busted seats, all-in contenders, and heads-up transition")


def check_v2_gate():
  bot = bot_for_strategy(ASHWING_V2, seed=42)
  match = {"match_id": "first", "game_config": {"big_blind": 100}, "seats": [
    {"seat": 0, "is_self": True}, {"seat": 1, "is_self": False}]}
  bot.on_match_start(match)
  history = [entry(0, "post_small_blind", 50), entry(1, "post_big_blind", 100),
    entry(0, "call", 50), entry(0, "raise", 100, "flop"), entry(1, "call", 100, "flop"),
    entry(0, "raise", 300, "turn"), entry(1, "call", 300, "turn")]
  state = GameState(
    hole_cards=[Card.from_str(card) for card in ("Ac", "Ah")],
    board=[Card.from_str(card) for card in ("As", "7d", "2c", "7h", "2d")],
    phase="river", pot=1000, your_stack=9500, your_seat=0, dealer_seat=0,
    opponent_stacks=[9500], to_call=0, min_raise=100, max_raise=9500,
    valid_actions=["check", "raise"], action_history=history)
  assert bot.choose(observation(state, 100)) == ("raise", 720)
  public = history + [entry(0, "raise", 720, "river"), entry(1, "call", 720, "river")]
  for hand in range(6):
    message = {"round_id": f"r_{hand}", "result": {"action_history": public}}
    bot.on_round_result(message)
    bot.on_round_result(message)
  timed_out = history + [entry(0, "raise", 720, "river"),
    {**entry(1, "fold", phase="river"), "is_timeout": True}]
  bot.on_round_result({"round_id": "timeout", "result": {"action_history": timed_out}})
  assert len(bot.histories[1].responses) == 6
  bot.on_reconnected(match)
  assert bot.choose(observation(state, 100)) == ("raise", 1500)
  bot.on_match_start({**match, "match_id": "second"})
  assert bot.choose(observation(state, 100)) == ("raise", 720)
  print("Ashwing v2: pass: public river learning, duplicate and timeout handling, reconnect, match reset")


def main(names=()):
  ok = True
  for name in names or TOOLKIT_STRATEGIES:
    results = run_conformance_checks(bot_for_strategy(name, seed=42), timeout_s=3)
    for result in results:
      print(f"{name}: {result.severity}: {result.name}: {result.message}")
    ok = ok and bool(results) and all(result.severity == "pass" for result in results)
    if name in ("Hive Mind", ASHWING_V2, ASHWING_SEARCH, ASHWING):
      strategies = {ASHWING: ashwing_decide, ASHWING_V2: hive_mind}
      strategy = strategies[name] if name in strategies else TOOLKIT_STRATEGIES[name]
      asyncio.run(check_holdem_tables(name))
      check_multiway_observation(strategy, method=None if name == ASHWING else "Hive Mind")
    if name == ASHWING_V2:
      check_v2_gate()
  return 0 if ok else 1


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
