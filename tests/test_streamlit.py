from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def button(app, label):
  return next(item for item in app.button if item.label == label)


def test_setup_controls_follow_player_count_and_mode_before_dealing():
  app = AppTest.from_file(str(APP_PATH)).run()
  assert app.radio[0].options == ["Local Pass-and-Play", "Human vs Ashwing"]
  app.radio[0].set_value("Human vs Ashwing").run()
  assert app.slider[0].value == 2
  assert app.slider[0].max == 6
  assert [item.label for item in app.text_input] == ["Your name"]
  button(app, "Deal the first hand").click().run()
  assert not app.exception
  assert app.session_state.player_names == {1: "You", 2: "Ashwing"}
  assert len(app.session_state.game.players) == 2


def test_pass_and_play_resume_hides_cards_and_reruns_do_not_pay_twice():
  app = AppTest.from_file(str(APP_PATH)).run()
  app.slider[0].set_value(2).run()
  button(app, "Deal the first hand").click().run()
  button(app, "Reveal my cards").click().run()
  first_fold_key = button(app, "Fold").key
  button(app, "Main menu").click().run()
  button(app, "Resume current game").click().run()
  assert all("Your private hole cards" not in item.value for item in app.markdown)
  button(app, "Reveal my cards").click().run()
  button(app, "Fold").click().run()

  stacks = [player.stack for player in app.session_state.game.players]
  assert stacks == [995, 1005]
  assert len(app.session_state.history) == 1
  app.run().run()
  assert [player.stack for player in app.session_state.game.players] == stacks
  assert len(app.session_state.history) == 1
  assert {stats["hands"] for stats in app.session_state.stats.values()} == {1}

  second_session = AppTest.from_file(str(APP_PATH)).run()
  assert second_session.session_state.game is None
  assert second_session.session_state.history == []
  button(app, "Next hand").click().run()
  button(app, "Reveal my cards").click().run()
  assert not app.exception
  assert app.session_state.game.hand_number == 2
  assert button(app, "Fold").key != first_fold_key


def test_pot_preset_commits_only_additional_chips():
  app = AppTest.from_file(str(APP_PATH)).run()
  app.slider[0].set_value(2).run()
  button(app, "Deal the first hand").click().run()
  button(app, "Reveal my cards").click().run()
  button(app, "Pot 30").click().run()
  assert not app.exception
  game = app.session_state.game
  assert game.table_bet == 30
  assert game.players[0].stack == 970
  assert app.session_state.history[-1]["amount"] == 25


def test_paced_bot_waits_then_commits_one_action_per_turn():
  app = AppTest.from_file(str(APP_PATH)).run()
  app.radio[0].set_value("Human vs Ashwing").run()
  app.slider[0].set_value(3).run()
  button(app, "Deal the first hand").click().run()
  button(app, "Fold").click().run()
  assert not app.exception
  assert len(app.session_state.history) == 1
  turn, delay, _ = app.session_state.bot_due
  app.session_state.bot_due = (turn, delay, 0)
  app.run()
  assert not app.exception
  assert len(app.session_state.history) == 2
  assert app.session_state.history[-1]["player_id"] == 2


def test_benchmarks_open_with_bundled_results():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Bot benchmarks").click().run()
  assert not app.exception
  assert not app.error
  rows = app.dataframe[0].value
  assert set(rows["Opponent"]) == {"Calling Station", "Random", "Tight", "Loose-Aggressive"}
  assert (rows["Hands"] == 200).all()
  assert (rows["Illegal actions"] == 0).all()
  button(app, "Back to menu").click().run()
  assert button(app, "Deal the first hand")


def test_ashwing_turn_does_not_depend_on_the_arena_registry(monkeypatch):
  import arena

  app = AppTest.from_file(str(APP_PATH)).run()
  app.radio[0].set_value("Human vs Ashwing").run()
  app.slider[0].set_value(3).run()
  button(app, "Deal the first hand").click().run()
  assert app.session_state.player_names == {1: "You", 2: "Ashwing 1", 3: "Ashwing 2"}
  monkeypatch.delitem(arena.TOOLKIT_STRATEGIES, "Hive Mind")
  monkeypatch.delitem(arena.STRATEGIES, "Hive Mind")
  app.session_state.bot_pacing = "Instant"
  button(app, "Fold").click().run()
  assert not app.exception
  assert app.session_state.bot_error is None
  assert any(event["player_id"] == 2 for event in app.session_state.history)
  assert any(turn.get("model") == "Ashwing"
    for turns in app.session_state.bot_simulations.values() for turn in turns)
  button(app, "Bot visualization").click().run()
  assert not app.exception
  assert app.session_state.screen == "visualization"
  button(app, "Back to table").click().run()
  assert app.session_state.screen == "table"


def test_move_clock_stays_off_until_private_reveal_and_folds_once_on_expiry():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Pass-and-play").click().run()
  assert app.session_state.turn_clock is None
  button(app, "Reveal my cards").click().run()
  turn, _ = app.session_state.turn_clock
  assert any('role="timer"' in item.value for item in app.markdown)
  app.session_state.turn_clock = (turn, 0)
  button(app, "Call 5").click().run()
  assert not app.exception
  assert [event["action"] for event in app.session_state.history] == ["fold"]
  app.run()
  assert len(app.session_state.history) == 1
  assert not app.session_state.chat


def test_expired_free_action_checks_and_ashwing_chat_survives_reruns():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Pass-and-play").click().run()
  button(app, "Reveal my cards").click().run()
  button(app, "Call 5").click().run()
  button(app, "Reveal my cards").click().run()
  turn, _ = app.session_state.turn_clock
  app.session_state.turn_clock = (turn, 0)
  app.run()
  assert [event["action"] for event in app.session_state.history] == ["call", "check"]
  assert app.session_state.game.phase == "flop"
  button(app, "Main menu").click().run()
  button(app, "Play Ashwing").click().run()
  first_line = list(app.session_state.chat)
  app.run()
  assert len(first_line) == 1 and app.session_state.chat == first_line
  button(app, "Fold").click().run()
  assert len(app.session_state.chat) == 2


def test_poker_puzzle_has_feedback():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Poker puzzles").click().run()
  app.radio[0].set_value("25%")
  button(app, "Check answer").click().run()
  assert app.success
