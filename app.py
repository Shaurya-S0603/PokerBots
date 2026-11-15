import html
import json
from math import ceil
from pathlib import Path
from secrets import randbits
from time import monotonic

import streamlit as st

from arena import BotArena, apply_decision, observe
from poker_engine import start_game
from ui.benchmark_dashboard import render_benchmarks
from pokerbots_sdk.hive_policy import hive_mind
from ui.bot_visualization import render_bot_visualization
from ui.render import ashwing_avatar, card_html, table_html
from ui.replay import export_history, record_step, start_record
from ui.session import action_event, new_stats, settle_stats
from ui.showdown import best_five, pot_explanation


st.set_page_config(page_title="PokerRoom · Texas Hold'em", page_icon="♠️", layout="wide", initial_sidebar_state="collapsed")
ROOT = Path(__file__).parent
CSS = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
LOCAL = "Local Pass-and-Play"
ASHWING = "Human vs Ashwing"
BOT_PACING = {"Instant": 0, "Quick": 0.6, "Relaxed": 1.2}
TURN_SECONDS = 30
BANTER = json.loads((ROOT / "ui" / "ashwing_banter.json").read_text(encoding="utf-8"))


def _init_state():
  defaults = {
    "screen": "menu",
    "game": None,
    "game_id": 0,
    "game_mode": LOCAL,
    "human_bots": None,
    "bot_simulations": {},
    "player_names": {},
    "revealed_player": None,
    "last_actions": {},
    "history": [],
    "hand_records": {},
    "stats": {},
    "hand_start_stacks": {},
    "finished_hand": None,
    "flash": None,
    "turn_clock": None,
    "chat": [],
    "chat_counts": {},
    "chat_events": set(),
    "reduced_motion": False,
    "bot_error": None,
    "bot_pacing": "Quick",
    "bot_due": None,
  }
  if st.session_state.get("screen") == "puzzles":
    st.session_state.screen = "menu"
  if st.session_state.get("game_mode") in {"Human vs Bots", "Bot Arena"}:
    st.session_state.update(game_mode=LOCAL, screen="menu", game=None, hand_records={})
  for key, value in defaults.items():
    if key not in st.session_state:
      st.session_state[key] = value


def _inject_css():
  st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
  if st.session_state.reduced_motion:
    st.markdown("<style>*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}</style>", unsafe_allow_html=True)


def _name(player_id):
  return st.session_state.player_names.get(player_id, f"Player {player_id}")


def _player(player_id):
  return next(p for p in st.session_state.game.players if p.player_id == player_id)


def _start_game(count, chips, small, big, mode, names):
  human_bots = BotArena(randbits(64), ["Ashwing"] * count) if mode == ASHWING else None
  game = start_game(count, chips, small, big, deck_rng=human_bots.deck_rng if human_bots else None)
  st.session_state.human_bots = human_bots
  st.session_state.bot_simulations = {}
  st.session_state.game = game
  st.session_state.game_id += 1
  st.session_state.screen = "table"
  st.session_state.game_mode = mode
  st.session_state.player_names = {i + 1: value.strip() for i, value in enumerate(names)}
  st.session_state.revealed_player = None
  st.session_state.last_actions = {}
  st.session_state.history = []
  st.session_state.hand_records = {}
  st.session_state.stats = {p.player_id: new_stats() for p in game.players}
  st.session_state.hand_start_stacks = {p.player_id: chips for p in game.players}
  _record_hand_start(game.get_state())
  st.session_state.finished_hand = None
  st.session_state.flash = None
  st.session_state.bot_error = None
  st.session_state.bot_due = None
  st.session_state.turn_clock = None
  st.session_state.chat = []
  st.session_state.chat_counts = {}
  st.session_state.chat_events = set()
  _say("start", 0)


def _say(event, hand, *, occurrence=None):
  if st.session_state.game_mode != ASHWING:
    return
  key = (event, hand, occurrence)
  if key in st.session_state.chat_events:
    return
  count = st.session_state.chat_counts.get(event, 0)
  lines = BANTER[event]
  st.session_state.chat.append(lines[count % len(lines)])
  st.session_state.chat = st.session_state.chat[-24:]
  st.session_state.chat_counts[event] = count + 1
  st.session_state.chat_events.add(key)


