import html
from pathlib import Path
from time import monotonic

import streamlit as st
import streamlit.components.v1 as components

from poker_bot import PokerBot
from poker_engine import start_game
from ui.render import card_html, table_html
from ui.session import action_event, new_stats, settle_stats
from ui.showdown import best_five, pot_explanation


st.set_page_config(page_title="PokerRoom · Texas Hold'em", page_icon="♠️", layout="wide", initial_sidebar_state="auto")
ROOT = Path(__file__).parent
CSS = (ROOT / "ui" / "styles.css").read_text(encoding="utf-8")
EFFECT_TEMPLATE = (ROOT / "ui" / "effect.html").read_text(encoding="utf-8")
BOT_PACING = {"Instant": 0, "Quick": 0.6, "Relaxed": 1.2}
EFFECT_SCRIPT = (ROOT / "ui" / "effects.js").read_text(encoding="utf-8")


def _init_state():
  defaults = {
    "screen": "menu",
    "game": None,
    "game_id": 0,
    "game_mode": "Local Pass-and-Play",
    "difficulty": "Easy",
    "player_names": {},
    "revealed_player": None,
    "handoff_required": True,
    "last_action": "",
    "last_actions": {},
    "history": [],
    "stats": {},
    "hand_start_stacks": {},
    "finished_hand": None,
    "flash": None,
    "pending_effect": None,
    "reduced_motion": False,
    "bot_error": None,
    "bot_pacing": "Quick",
    "bot_due": None
  }
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


def _start_game(count, chips, small, big, mode, difficulty, names):
  game = start_game(count, chips, small, big)
  st.session_state.game = game
  st.session_state.game_id += 1
  st.session_state.screen = "table"
  st.session_state.game_mode = mode
  st.session_state.difficulty = difficulty
  st.session_state.player_names = {i + 1: value.strip() for i, value in enumerate(names)}
  st.session_state.revealed_player = None
  st.session_state.handoff_required = mode == "Local Pass-and-Play"
  st.session_state.last_action = ""
  st.session_state.last_actions = {}
  st.session_state.history = []
  st.session_state.stats = {p.player_id: new_stats() for p in game.players}
  st.session_state.hand_start_stacks = {p.player_id: chips for p in game.players}
  st.session_state.finished_hand = None
  st.session_state.flash = ("info", "New game started. Blinds have been posted.")
  st.session_state.pending_effect = None
  st.session_state.bot_error = None
  st.session_state.bot_due = None


def _log_action(action, player_id, before):
  game = st.session_state.game
  event = action_event(action, player_id, before, _player(player_id))
  st.session_state.history.append(event)
  phrase = f"{_name(player_id)} {action.replace('_', ' ')}"
  if action in ("call", "raise", "all_in") and event["amount"] > 0:
    phrase += f" · {event['amount']:,} chips"
  st.session_state.last_action = phrase
  st.session_state.last_actions[player_id] = action.replace("_", " ").capitalize()
  if game.hand_over:
    st.session_state.pending_effect = ("win", "Hand complete · Pots awarded")
  else:
    st.session_state.pending_effect = ("action", phrase)


def _apply_action(action, player, amount=None):
  game = st.session_state.game
  before = game.get_state()
  if action == "raise":
    ok = game.raise_bet(player, int(amount))
  else:
    ok = getattr(game, action)(player)
  if ok:
    _log_action(action, player.player_id, before)
    st.session_state.revealed_player = None
    st.session_state.handoff_required = st.session_state.game_mode == "Local Pass-and-Play"
    st.session_state.flash = None
  else:
    st.session_state.flash = ("error", game.last_error or "That action could not be completed.")
  st.rerun()


def _bot_to_act(state):
  return (st.session_state.game_mode == "Human vs Bots"
    and not state["hand_over"] and state["current_player"] not in (None, 1))


def _play_bot_turn(before):
  game = st.session_state.game
  current = before["current_player"]
  bot = PokerBot(st.session_state.difficulty)
  action, ok = bot.act(game, _player(current))
  if not ok:
    st.session_state.bot_error = game.last_error or "A bot action was rejected."
    return False
  _log_action(action, current, before)
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
  st.session_state.pending_effect = ("win", "Hand complete · Pots awarded")


