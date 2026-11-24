from random import Random

from arena import observe
from ashwing_policy import decide
from poker_engine import start_game
from pokerbots_sdk import ashwing_policy, ashwing_v4
from pokerbots_sdk.model import validate_decision


def test_streamlit_uses_the_shared_benchmarked_policy():
  assert decide is ashwing_v4.decide


def test_preflop_dispatch_respects_the_effective_stack_and_player_count(monkeypatch):
  calls = []

  def shallow(view, rng, control, details):
    calls.append(view)
    return control

  monkeypatch.setattr(ashwing_policy, "short_stack", shallow)
  for players, stack, uses_shallow in ((2, 40, True), (2, 100, True),
                                        (2, 110, False), (3, 40, False)):
    game = start_game(players, stack, 5, 10, deck_rng=Random(1))
    view = observe(game, game.players[game.current_player])
    calls.clear()
    action, target = decide(view, Random(1))
    validate_decision(view, action, target)
    assert calls == ([view] if uses_shallow else [])