def _record_hand_start(state):
  st.session_state.hand_records[state["hand_number"]] = start_record(
    state, st.session_state.hand_start_stacks)


def _log_action(action, player_id, before):
  game = st.session_state.game
  event = action_event(action, player_id, before, _player(player_id))
  st.session_state.history.append(event)
  record = st.session_state.hand_records.get(before["hand_number"])
  if record is None:
    _record_hand_start(before)
    record = st.session_state.hand_records[before["hand_number"]]
  record_step(record, game.get_state(), event)
  st.session_state.last_actions[player_id] = action.replace("_", " ").capitalize()



def _turn_id(state):
  return (st.session_state.game_id, state["hand_number"], state["current_player"],
    len(st.session_state.history))


def _expired(turn):
  clock = st.session_state.turn_clock
  return clock is not None and clock[0] == turn and monotonic() >= clock[1]


def _expire_turn(turn):
  game = st.session_state.game
  state = game.get_state()
  if st.session_state.screen != "table" or state["hand_over"] or _bot_to_act(state):
    return
  if _turn_id(state) != turn or not _expired(turn):
    return
  player = _player(turn[2])
  action = "check" if game.legal_actions(player).get("check") else "fold"
  _say("timeout", turn[1], occurrence=turn[3])
  _apply_action(action, player, timed_out=True)


def _render_clock(turn):
  timing = st.session_state.turn_clock
  if timing is None or timing[0] != turn:
    st.session_state.turn_clock = (turn, monotonic() + TURN_SECONDS)

  @st.fragment(run_every=1)
  def tick():
    active = st.session_state.turn_clock
    if st.session_state.screen != "table" or active is None or active[0] != turn:
      return
    _expire_turn(turn)
    left = min(TURN_SECONDS, max(0, ceil(active[1] - monotonic())))
    if left <= 10 and st.session_state.game_mode == ASHWING:
      # Refresh the game once so the separate chat panel shows the new line.
      key = ("thinking", turn[1], None)
      if key not in st.session_state.chat_events:
        _say("thinking", turn[1])
        st.rerun()
    urgent = " room-clock--urgent" if left <= 10 else ""
    st.markdown(f'<div class="room-clock{urgent}" role="timer" aria-label="Time remaining: {left} seconds">'
      f'<span>{left}s</span><div><i style="--remaining:{left / TURN_SECONDS:.4f}"></i></div></div>',
      unsafe_allow_html=True)

  tick()


def _apply_action(action, player, amount=None, *, timed_out=False):
  game = st.session_state.game
  before = game.get_state()
  if not timed_out and _expired(_turn_id(before)):
    _expire_turn(_turn_id(before))
  if action == "raise":
    ok = game.raise_bet(player, int(amount))
  else:
    ok = getattr(game, action)(player)
  if ok:
    _log_action(action, player.player_id, before)
    st.session_state.revealed_player = None
    st.session_state.turn_clock = None
    st.session_state.flash = ("info", f"Time expired · Automatic {action}.") if timed_out else None
    if (action == "fold" and not timed_out and before["phase"] in ("turn", "river")
        and before["pot"] >= 12 * before["big_blind"] and player.total_bet >= 6 * before["big_blind"]):
      _say("blunder", before["hand_number"])
  else:
    st.session_state.flash = ("error", game.last_error or "That action could not be completed.")
  st.rerun()


def _bot_to_act(state):
  return (st.session_state.game_mode == ASHWING
    and not state["hand_over"] and state["current_player"] not in (None, 1))


def _play_bot_turn(before):
  game = st.session_state.game
  current = before["current_player"]
  player = _player(current)
  diagnostics = {}
  try:
    view = observe(game, player)
    action, target = hive_mind(view, st.session_state.human_bots.bot_rngs[current - 1],
      diagnostics=diagnostics)
    action, ok = apply_decision(game, player, view, action, target)
  except ValueError as error:
    st.session_state.bot_error = str(error)
    return False
  if not ok:
    st.session_state.bot_error = game.last_error or "A bot action was rejected."
    return False
  _log_action(action, current, before)
  if diagnostics:
    diagnostics.update(model="Ashwing", action=action, seat=current, phase=before["phase"],
      board=before["board"], pot=before["pot"])
    st.session_state.bot_simulations.setdefault(before["hand_number"], []).append(diagnostics)
  return True


