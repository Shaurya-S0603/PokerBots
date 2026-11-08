from poker_bot import PokerBot
from poker_engine import start_game


def test_game_starts_for_supported_player_counts():
  for count in (2, 5, 10):
    game = start_game(count)
    state = game.get_state()
    assert len(state["players"]) == count
    assert state["phase"] == "preflop"
    assert state["pot"] == game.small_blind + game.big_blind


def test_public_state_hides_private_cards():
  game = start_game(3)
  public = game.get_state()
  private = game.get_state(1)
  assert all(not item["hole_cards"] for item in public["players"])
  assert len(next(item for item in private["players"] if item["player_id"] == 1)["hole_cards"]) == 2


def test_bot_uses_a_legal_action():
  game = start_game(3)
  player = game.players[game.current_player]
  action, succeeded = PokerBot("Medium").act(game, player)
  assert action in {"fold", "check", "call", "raise", "all_in"}
  assert succeeded
