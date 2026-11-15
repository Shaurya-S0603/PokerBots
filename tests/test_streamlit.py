import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def button(app, label):
  return next(item for item in app.button if item.label == label)


def deal(app):
  button(app, "Deal the first hand").click().run()
  assert app.session_state.screen == "dealing"
  assert any("Dealing you in" in item.value for item in app.markdown)
  app.session_state.deal_ready_at = 0
  app.run()
  assert not app.exception
  assert app.session_state.screen == "table"


def test_mode_selection_opens_setup_and_deals_only_after_loading():
  app = AppTest.from_file(str(APP_PATH)).run()
  assert {item.label for item in app.button} == {"Play Ashwing", "Pass-and-play"}
  assert not app.slider
  button(app, "Play Ashwing").click().run()
  assert app.session_state.screen == "setup"
  assert app.session_state.game is None
  assert app.slider[0].value == 2
  assert app.slider[0].max == 6
  assert [item.label for item in app.text_input] == ["Your name"]
  app.text_input[0].set_value("Shaun")
  app.number_input[0].set_value(1600)
  app.number_input[1].set_value(10)
  app.number_input[2].set_value(20)
  deal(app)
  assert app.session_state.player_names == {1: "Shaun", 2: "Ashwing"}
  assert app.session_state.hand_start_stacks == {1: 1600, 2: 1600}
  assert app.session_state.game.get_state()["big_blind"] == 20
  assert app.session_state.game.get_state()["small_blind"] == 10
  assert "Bot logs" not in {item.label for item in app.button}
  assert any('class="seat__identity"><img class="ashwing-avatar"' in item.value for item in app.markdown)


def test_local_setup_switching_mode_and_validating_settings():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Play Ashwing").click().run()
  button(app, "Back to modes").click().run()
  button(app, "Pass-and-play").click().run()
  assert app.slider[0].max == 10
  app.slider[0].set_value(3).run()
  assert len(app.text_input) == 3
  app.number_input[1].set_value(10)
  button(app, "Deal the first hand").click().run()
  assert app.error and app.session_state.game is None
  app.number_input[1].set_value(5)
  app.text_input[2].set_value("Player 1")
  button(app, "Deal the first hand").click().run()
  assert app.error and app.session_state.game is None
  app.text_input[2].set_value("River")
  deal(app)
  assert app.session_state.player_names == {1: "Player 1", 2: "Player 2", 3: "River"}


def test_pass_and_play_resume_hides_cards_and_reruns_do_not_pay_twice():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Pass-and-play").click().run()
  deal(app)
  button(app, "Reveal my cards").click().run()
  first_fold_key = button(app, "Fold").key
  button(app, "Leave game").click().run()
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
  button(app, "Pass-and-play").click().run()
  deal(app)
  button(app, "Reveal my cards").click().run()
  button(app, "Pot 30").click().run()
  assert not app.exception
  game = app.session_state.game
  assert game.table_bet == 30
  assert game.players[0].stack == 970
  assert app.session_state.history[-1]["amount"] == 25


def test_paced_bot_waits_then_commits_one_action_per_turn():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Play Ashwing").click().run()
  app.slider[0].set_value(3).run()
  deal(app)
  button(app, "Fold").click().run()
  assert not app.exception
  assert len(app.session_state.history) == 1
  turn, delay, _ = app.session_state.bot_due
  app.session_state.bot_due = (turn, delay, 0)
  app.run()
  assert not app.exception
  assert len(app.session_state.history) == 2
  assert app.session_state.history[-1]["player_id"] == 2


def test_history_remains_available_from_lobby_and_table():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Pass-and-play").click().run()
  deal(app)
  button(app, "Reveal my cards").click().run()
  button(app, "Fold").click().run()
  button(app, "History").click().run()
  assert app.selectbox[0].value == 1
  button(app, "Back to table").click().run()
  button(app, "Leave game").click().run()
  button(app, "Hand history").click().run()
  assert app.selectbox[0].value == 1
  button(app, "Back to menu").click().run()
  assert button(app, "Resume current game")


