from dataclasses import replace
from random import Random

from arena import observe
import ashwing_policy
from poker_engine import start_game
from pokerbots_sdk.model import validate_decision


def test_trained_checkpoint_selects_a_legal_shallow_action(monkeypatch):
  def unexpected_baseline(*args, **kwargs):
    raise AssertionError("expected a supported checkpoint bucket")

  monkeypatch.setattr(ashwing_policy, "hive_mind", unexpected_baseline)
  game = start_game(2, 40, 5, 10, deck_rng=Random(1))
  player = game.players[game.current_player]
  view = observe(game, player)
  action, target = ashwing_policy.decide(view, Random(1))
  validate_decision(view, action, target)


def test_hybrid_dispatches_to_v2_at_deeper_stacks_and_on_river(monkeypatch):
  game = start_game(2, 100, 5, 10, deck_rng=Random(1))
  view = observe(game, game.players[game.current_player])
  monkeypatch.setattr(ashwing_policy, "_buckets", lambda: (_ for _ in ()).throw(
    AssertionError("checkpoint must not load at this depth")))
  monkeypatch.setattr(ashwing_policy, "hive_mind", lambda *_: ("call", None))
  history = object()
  calls = []

  def adaptive(received_view, rng, received_history):
    calls.append((received_view, received_history))
    return "check", None

  monkeypatch.setattr(ashwing_policy, "adaptive_river_value_pressure", adaptive)
  assert ashwing_policy.decide(view, Random(1)) == ("call", None)
  river = replace(view, board=(("2", "s"),) * 5)
  assert ashwing_policy.decide(river, Random(1), history=history) == ("check", None)
  assert calls == [(river, history)]