def _show_effect():
  effect = st.session_state.pending_effect
  if not effect:
    return
  kind, message = effect
  content = (EFFECT_TEMPLATE.replace("__KIND__", html.escape(kind, quote=True))
    .replace("__REDUCED__", "true" if st.session_state.reduced_motion else "false")
    .replace("__MESSAGE__", html.escape(message))
    .replace("__SCRIPT__", EFFECT_SCRIPT.replace("</script", "<\\/script")))
  components.html(content, height=69, scrolling=False)
  st.session_state.pending_effect = None


def _render_table(state):
  shown = state
  current = state["current_player"]
  if not state["hand_over"] and current is not None:
    if st.session_state.game_mode == "Human vs Bots" and current == 1:
      shown = st.session_state.game.get_state(1)
    if st.session_state.game_mode == "Local Pass-and-Play" and st.session_state.revealed_player == current:
      shown = st.session_state.game.get_state(current)
  bot_ids = {p.player_id for p in st.session_state.game.players if p.player_id != 1} if st.session_state.game_mode == "Human vs Bots" else set()
  markup = table_html(shown, st.session_state.player_names, st.session_state.last_actions, bot_ids)
  st.markdown(markup, unsafe_allow_html=True)


def _render_private_cards(current):
  private = st.session_state.game.get_state(current)
  cards = next(item["hole_cards"] for item in private["players"] if item["player_id"] == current)
  markup = '<div class="room-cardline" role="group" aria-label="Your private hole cards">'
  markup += "".join(card_html(card) for card in cards)
  markup += "</div>"
  st.markdown(markup, unsafe_allow_html=True)