def _run_bots():
  game = st.session_state.game
  for _ in range(250):
    state = game.get_state()
    if not _bot_to_act(state) or not _play_bot_turn(state):
      return
  st.session_state.bot_error = "Bot action limit reached. Select Continue bot turns to resume."


def _render_paced_bot(state, delay):
  st.info(f"{_name(state['current_player'])} is thinking…")
  turn = (st.session_state.game_id, state["hand_number"], len(st.session_state.history))
  timing = st.session_state.bot_due
  if timing is None or timing[:2] != (turn, delay):
    st.session_state.bot_due = (turn, delay, monotonic() + delay)

  @st.fragment(run_every=delay)
  def tick():
    current_timing = st.session_state.bot_due
    if current_timing is None or current_timing[:2] != (turn, delay) or st.session_state.screen != "table":
      return
    if monotonic() >= current_timing[2]:
      st.session_state.bot_due = None
      _play_bot_turn(state)
      st.rerun()

  tick()


def _finish_hand_if_needed(state):
  if not state["hand_over"] or st.session_state.finished_hand == state["hand_number"]:
    return
  st.session_state.finished_hand = state["hand_number"]
  settle_stats(st.session_state.stats, st.session_state.history, st.session_state.hand_start_stacks, state)
  hand = state["hand_number"]
  human = state["players"][0]
  if state["game_over"]:
    _say("match_win" if human["stack"] == 0 else "match_loss", hand)
  elif human["stack"] == 0 and st.session_state.hand_start_stacks.get(1, 0) > 0:
    _say("match_win", hand)
  elif st.session_state.game_mode == ASHWING:
    knocked_out = any(seat["stack"] == 0 and st.session_state.hand_start_stacks.get(seat["player_id"], 0) > 0
      for seat in state["players"][1:])
    if knocked_out and 1 in state["winners"]:
      _say("eliminated", hand)
    elif human["in_hand"]:
      _say("loss" if 1 in state["winners"] else "win", hand)


def _render_table(state):
  shown = state
  current = state["current_player"]
  if not state["hand_over"] and current is not None:
    if st.session_state.game_mode == ASHWING and current == 1:
      shown = st.session_state.game.get_state(1)
    if st.session_state.game_mode == LOCAL and st.session_state.revealed_player == current:
      shown = st.session_state.game.get_state(current)
  bot_ids = {p.player_id for p in st.session_state.game.players if p.player_id != 1} if st.session_state.game_mode == ASHWING else set()
  markup = table_html(shown, st.session_state.player_names, st.session_state.last_actions, bot_ids)
  st.markdown(markup, unsafe_allow_html=True)


