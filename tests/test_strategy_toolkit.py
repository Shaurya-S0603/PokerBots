from random import Random

import pytest

from arena import BotArena, equity_bot, observe
from poker_engine import start_game
from pokerbots_sdk import button_pressure, load_strategy, validate_decision, value
from pokerbots_sdk.equity_policy import EquityProfile
from pokerbots_sdk.strategies import VALUE_PROFILE
from strategy_matchup import compare_strategies


def test_arena_and_toolkit_value_submit_the_same_decision():
  arena = BotArena(81, ["Value", "Button Pressure"])
  game = start_game(2, deck_rng=arena.deck_rng)
  player = game.players[game.current_player]
  view = observe(game, player)
  rng = Random()
  rng.setstate(arena.bot_rngs[player.player_id - 1].getstate())
  expected = value(view, rng)
  rng.setstate(arena.bot_rngs[player.player_id - 1].getstate())
  assert expected == equity_bot(view, rng, profile=VALUE_PROFILE)
  action, ok = arena.act(game, player)
  assert ok and action == expected[0]
  if action == "raise":
    assert player.current_bet == expected[1]


def test_custom_strategy_can_be_loaded_and_used_at_an_arena_seat():
  strategy = load_strategy("baseline_v4:calling_station")
  arena = BotArena(42, ["My bot", "Value"], strategies={"My bot": strategy})
  game = start_game(2, deck_rng=arena.deck_rng)
  assert arena.act(game, game.players[0]) == ("call", True)


def test_raise_target_is_a_total_and_plain_actions_reject_an_amount():
  game = start_game(2)
  view = observe(game, game.players[0])
  validate_decision(view, "raise", view.legal["min_raise_total"])
  with pytest.raises(ValueError, match="raise target"):
    validate_decision(view, "raise", view.legal["min_raise_total"] - 1)
  with pytest.raises(ValueError, match="Only a raise"):
    validate_decision(view, "call", 5)


def test_button_pressure_and_value_can_play_a_paired_matchup():
  assert load_strategy("Button Pressure") is button_pressure
  assert VALUE_PROFILE != EquityProfile()
  report = compare_strategies("Button Pressure", "Value", seed=27000, pairs=2, stack=1000, workers=1)
  assert report["hands"] == 4
  assert report["pairs"] == 2


def test_pot_guard_tightens_only_against_large_heads_up_postflop_bets(monkeypatch):
  from dataclasses import replace
  from pokerbots_sdk import strategies

  game = start_game(2)
  state = observe(game, game.players[0])
  captured = []
  def decision(state, rng, *, profile, diagnostics):
    captured.append(profile)
    return "fold", None

  monkeypatch.setattr(strategies, "equity_bot", decision)
  strategy = load_strategy("Pot Guard")
  strategy(state, Random(1))
  flop = replace(state, board=(("2", "♣️"), ("3", "♣️"), ("4", "♣️")), pot=90)
  for call in (10, 30):
    strategy(replace(flop, legal={**flop.legal, "call_amount": call}), Random(1))
  assert captured[:2] == [VALUE_PROFILE, VALUE_PROFILE]
  assert captured[2].call_cushion > VALUE_PROFILE.call_cushion
  assert captured[2].river_call_margin > VALUE_PROFILE.river_call_margin