def _render_actions(state):
  if state["hand_over"]:
    _render_showdown(state)
    return
  current = state["current_player"]
  if current is None:
    st.info("Waiting for the betting state to advance.")
    return
  if st.session_state.game_mode == "Local Pass-and-Play" and st.session_state.revealed_player != current:
    st.session_state.handoff_required = True
  turn_key = f"{st.session_state.game_id}_{state['hand_number']}_{current}_{len(st.session_state.history)}"
  if st.session_state.handoff_required:
    st.markdown('<div class="room-status room-status--warning" role="status">PRIVATE HANDOFF · Give the device to the next player before revealing their cards.</div>', unsafe_allow_html=True)
    st.subheader(f"{_name(current)}'s turn")
    st.caption("The previous player's hole cards are hidden. Do not reveal this hand until the right player has the device.")
    if st.button("Reveal my cards", key=f"reveal_{turn_key}", type="primary", use_container_width=True):
      st.session_state.revealed_player = current
      st.session_state.handoff_required = False
      st.rerun()
    return
  player = _player(current)
  legal = st.session_state.game.legal_actions(player)
  st.markdown(f'<div class="room-action-head"><div class="room-action-head__title">{html.escape(_name(current))} · Your turn</div><div class="room-action-head__meta">Stack {player.stack:,} · Bet {player.current_bet:,} · To call {legal.get("call_amount", 0):,}</div></div>', unsafe_allow_html=True)
  _render_private_cards(current)
  columns = st.columns(2) + st.columns(2)
  actions = [
    ("Fold", "fold"),
    ("Check", "check"),
    (f"Call {legal.get('call_amount', 0):,}", "call"),
    (f"All-in {player.stack:,}", "all_in")
  ]
  for column, (label, action) in zip(columns, actions):
    with column:
      if st.button(label, key=f"{action}_{turn_key}", disabled=not legal.get(action, False), use_container_width=True):
        _apply_action(action, player)
  st.markdown('<div class="room-divider"></div>', unsafe_allow_html=True)
  can_raise = legal.get("raise", False)
  min_total = legal.get("min_raise_total") if can_raise else None
  max_total = legal.get("max_raise_total") if can_raise else None
  target = min(min_total, max_total) if can_raise else player.current_bet + 1
  target = max(player.current_bet + 1, target)
  st.caption("Raise to a total bet for this street. The engine will contribute only the additional chips.")
  col_amount, col_button = st.columns([3, 1])
  with col_amount:
    raise_to = st.number_input("Raise to (total bet)", min_value=int(target), max_value=int(max_total) if can_raise else int(target), value=int(target), step=1, disabled=not can_raise, key=f"raise_to_{turn_key}")
  with col_button:
    st.write(" ")
    if st.button("Raise", key=f"raise_{turn_key}", disabled=not can_raise, type="primary", use_container_width=True):
      _apply_action("raise", player, int(raise_to) - player.current_bet)
  if can_raise and min_total <= max_total:
    pot_after_call = state["pot"] + legal["call_amount"]
    presets = [("Min", min_total),
      ("½ pot", state["table_bet"] + pot_after_call // 2),
      ("Pot", state["table_bet"] + pot_after_call)]
    used_totals = set()
    columns = iter(st.columns(3))
    for label, total in presets:
      if not min_total <= total < max_total or total in used_totals:
        continue
      used_totals.add(total)
      with next(columns):
        if st.button(f"{label} {total:,}", key=f"preset_{label}_{turn_key}", use_container_width=True):
          _apply_action("raise", player, total - player.current_bet)
  if can_raise and min_total > max_total:
    st.caption("Only a short all-in raise is available at this stack size.")
  with st.expander("How betting works"):
    st.markdown("**Check** when nothing is owed. **Call** to match a bet. **Raise** to increase it. **All-in** commits your entire stack. A short all-in raise may not reopen betting for players who have already acted.")


def _render_showdown(state):
  if st.session_state.game_mode == "Human vs Bots":
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
  st.subheader("Payout summary")
  if state["pot_results"]:
    for index, pot in enumerate(state["pot_results"]):
      title = "Main pot" if index == 0 else f"Side pot {index}"
      winners = ", ".join(f"{_name(int(player_id))} (+{chips:,})" for player_id, chips in pot["payouts"].items())
      st.write(f"**{title}: {pot['amount']:,} chips** · {winners}")
      st.caption(pot_explanation(pot, state["showdown_hands"]))
  for player_id, chips in state["uncalled_returns"].items():
    st.write(f"Uncalled bet returned to {_name(player_id)} · {chips:,} chips")
  st.caption("Winners and pot eligibility are calculated by the poker engine, not by the interface.")
  if state["game_over"]:
    st.subheader("Final standings")
    for player in sorted(state["players"], key=lambda p: p["stack"], reverse=True):
      st.write(f"{_name(player['player_id'])}: {player['stack']:,} chips")
    if st.button("New game", type="primary", use_container_width=True):
      st.session_state.screen = "menu"
      st.session_state.game = None
      st.rerun()
  elif st.button("Next hand", key=f"next_{st.session_state.game_id}_{state['hand_number']}", type="primary", use_container_width=True):
    game = st.session_state.game
    st.session_state.hand_start_stacks = {p.player_id: p.stack for p in game.players}
    if game.start_next_round():
      st.session_state.revealed_player = None
      st.session_state.handoff_required = st.session_state.game_mode == "Local Pass-and-Play"
      st.session_state.last_actions = {}
      st.session_state.last_action = ""
      st.session_state.flash = ("info", f"Hand {game.hand_number} started. Dealer rotated and blinds posted.")
      st.rerun()
    st.session_state.flash = ("error", game.last_error or "Could not start the next hand.")
    st.rerun()


def _render_menu():
  st.markdown('<div class="room-hero"><h1>POKERROOM</h1><p>NO-LIMIT TEXAS HOLD’EM</p></div>', unsafe_allow_html=True)
  st.markdown('<p class="room-subtitle">A proper poker table. Real betting rules, side pots and showdown payouts. Play on one device or challenge the bots.</p>', unsafe_allow_html=True)
  if st.session_state.game is not None:
    if st.button("Resume current game", type="primary", use_container_width=True):
      st.session_state.screen = "table"
      st.rerun()
  with st.expander("How to play · 60-second guide", expanded=st.session_state.game is None):
    st.markdown("Each player receives two private cards. Make the strongest five-card hand using your cards and the shared board. Betting happens **before the flop**, **after the flop**, **after the turn** and **after the river**. Fold to leave the hand, check when no bet is owed, call to match, or raise to increase the bet. The last player standing wins immediately, otherwise the best eligible hand wins each pot.")
    st.markdown("**Pass-and-play:** hand the device to the named player and reveal their cards only when they are ready. **Human vs Bots:** you play as Player 1; the opponents use a simple heuristic, not a trained solver.")
  st.subheader("New game")
  count = st.slider("Number of players", 2, 10, 5)
  mode = st.selectbox("Game mode", ["Local Pass-and-Play", "Human vs Bots"])
  with st.form("new_game", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
      chips = st.number_input("Starting chips per player", min_value=10, max_value=1000000, value=1000, step=100)
    with c2:
      small = st.number_input("Small blind", min_value=1, max_value=1000000, value=5, step=1)
    with c3:
      big = st.number_input("Big blind", min_value=2, max_value=1000000, value=10, step=1)
    difficulty = st.selectbox("Bot difficulty", ["Easy", "Medium", "Hard"], disabled=mode != "Human vs Bots", help="Difficulty controls the bot's heuristics and bluff frequency.")
    with st.expander("Player names"):
      names = [st.text_input(f"Seat {index + 1} name", value=("You" if index == 0 and mode == "Human vs Bots" else f"Player {index + 1}"), max_chars=24, key=f"player_name_{index}") for index in range(count)]
    submit = st.form_submit_button("Deal the first hand", type="primary", use_container_width=True)
    if submit:
      clean = [value.strip() for value in names]
      if not 0 < small < big:
        st.error("The big blind must be greater than the small blind.")
      elif len(set(value.casefold() for value in clean)) != len(clean) or any(not value for value in clean):
        st.error("Enter a distinct, nonempty name for each player.")
      else:
        try:
          _start_game(count, int(chips), int(small), int(big), mode, difficulty, clean)
          st.rerun()
        except ValueError as error:
          st.error(str(error))


def _render_sidebar(state):
  with st.sidebar:
    st.markdown("### ♠ POKERROOM")
    if st.button("Main menu", use_container_width=True):
      if st.session_state.game_mode == "Local Pass-and-Play":
        st.session_state.revealed_player = None
        st.session_state.handoff_required = True
      st.session_state.screen = "menu"
      st.rerun()
    st.checkbox("Reduce animations", key="reduced_motion")
    if st.session_state.game_mode == "Human vs Bots":
      st.selectbox("Bot pace", list(BOT_PACING), key="bot_pacing")
    st.markdown("---")
    st.caption(f"{st.session_state.game_mode} · Hand {state['hand_number']}")
    st.metric("Pot", f"{state['pot']:,}")
    st.metric("Active stacks", f"{sum(item['stack'] > 0 for item in state['players'])} players")
    with st.expander("Recent actions", expanded=True):
      events = [event for event in st.session_state.history if event["hand"] == state["hand_number"]]
      if not events:
        st.caption("No actions yet. Blinds have been posted.")
      for event in events[-12:][::-1]:
        amount = f" · {event['amount']:,}" if event["amount"] else ""
        st.write(f"{_name(event['player_id'])}: {event['action'].replace('_', ' ')}{amount}")
    with st.expander("Session hand history"):
      for hand in sorted({e["hand"] for e in st.session_state.history}, reverse=True):
        count = sum(1 for e in st.session_state.history if e["hand"] == hand)
        st.write(f"Hand {hand}: {count} actions")
    with st.expander("Player statistics"):
      for player_id, stats in st.session_state.stats.items():
        hands = max(1, stats["hands"])
        st.write(f"**{_name(player_id)}** · {stats['hands']} hands · {stats['wins']} wins")
        st.caption(f"Net {stats['net']:+,} chips · VPIP {stats['vpip']/hands:.0%} · PFR {stats['pfr']/hands:.0%}")
    with st.expander("Rules and privacy"):
      st.markdown("A **straight** is five consecutive ranks. A **flush** is five of one suit. **Full house** beats a flush. Pots are split among the best eligible hands. The table hides private cards until a player reveals them or a showdown occurs.")
      st.caption("Pass-and-play is for a trusted, shared device. Do not use this interface as a secure remote multiplayer server.")


def main():
  _init_state()
  _inject_css()
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
  _render_sidebar(state)
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
      st.info(message)
    st.session_state.flash = None
  st.markdown(f"## Hand {state['hand_number']} · {state['phase'].replace('_', ' ').title()}")
  _render_table(state)
  _show_effect()
  if st.session_state.last_action:
    st.caption(f"Last action: {st.session_state.last_action}")
  if _bot_to_act(state):
    _render_paced_bot(state, delay)
  else:
    st.session_state.bot_due = None
    _render_actions(state)


if __name__ == "__main__":
  main()
