from dataclasses import replace
from random import Random

from arena import BotArena, calling_station, loose_aggressive, observe, tight
from poker_engine import GameManager, Player, start_game


def test_calling_station_checks_calls_and_commits_a_short_stack():
  arena = BotArena(42, ["Calling Station"] * 2)
  game = start_game(2, deck_rng=arena.deck_rng)
  assert arena.act(game, game.players[0]) == ("call", True)
  assert arena.act(game, game.players[1]) == ("check", True)
  short = GameManager([Player(1, 7), Player(2, 100)], deck_rng=arena.deck_rng)
  assert short.start_round()
  assert calling_station(observe(short, short.players[0]), Random(1)) == ("call", None)
  assert arena.act(short, short.players[0]) == ("call", True)
  assert short.players[0].total_bet == 7 and short.hand_over


def test_seed_reproduces_a_mixed_match_and_every_decision_is_legal():
  def match(seed):
    arena = BotArena(seed, ["Random", "Calling Station", "Tight", "Loose-Aggressive"])
    game = start_game(4, 120, deck_rng=arena.deck_rng)
    trace = []
    for _ in range(1000):
      if game.hand_over:
        trace.append(game.get_state())
        if game.game_over or game.hand_number == 12:
          return trace
        dealer = game.dealer_index
        assert game.start_next_round()
        assert game.dealer_index != dealer
        continue
      player = game.players[game.current_player]
      action, ok = arena.act(game, player)
      assert ok, (action, game.last_error)
      assert sum(p.stack for p in game.players) + game.pot == 480
      trace.append((player.player_id, action, game.table_bet))
    raise AssertionError("The match did not finish within the test budget")

  for seed in range(20):
    assert match(seed) == match(seed)


def test_tight_and_loose_strategies_differ_in_the_expected_spots():
  game = start_game(2)
  actor = game.players[game.current_player]
  view = observe(game, actor)
  rng = Random(5)
  weak = replace(view, hole=(("7", "♣️"), ("2", "♥️")))
  assert tight(weak, rng) == ("fold", None)
  assert tight(replace(weak, legal={**weak.legal, "check": True}), rng) == ("check", None)
  assert tight(replace(view, hole=(("A", "♣️"), ("A", "♥️"))), rng)[0] == "raise"
  suited = replace(view, hole=(("8", "♣️"), ("7", "♣️")))
  assert tight(suited, rng)[0] == "fold"
  assert loose_aggressive(suited, rng)[0] == "raise"
  shared_pair = replace(weak, board=(("K", "♣️"), ("K", "♥️"), ("4", "♥️")))
  assert tight(shared_pair, rng)[0] == "fold"
  trips = replace(shared_pair, hole=(("K", "♠️"), ("2", "♥️")))
  assert tight(trips, rng)[0] == "raise"


def test_equity_strategy_cannot_see_hidden_cards_and_uses_a_legal_raise():
  from arena import equity_bot

  game = start_game(2)
  actor = game.players[game.current_player]
  opponent = next(player for player in game.players if player is not actor)
  actor.hole_cards = [("A", "♣️"), ("A", "♥️")]
  before = observe(game, actor)
  opponent.hole_cards = [("K", "♣️"), ("Q", "♦️")]
  after = observe(game, actor)
  assert before == after
  action, target = equity_bot(before, Random(12))
  assert (action, target) == equity_bot(after, Random(12))
  assert action == "raise"
  assert before.legal["min_raise_total"] <= target <= before.effective_raise_total


def test_equity_arena_opens_playable_hands_outside_the_blinds():
  arena = BotArena(8, ["Equity"] * 10)
  game = start_game(10, 500, deck_rng=arena.deck_rng)
  player = game.players[game.current_player]
  assert game.current_player not in {game.sb_index, game.bb_index}
  player.hole_cards = [("K", "♣️"), ("K", "♥️")]
  trace = {}
  assert arena.act(game, player, diagnostics=trace) == ("raise", True)
  assert game.table_bet == 25
  assert trace["decision_basis"] == "Preflop opening range"

  player = game.players[game.current_player]
  player.hole_cards = [("7", "♣️"), ("2", "♥️")]
  trace = {}
  assert arena.act(game, player, diagnostics=trace) == ("fold", True)
  assert "decision_basis" not in trace
