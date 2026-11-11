from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def button(app, label):
  return next(item for item in app.button if item.label == label)


def test_setup_controls_follow_player_count_and_mode_before_dealing():
  app = AppTest.from_file(str(APP_PATH)).run()
  app.slider[0].set_value(2).run()
  app.selectbox[0].select("Human vs Bots").run()
  assert [item.label for item in app.text_input] == ["Seat 1 name", "Seat 2 name"]
  app.selectbox[1].select("Hard")
  button(app, "Deal the first hand").click().run()
  assert not app.exception
  assert app.session_state.difficulty == "Hard"
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
