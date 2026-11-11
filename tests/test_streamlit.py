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
  app.slider[0].set_value(3).run()
  app.selectbox[0].select("Human vs Bots").run()
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


def test_arena_pause_and_step_produce_the_same_hand_as_autoplay():
  def play(autoplay):
    app = AppTest.from_file(str(APP_PATH)).run()
    app.slider[0].set_value(2).run()
    app.selectbox[0].select("Bot Arena").run()
    app.selectbox[2].select("Random")
    button(app, "Deal the first hand").click().run()
    if autoplay:
      button(app, "Play").click().run()
      assert app.session_state.history == []
      turn, _ = app.session_state.arena_due
      app.session_state.arena_due = (turn, 0)
      app.run()
      assert len(app.session_state.history) == 1
      button(app, "Pause").click().run()
      app.run()
      assert len(app.session_state.history) == 1
    while not app.session_state.game.hand_over:
      before = len(app.session_state.history)
      button(app, "Step").click().run()
      assert not app.exception
      assert len(app.session_state.history) == before + 1
    record = app.session_state.hand_records[1]
    dealer = app.session_state.game.dealer_index
    action_count = len(app.session_state.history)
    if not app.session_state.game.game_over:
      button(app, "Step").click().run()
      assert app.session_state.game.hand_number == 2
      assert app.session_state.game.dealer_index != dealer
      assert len(app.session_state.history) == action_count
    return record

  assert play(False) == play(True)


def test_arena_can_select_and_run_equity_strategy():
  app = AppTest.from_file(str(APP_PATH)).run()
  app.slider[0].set_value(2).run()
  app.selectbox[0].select("Bot Arena").run()
  app.selectbox[2].select("Equity")
  button(app, "Deal the first hand").click().run()
  assert app.session_state.arena.styles == ("Calling Station", "Equity")
  for _ in range(2):
    button(app, "Step").click().run()
    assert not app.exception
  assert [event["player_id"] for event in app.session_state.history] == [1, 2]
  assert app.session_state.bot_error is None


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