def _render_actions(state):
  if state["hand_over"]:
    _render_showdown(state)
    return
  current = state["current_player"]
  if current is None:
    return
  turn = _turn_id(state)
  key = "_".join(map(str, turn))
  if st.session_state.game_mode == LOCAL and st.session_state.revealed_player != current:
    st.caption(f"{_name(current)}’s turn · Pass them the device to reveal their cards.")
    if st.button("Reveal my cards", key=f"reveal_{key}", type="primary", use_container_width=True):
      st.session_state.revealed_player = current
      st.rerun()
    return

  player = _player(current)
  legal = st.session_state.game.legal_actions(player)
  _render_clock(turn)
  passive = ("Check", "check") if legal["check"] else (f"Call {legal['call_amount']:,}", "call")
  actions = [("Fold", "fold"), passive, ("All-in", "all_in")]
  can_raise = legal.get("raise", False)
  available = []
  if can_raise:
    maximum = legal["max_raise_total"]
    minimum = min(legal["min_raise_total"], maximum)
    pot_after_call = state["pot"] + legal["call_amount"]
    presets = [("½ pot", state["table_bet"] + pot_after_call // 2), ("Pot", state["table_bet"] + pot_after_call)]
    available = [(label, amount) for label, amount in presets if minimum <= amount < maximum]
  with st.container(key="move_buttons"):
    widths = [1, 1.15] + ([1, 1.8] + [1.05] * len(available) if can_raise else []) + [1]
    fold, call, *sizing, all_in = st.columns(widths, gap="small", vertical_alignment="center")
    for column, (label, action) in zip((fold, call, all_in), actions):
      if column.button(label, key=f"{action}_{key}", disabled=not legal.get(action, False),
          type="primary" if action in ("check", "call") else "secondary", use_container_width=True):
        _apply_action(action, player)
    if can_raise:
      raise_column, amount_column, *preset_columns = sizing
      target = amount_column.number_input("Raise to", min_value=minimum, max_value=maximum,
        value=minimum, step=1, key=f"raise_to_{key}", label_visibility="collapsed")
      if raise_column.button("Raise", key=f"raise_{key}", use_container_width=True):
        _apply_action("raise", player, int(target) - player.current_bet)
      for column, (label, amount) in zip(preset_columns, available):
        if column.button(f"{label} {amount:,}", key=f"preset_{label}_{key}", use_container_width=True):
          _apply_action("raise", player, amount - player.current_bet)


def _render_showdown(state):
  if st.session_state.game_mode == ASHWING:
    human = next(item for item in state["players"] if item["player_id"] == 1)
    if human["stack"] == 0 and not state["game_over"]:
      st.error("You were eliminated. The remaining bots can continue the tournament if you choose Next hand.")
      if st.button("Start a fresh game", use_container_width=True):
        st.session_state.screen = "menu"
        st.session_state.game = None
        st.rerun()
  if state["game_over"]:
    champions = [p for p in state["players"] if p["stack"] > 0]
    if champions:
      st.success(f"Poker champion: {_name(champions[0]['player_id'])} · {champions[0]['stack']:,} chips")
    else:
      st.success("Game complete")
  elif state["showdown_hands"]:
    st.success("Showdown complete · Chips awarded")
  else:
    st.success("Hand won · All opponents folded")
  if state["showdown_hands"]:
    st.subheader("Revealed hands")
    for raw_id, hand in state["showdown_hands"].items():
      player_id = int(raw_id)
      player = next(p for p in state["players"] if p["player_id"] == player_id)
      hole = player["hole_cards"]
      chosen = best_five(state["board"], hole, hand)
      cards = "".join(card_html(card, highlight=card in hole) for card in chosen)
      used = sum(card in hole for card in chosen)
      source = "Plays the board" if not used else f"{used} hole card{'s' if used == 2 else ''} in the best five"
      st.markdown(f'<div class="room-status"><strong>{html.escape(_name(player_id))}</strong> · {html.escape(hand[0])}<div class="room-cardline room-cardline--showdown" role="group" aria-label="Best five cards">{cards}</div><small>{source}</small></div>', unsafe_allow_html=True)
  _render_payouts(state)
  if st.button("Replay this hand", use_container_width=True):
    _open_history(state["hand_number"])
  if state["game_over"]:
    st.subheader("Final standings")
    for player in sorted(state["players"], key=lambda p: p["stack"], reverse=True):
      st.write(f"{_name(player['player_id'])}: {player['stack']:,} chips")
    if st.button("New game", type="primary", use_container_width=True):
      st.session_state.screen = "menu"
      st.session_state.game = None
      st.rerun()
  elif st.button("Next hand", key=f"next_{st.session_state.game_id}_{state['hand_number']}", type="primary", use_container_width=True):
    _deal_next_hand()
    st.rerun()


def _deal_next_hand():
  game = st.session_state.game
  starting_stacks = {p.player_id: p.stack for p in game.players}
  if not game.start_next_round():
    st.session_state.flash = ("error", game.last_error or "Could not start the next hand.")
    return False
  st.session_state.hand_start_stacks = starting_stacks
  _record_hand_start(game.get_state())
  st.session_state.turn_clock = None
  st.session_state.revealed_player = None
  st.session_state.last_actions = {}
  st.session_state.flash = None
  return True


def _render_payouts(state):
  st.subheader("Payout summary")
  if state["pot_results"]:
    for index, pot in enumerate(state["pot_results"]):
      title = "Main pot" if index == 0 else f"Side pot {index}"
      winners = ", ".join(f"{_name(int(player_id))} (+{chips:,})" for player_id, chips in pot["payouts"].items())
      st.write(f"**{title}: {pot['amount']:,} chips** · {winners}")
      st.caption(pot_explanation(pot, state["showdown_hands"]))
  for player_id, chips in state["uncalled_returns"].items():
    st.write(f"Uncalled bet returned to {_name(player_id)} · {chips:,} chips")


def _open_history(hand=None):
  if hand is not None:
    game_id = st.session_state.game_id
    st.session_state[f"replay_hand_{game_id}"] = hand
    st.session_state[f"replay_step_{game_id}_{hand}"] = 0
  st.session_state.screen = "history"
  st.session_state.bot_due = None
  if st.session_state.game_mode == LOCAL:
    st.session_state.revealed_player = None
  st.rerun()


def _render_history():
  if st.button("Back to table" if st.session_state.game else "Back to menu"):
    st.session_state.screen = "table" if st.session_state.game else "menu"
    st.rerun()
  st.title("Hand history")
  completed = {number: record for number, record in st.session_state.hand_records.items()
    if record["steps"][-1]["table"]["hand_over"]}
  if not completed:
    st.info("Finish a hand to replay or download it.")
    return
  hand = st.selectbox("Completed hand", sorted(completed, reverse=True),
    format_func=lambda number: f"Hand {number}", key=f"replay_hand_{st.session_state.game_id}")
  record = completed[hand]
  steps = record["steps"]
  cursor_key = f"replay_step_{st.session_state.game_id}_{hand}"
  index = st.session_state.get(cursor_key, 0)
  previous, following = st.columns(2)
  previous.button("Previous step", disabled=index == 0, use_container_width=True,
    on_click=lambda: st.session_state.update({cursor_key: index - 1}))
  following.button("Next step", disabled=index == len(steps) - 1, use_container_width=True,
    on_click=lambda: st.session_state.update({cursor_key: index + 1}))
  step = steps[index]
  table = step["table"]
  st.caption(f"Step {index + 1} of {len(steps)}")
  if step["action"]:
    event = step["action"]
    action = event["action"].replace("_", " ")
    amount = f" · {event['amount']:,} chips" if event["amount"] else ""
    st.text(f"{event['phase'].capitalize()} · {_name(event['player_id'])}: {action}{amount}")
  else:
    st.text("Blinds posted")
  for change in step["board_changes"]:
    cards = " ".join(f"{rank}{suit}" for rank, suit in change["cards"])
    st.text(f"{change['street']} · {cards}")
  st.markdown(table_html(table, st.session_state.player_names), unsafe_allow_html=True)
  with st.expander("Starting stacks"):
    for player_id, stack in record["starting_stacks"].items():
      st.text(f"{_name(player_id)} · {stack:,} chips")
  if table["hand_over"]:
    _render_payouts(table)
  st.download_button("Download completed hands (JSON)", data=export_history(completed),
    file_name="pokerroom-hand-history.json", mime="application/json")
  st.caption("The download uses seat numbers and includes only cards revealed at showdown.")


def _masthead():
  st.markdown('<div class="room-masthead"><span class="room-mark" aria-hidden="true">♠</span>'
    '<span class="room-wordmark">PokerRoom</span><span class="room-variant">No-Limit Hold’em</span></div>',
    unsafe_allow_html=True)


def _deal(count, chips, small, big, mode, names):
  st.markdown('<div class="deal-overlay" role="status"><div class="deal-deck" aria-hidden="true">'
    '<i></i><i></i><i></i></div><strong>Dealing you in…</strong></div>', unsafe_allow_html=True)
  _start_game(count, chips, small, big, mode, names)
  st.rerun()


def _render_lobby_hero():
  with st.container(key="club_hero"):
    st.markdown('<div class="room-club-hero"><div><h1>Take a seat.</h1>'
      '<p>Play No-Limit Hold’em against Ashwing or share a table on one device.</p>'
      '</div><div class="room-club-portrait">' + ashwing_avatar() + '<span>Ashwing</span></div></div>',
      unsafe_allow_html=True)
    play, local = st.columns(2, gap="small")
    if play.button("Play Ashwing", type="primary", use_container_width=True):
      _deal(2, 1000, 5, 10, ASHWING, ["You", "Ashwing"])
    if local.button("Pass-and-play", use_container_width=True):
      _deal(2, 1000, 5, 10, LOCAL, ["Player 1", "Player 2"])


def _render_menu():
  _render_lobby_hero()
  if st.session_state.game is not None and st.button("Resume current game", use_container_width=True):
    st.session_state.screen = "table"
    st.rerun()
  with st.expander("Customize a table"):
    mode = st.radio("Game mode", [LOCAL, ASHWING], horizontal=True)
    vs_ashwing = mode == ASHWING
    st.caption("Play heads-up or add up to four more Ashwing seats." if vs_ashwing
      else "Share one device. Each player reveals their cards on their turn.")
    count = st.slider("Number of players", 2, 6 if vs_ashwing else 10, 2 if vs_ashwing else 5,
      key="ashwing_seats" if vs_ashwing else "local_seats")
    with st.form("new_game", clear_on_submit=False, border=False):
      c1, c2, c3 = st.columns(3)
      with c1:
        chips = st.number_input("Starting chips", min_value=10, max_value=1000000, value=1000, step=100)
      with c2:
        small = st.number_input("Small blind", min_value=1, max_value=1000000, value=5, step=1)
      with c3:
        big = st.number_input("Big blind", min_value=2, max_value=1000000, value=10, step=1)
      with st.expander("Player names"):
        if vs_ashwing:
          human = st.text_input("Your name", value="You", max_chars=24)
          bots = ["Ashwing"] if count == 2 else [f"Ashwing {i}" for i in range(1, count)]
          names = [human, *bots]
        else:
          names = [st.text_input(f"Seat {index + 1} name", value=f"Player {index + 1}",
            max_chars=24, key=f"local_player_{index}") for index in range(count)]
      submit = st.form_submit_button("Deal the first hand", type="primary", use_container_width=True)
      if submit:
        clean = [value.strip() for value in names]
        if not 0 < small < big:
          st.error("The big blind must be greater than the small blind.")
        elif len({value.casefold() for value in clean}) != len(clean) or any(not value for value in clean):
          st.error("Enter a distinct, nonempty name for each player.")
        else:
          _deal(count, int(chips), int(small), int(big), mode, clean)
  with st.sidebar, st.expander("PokerRoom tools"):
    if st.button("Bot visualization", use_container_width=True):
      _open_visualization("menu")
    if st.button("Bot benchmarks", use_container_width=True):
      st.session_state.screen = "benchmarks"
      st.rerun()
    if st.session_state.hand_records and st.button("Hand history", use_container_width=True):
      _open_history()


def _render_sidebar():
  with st.sidebar:
    st.subheader("Table settings")
    st.checkbox("Reduce animations", key="reduced_motion")
    if st.session_state.game_mode == ASHWING:
      st.selectbox("Bot pace", list(BOT_PACING),
        index=list(BOT_PACING).index(st.session_state.bot_pacing), key="bot_pace_control",
        on_change=lambda: st.session_state.update(bot_pacing=st.session_state.bot_pace_control))
    with st.expander("Player statistics"):
      for player_id, stats in st.session_state.stats.items():
        hands = max(1, stats["hands"])
        name = html.escape(_name(player_id))
        st.markdown(f'<div class="room-stat"><span aria-hidden="true"></span>'
          f"{name} · {stats['hands']} hands · {stats['wins']} wins</div>", unsafe_allow_html=True)
        st.caption(f"Net {stats['net']:+,} chips · VPIP {stats['vpip']/hands:.0%} · PFR {stats['pfr']/hands:.0%}")


def _render_action_log(state):
  street = "showdown" if state["hand_over"] else state["phase"]
  labels = ("Preflop", "Flop", "Turn", "River", "Showdown")
  stages = "".join(f'<span{" aria-current=step" if label.lower() == street else ""}>{label}</span>'
    for label in labels)
  events = [event for event in st.session_state.history if event["hand"] == state["hand_number"]]
  rows = []
  for event in reversed(events[-24:]):
    player = html.escape(_name(event["player_id"]))
    action = html.escape(event["action"].replace("_", " "))
    amount = f'<strong>{event["amount"]:,}</strong>' if event["amount"] else ""
    phase = html.escape(event["phase"].capitalize())
    rows.append(f'<li><span>{player} {action}</span>{amount}<small>{phase}</small></li>')
  if not rows:
    rows.append("<li><span>Blinds posted</span></li>")
  st.markdown(f'<section class="room-log" aria-label="Action log"><h3>Action log</h3>'
    f'<div class="room-streets" aria-label="Betting streets">{stages}</div>'
    f'<ol class="room-events">{"".join(rows)}</ol></section>', unsafe_allow_html=True)


def _render_table_chat():
  chat = st.session_state.chat
  if not chat:
    return
  rows = "".join(f"<li>{html.escape(line)}</li>" for line in reversed(chat))
  st.markdown('<section class="room-chat" aria-label="Ashwing chat"><h3>' + ashwing_avatar() + 'Ashwing chat</h3>'
    f'<ol class="room-chat__messages" aria-live="polite">{rows}</ol></section>',
    unsafe_allow_html=True)


def _table_heading(state):
  with st.container(key="table_nav"):
    leave, details, history, logs = st.columns([1.15, 1.7, 1, 1], gap="small", vertical_alignment="center")
    if leave.button("Leave game", use_container_width=True):
      if st.session_state.game_mode == LOCAL:
        st.session_state.revealed_player = None
      st.session_state.bot_due = None
      st.session_state.screen = "menu"
      st.rerun()
    phase = state["phase"].replace("_", " ").title()
    details.markdown(f'<div class="room-table-heading"><h2><span>{phase}</span>'
      f' <small>Hand {state["hand_number"]}</small></h2></div>', unsafe_allow_html=True)
    if history.button("History", use_container_width=True):
      _open_history()
    if st.session_state.game_mode == ASHWING and logs.button("Bot logs", use_container_width=True):
      _open_visualization("table")


def _open_visualization(return_to):
  st.session_state.bot_due = None
  st.session_state.visualization_return = return_to
  st.session_state.screen = "visualization"
  st.rerun()


def main():
  _init_state()
  _inject_css()
  if st.session_state.screen != "table":
    _masthead()
  if st.session_state.screen == "visualization":
    destination = st.session_state.visualization_return
    if st.button(f"Back to {destination}"):
      st.session_state.screen = destination
      st.rerun()
    completed = {number for number, record in st.session_state.hand_records.items()
      if record["steps"][-1]["table"]["hand_over"]}
    render_bot_visualization(st.session_state.bot_simulations, completed,
      st.session_state.stats, st.session_state.player_names)
    return
  if st.session_state.screen == "benchmarks":
    if st.button("Back to menu"):
      st.session_state.screen = "menu"
      st.rerun()
    render_benchmarks()
    return
  if st.session_state.screen == "history":
    _render_history()
    return
  if st.session_state.screen == "menu" or st.session_state.game is None:
    _render_menu()
    return
  delay = BOT_PACING[st.session_state.bot_pacing]
  if not delay and not st.session_state.bot_error:
    st.session_state.bot_due = None
    _run_bots()
  game = st.session_state.game
  state = game.get_state()
  _finish_hand_if_needed(state)
  _render_sidebar()
  _table_heading(state)
  if st.session_state.bot_error:
    st.error(st.session_state.bot_error)
    if st.button("Continue bot turns"):
      st.session_state.bot_error = None
      st.rerun()
    return
  if st.session_state.flash:
    level, message = st.session_state.flash
    if level == "error":
      st.error(message)
    else:
      st.caption(message)
    st.session_state.flash = None
  _render_table(state)
  with st.container(key="table_controls"):
    if _bot_to_act(state):
      _render_paced_bot(state, delay)
    else:
      st.session_state.bot_due = None
      _render_actions(state)
  with st.container(key="table_log"):
    _render_table_chat()
    with st.expander("Hand action log"):
      _render_action_log(state)


if __name__ == "__main__":
  main()
