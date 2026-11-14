from random import Random

from arena import observe
from poker_engine import start_game
from pokerbots_sdk import load_strategy, validate_decision
from pokerbots_sdk.champion_policy import TITLE, roster, selection


def test_champion_dispatches_to_verified_entrants():
  policy = load_strategy(TITLE)
  report = selection()
  entrants = roster()
  assert TITLE not in entrants
  for mode, count in (("heads_up", 2), ("multiway", 5)):
    section = report[mode]
    assert set(entrants) == {row["name"] for row in section["leaderboard"]}
    if section["selected"] != section["incumbent"]:
      assert section["incumbent_edge"]["interval_95"][0] > 0
    game = start_game(count, deck_rng=Random(14))
    view = observe(game, game.players[game.current_player])
    expected = entrants[section["selected"]](view, Random(42))
    action = policy(view, Random(42))
    assert action == expected
    validate_decision(view, *action)
