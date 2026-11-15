import json

from poker_engine import start_game
from ui.replay import export_history, record_step, start_record
from ui.session import action_event


def test_replay_exports_all_in_runout_and_only_showdown_cards():
  game = start_game(3, 100)
  record = start_record(game.get_state(1), {1: 100, 2: 100, 3: 100})
  assert all(not seat["hole_cards"] for seat in record["steps"][0]["table"]["players"])
  assert json.loads(export_history({1: record}))["hands"] == []

  for player, action in zip(game.players, ["all_in", "fold", "call"]):
    before = game.get_state()
    assert getattr(game, action)(player)
    record_step(record, game.get_state(2), action_event(action, player.player_id, before, player))

  hand, = json.loads(export_history({1: record}))["hands"]
  steps = hand["steps"]
  assert [step["action"]["action"] for step in steps[1:]] == ["all_in", "fold", "call"]
  assert [change["street"] for change in steps[-1]["board_changes"]] == ["Flop", "Turn", "River"]
  assert all(not seat["hole_cards"] for step in steps[:-1] for seat in step["table"]["players"])
  final = steps[-1]["table"]
  assert [seat["stack"] for seat in final["players"]] == [player.stack for player in game.players]
  assert [seat["player_id"] for seat in final["players"] if seat["hole_cards"]] == [1, 3]
  assert "deck" not in final
  assert sum(pot["amount"] for pot in final["pot_results"]) == 205
