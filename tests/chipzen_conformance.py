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
from chipzen_entry import CompetitionBot, observation
from pokerbots_sdk import TOOLKIT_STRATEGIES



def entry(seat, action, amount=0, phase="preflop"):
  return dict(seat=seat, action=action, amount=amount, phase=phase, is_timeout=False)


async def check_holdem_tables(strategy):
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
    socket, error = await _drive_session(CompetitionBot(seed=42, strategy=strategy), script, timeout_s=3)
    assert error is None, f"{size}-max session failed: {error}"
    actions = [message for raw in socket.sent if (message := json.loads(raw))["type"] == "turn_action"]
    assert len(actions) == 1, (size, actions)
    action = actions[0]
    assert action["request_id"] == turn["request_id"]
    assert action["action"] == "raise" and 20 <= action["params"]["amount"] <= 1000, (size, action)
    print(f"Hive Mind: pass: {size}-max hosted protocol raises with pocket aces")


def check_multiway_observation(strategy):
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
  diagnostics = {}
  strategy(view, CompetitionBot(seed=42).rng, diagnostics=diagnostics)
  assert diagnostics["method"] == "Hive Mind"
  state.opponent_stacks[2] = 0
  state.action_history.pop(-2)  # Seat 2 is still contesting the pot all-in.
  view = observation(state, 10)
  assert view.opponents == 2 and view.has_all_in_opponent and view.effective_raise_total == 100
  result = CompetitionBot(seed=42, strategy=strategy).decide(state)
  assert result.action in state.valid_actions, result
  print("Hive Mind: pass: folded and busted seats, all-in contenders, and heads-up transition")


def main(names=()):
  ok = True
  for name in names or TOOLKIT_STRATEGIES:
    strategy = TOOLKIT_STRATEGIES[name]
    results = run_conformance_checks(CompetitionBot(strategy=strategy, seed=42), timeout_s=3)
    for result in results:
      print(f"{name}: {result.severity}: {result.name}: {result.message}")
    ok = ok and bool(results) and all(result.severity == "pass" for result in results)
    if name == "Hive Mind":
      asyncio.run(check_holdem_tables(strategy))
      check_multiway_observation(strategy)
  return 0 if ok else 1


if __name__ == "__main__":
  raise SystemExit(main(sys.argv[1:]))
