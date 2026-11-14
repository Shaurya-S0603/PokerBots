from dataclasses import replace
from random import Random

import pytest

from arena import observe
from equity import exact_river_equity, sample_equity
from poker_engine import start_game
from pokerbots_sdk.betting_line import evaluate_range
from pokerbots_sdk.model import LineAction
from pokerbots_sdk.strategies import heads_up_preflop
from river_experiment import LINE_FIXTURES, LINE_STRATEGIES, cards, fixture_decisions


def test_public_line_exposes_call_and_raise_totals_then_resets():
  game = start_game(2)
  button, blind = game.players
  assert game.call(button)
  assert game.raise_bet(blind, 20)
  assert observe(game, button).betting_line == (
    LineAction(False, "preflop", "call", 5, 15),
    LineAction(True, "preflop", "raise", 30, 20))
  assert game.fold(button)
  assert game.start_next_round()
  assert not observe(game, game.players[game.current_player]).betting_line


def test_sampling_keeps_uniform_draws_and_reweights_only_observed_actions():
  game = start_game(2)
  state = replace(observe(game, game.players[0]), hole=cards("Ks 7s"), board=cards("9c 6h Ac 8h"))
  standard = sample_equity(state.hole, state.board, 1, 128, Random(7))
  result, weighted, _ = evaluate_range(state, Random(7), 128)
  assert result == standard
  assert weighted == pytest.approx(standard.equity)
  state = replace(state, board=state.board + cards("4c"), betting_line=(
    LineAction(True, "flop", "raise", 396, 600),
    LineAction(True, "river", "raise", 2130, 3228)))
  result, weighted, _ = evaluate_range(state, Random(7), 128)
  assert result == exact_river_equity(state.hole, state.board)
  assert weighted < result.equity


def test_sizing_regressions_and_private_two_pair_value():
  decisions = {(row["opponent"], row["hand"]): row["decisions"]["Range + Sizing"]
    for row in fixture_decisions(LINE_FIXTURES, LINE_STRATEGIES)}
  for key in [("Plodder8", 26), ("fledge", 25)]:
    assert decisions[key]["action"] == "check"
    assert len(decisions[key]["bet_options"]) == 3
  for key in [("pebble", 87), ("PluriBot", 5)]:
    assert decisions[key]["action"] == "raise"


def test_preflop_uses_position_and_depth():
  for stack, target in [(150, 20), (1000, 25)]:
    game = start_game(2, starting_chips=stack)
    button, blind = game.players
    button.hole_cards = list(cards("As Kd"))
    assert heads_up_preflop(observe(game, button), Random(0)) == ("raise", target)
    assert game.call(button)
    assert game.raise_bet(blind, 50)
    button.hole_cards = list(cards("7s 2d"))
    diagnostics = {}
    assert heads_up_preflop(observe(game, button), Random(0), diagnostics=diagnostics) == ("fold", None)
    assert diagnostics["decision_basis"] == "Button facing raise after limp"


def test_preflop_ablations_only_change_their_target_decisions():
  from pokerbots_sdk.strategies import big_blind_defense_only, button_open_only, range_and_sizing

  game = start_game(2)
  button, blind = game.players
  button.hole_cards = list(cards("As Kd"))
  unopened = observe(game, button)
  assert button_open_only(unopened, Random(0)) == ("raise", 25)
  assert big_blind_defense_only(unopened, Random(0)) == range_and_sizing(unopened, Random(0))

  assert game.raise_bet(button, 20)
  blind.hole_cards = list(cards("7s 2d"))
  opened = observe(game, blind)
  assert big_blind_defense_only(opened, Random(0)) == ("fold", None)
  assert button_open_only(opened, Random(0)) == range_and_sizing(opened, Random(0))
  assert game.raise_bet(blind, 50)
  reraised = observe(game, button)
  for strategy in (button_open_only, big_blind_defense_only):
    assert strategy(reraised, Random(0)) == range_and_sizing(reraised, Random(0))