def test_ashwing_turn_does_not_depend_on_the_arena_registry(monkeypatch):
  import arena

  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Play Ashwing").click().run()
  app.slider[0].set_value(3).run()
  deal(app)
  assert app.session_state.player_names == {1: "You", 2: "Ashwing 1", 3: "Ashwing 2"}
  monkeypatch.delitem(arena.TOOLKIT_STRATEGIES, "Hive Mind")
  monkeypatch.delitem(arena.STRATEGIES, "Hive Mind")
  app.session_state.bot_pacing = "Instant"
  button(app, "Fold").click().run()
  assert not app.exception
  assert app.session_state.bot_error is None
  assert any(event["player_id"] == 2 for event in app.session_state.history)


def test_move_clock_stays_off_until_private_reveal_and_folds_once_on_expiry():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Pass-and-play").click().run()
  deal(app)
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
  deal(app)
  button(app, "Reveal my cards").click().run()
  button(app, "Call 5").click().run()
  button(app, "Reveal my cards").click().run()
  turn, _ = app.session_state.turn_clock
  app.session_state.turn_clock = (turn, 0)
  app.run()
  assert [event["action"] for event in app.session_state.history] == ["call", "check"]
  assert app.session_state.game.phase == "flop"
  assert sum(item.value.count('play-card--reveal"') for item in app.markdown) == 3
  app.run()
  assert all('play-card--reveal"' not in item.value for item in app.markdown)
  button(app, "Leave game").click().run()
  button(app, "Play Ashwing").click().run()
  deal(app)
  first_line = list(app.session_state.chat)
  assert any('room-speech--seat' in item.value and first_line[0] in item.value for item in app.markdown)
  app.run()
  assert len(first_line) == 1 and app.session_state.chat == first_line
  button(app, "Fold").click().run()
  assert len(app.session_state.chat) == 2
  assert any('room-speech--seat' in item.value and app.session_state.chat[-1] in item.value for item in app.markdown)


def test_ashwing_transcript_follows_a_hand_through_showdown(monkeypatch):
  from pokerbots_sdk import hive_policy

  def passive_bot(view, _rng):
    return ("check" if view.legal["check"] else "call"), None

  monkeypatch.setattr(hive_policy, "hive_mind", passive_bot)
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Play Ashwing").click().run()
  deal(app)
  app.session_state.bot_pacing = "Instant"
  button(app, "Raise").click().run()
  for _ in range(3):
    button(app, "Check").click().run()

  lines = json.loads((APP_PATH.parent / "ui" / "ashwing_banter.json").read_text(encoding="utf-8"))
  scene = list(app.session_state.chat)
  expected = ["start", "human_raise", "flop", "turn", "river", "showdown"]
  assert scene[:-1] == [lines[event][0] for event in expected]
  assert scene[-1] in [lines[event][0] for event in ("win", "loss", "split")]
  assert not app.exception
  app.run()
  assert app.session_state.chat == scene
  button(app, "Next hand").click().run()
  assert app.session_state.chat == [*scene, lines["new_hand"][0]]


def test_next_hand_clock_waits_on_history_and_deals_only_once():
  app = AppTest.from_file(str(APP_PATH)).run()
  button(app, "Pass-and-play").click().run()
  deal(app)
  button(app, "Reveal my cards").click().run()
  button(app, "Fold").click().run()
  assert any('aria-label="Next hand in 5 seconds"' in item.value for item in app.markdown)
  assert app.session_state.game.hand_number == 1
  button(app, "Replay this hand").click().run()
  assert app.session_state.next_hand_clock is None
  assert app.session_state.game.hand_number == 1
  button(app, "Back to table").click().run()
  round_key, _ = app.session_state.next_hand_clock
  app.session_state.next_hand_clock = (round_key, 0)
  app.run().run()
  assert not app.exception
  assert app.session_state.game.hand_number == 2
  assert app.session_state.next_hand_clock is None
  assert app.session_state.turn_clock is None
  assert app.session_state.revealed_player is None
  assert sorted(app.session_state.hand_records) == [1, 2]
