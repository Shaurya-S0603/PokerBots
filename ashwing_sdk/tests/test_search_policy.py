from random import Random

from arena import observe
from ashwing_v2_validation import game_for
from pokerbots_sdk import validate_decision
from pokerbots_sdk.adaptive_policy import ashwing_adaptive
from pokerbots_sdk.search_policy import ashwing_search, limp_bucket


def test_search_switches_only_big_blind_response_to_limp(monkeypatch):
  game, _ = game_for(123, 100)
  opening = observe(game, game.players[0])
  assert ashwing_search(opening, Random(1)) == ashwing_adaptive(opening, Random(1))
  assert game.call(game.players[0])
  view = observe(game, game.players[1])
  depth, _ = limp_bucket(view)
  assert depth == 100
  monkeypatch.setattr("pokerbots_sdk.search_policy.blind_blueprint", lambda: {"100": [4, 4, 4]})
  action = ashwing_search(view, Random(1))
  assert action == ("raise", 400)
  validate_decision(view, *action)
