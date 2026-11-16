from dataclasses import replace
from random import Random

from pokerbots_sdk import Observation, load_strategy, validate_decision
from pokerbots_sdk.adaptive_policy import TITLE, ashwing_adaptive, wager_ev
from pokerbots_sdk.betting_line import holding
from pokerbots_sdk.hive_policy import adaptive_river_value_pressure, hive_mind
from pokerbots_sdk.river_calls import RiverCallHistory
from pokerbots_sdk.model import LineAction
from river_experiment import cards


def river_view(hole, board, pot, amount, line, *, big_blind=100, shove=False):
  stack = amount if shove else 8000
  return Observation(
    hole=cards(hole), board=cards(board), stack=stack,
    stacks=((0, stack), (1, 0 if shove else 8000)), current_bet=0,
    table_bet=amount, big_blind=big_blind, pot=pot + amount, late_position=True,
    opponents=1, effective_raise_total=0 if shove else 8000, has_all_in_opponent=shove,
    legal={"call": True, "check": False, "fold": True, "raise": not shove,
      "call_amount": amount, "min_raise_total": 2 * amount, "max_raise_total": stack},
    betting_line=tuple(LineAction(*step) for step in
      (*line, (True, "river", "raise", amount, pot))))


def opening(hole, board):
  view = river_view(hole, board, 1000, 0, ())
  return replace(view, betting_line=(), legal={
    **view.legal, "call": False, "check": True, "fold": False, "min_raise_total": 100,
  })


def callers():
  history = RiverCallHistory()
  for _ in range(16):
    history.record(700, 1000, "call")
  return history


def test_adaptive_uses_public_call_history_to_unlock_extra_value_sizes():
  view = opening("As Ks", "Qs Js 2s 4h 7d")
  cold, warm = RiverCallHistory(), callers()
  strategy = load_strategy(TITLE)
  assert strategy(view, Random(7), history=cold) == adaptive_river_value_pressure(view, Random(7), cold)
  assert strategy(view, Random(7), history=warm) == ("raise", 1500)
  view = replace(view, effective_raise_total=900)
  action = strategy(view, Random(7), history=warm)
  assert action == ("raise", 900)
  validate_decision(view, *action)


def test_adaptive_preserves_v2_defense_and_weak_river_holdings():
  view = river_view("As Ks", "Qs Js 2s 4h 7d", 1000, 1400, ())
  history = callers()
  assert ashwing_adaptive(view, Random(7), history=history) == hive_mind(view, Random(7))
  view = opening("4d 5c", "Qs Js 2s 4h 7d")
  assert ashwing_adaptive(view, Random(7), history=history) == adaptive_river_value_pressure(view, Random(7), history)


def test_wager_ev_includes_raises_and_terminal_showdown():
  board = cards("Qs Js 2s 4h 7d")
  strong = holding(cards("9s 8s"), board)
  outcomes = [(strong, 1., 1.)]
  assert wager_ev(outcomes, 1000, 500, 1.) == 1500
  assert wager_ev(outcomes, 1000, 500, 0.) < 1000
