import html
import math
from pathlib import Path

TEMPLATE = (Path(__file__).parent / "table.html").read_text(encoding="utf-8")
SUIT_NAMES = {"♣️": "clubs", "♦️": "diamonds", "♠️": "spades", "♥️": "hearts"}
RANK_NAMES = {"A": "Ace", "K": "King", "Q": "Queen", "J": "Jack", "10": "Ten"}
PHASE_NAMES = {"preflop": "Preflop", "flop": "Flop", "turn": "Turn", "river": "River", "showdown": "Showdown", "hand_over": "Hand complete"}


def card_html(card=None, hidden=False, empty=False):
  if empty:
    return '<span class="play-card play-card--empty" role="img" aria-label="Empty card slot">?</span>'
  if hidden or not card:
    return '<span class="play-card play-card--back" role="img" aria-label="Face-down card"><span aria-hidden="true">♠</span></span>'
  rank, suit = card
  readable = RANK_NAMES.get(rank, rank)
  readable = readable if readable != rank or not rank.isdigit() else rank
  color = " play-card--red" if suit in ("♦️", "♥️") else ""
  label = html.escape(f"{readable} of {SUIT_NAMES.get(suit, suit)}", quote=True)
  return (f'<span class="play-card{color}" role="img" aria-label="{label}">'
    f'<span class="play-card__rank" aria-hidden="true">{html.escape(rank)}</span>'
    f'<span class="play-card__suit" aria-hidden="true">{html.escape(suit)}</span></span>')


def seat_html(player, state, name, index, total, last_action="", is_bot=False):
  seat_id = player["player_id"]
  angle = math.pi + (2 * math.pi * index / total)
  left = 50 + 42 * math.sin(angle)
  top = 50 - 37 * math.cos(angle)
  classes = ["seat"]
  if state["current_player"] == seat_id:
    classes.append("seat--active")
  if player["folded"]:
    classes.append("seat--folded")
  if not player["in_hand"]:
    classes.append("seat--out")
  marker = []
  if seat_id == state["dealer"]:
    marker.append("D")
  if seat_id == state["small_blind_player"]:
    marker.append("SB")
  if seat_id == state["big_blind_player"]:
    marker.append("BB")
  if is_bot:
    marker.append("BOT")
  marker_html = "".join(f'<span class="seat__badge">{item}</span>' for item in marker)
  if player["folded"] and player["in_hand"]:
    status = "Folded"
  elif player["all_in"]:
    status = "All-in"
  elif not player["in_hand"]:
    status = "Out"
  elif state["current_player"] == seat_id:
    status = "To act"
  else:
    status = last_action
  if player["in_hand"]:
    cards = player["hole_cards"] if player["hole_cards"] else [None, None]
    card_markup = "".join(card_html(card, hidden=card is None) for card in cards)
  else:
    card_markup = '<span class="seat__footer">No cards</span>'
  safe_name = html.escape(str(name), quote=True)
  safe_status = html.escape(str(status), quote=True)
  accessible = html.escape(f"{name}, {player['stack']} chips, {player['current_bet']} bet, {status}", quote=True)
  return (f'<article class="{" ".join(classes)}" style="--seat-x:{left:.2f}%;--seat-y:{top:.2f}%" aria-label="{accessible}">'
    f'<span class="seat__name" title="{safe_name}">{safe_name}</span>'
    f'<div class="seat__stack">{player["stack"]:,} chips · {player["current_bet"]:,} bet</div>'
    f'<div class="seat__cards">{card_markup}</div>'
    f'<div class="seat__footer">{marker_html}<span>{safe_status}</span></div></article>')


def table_html(state, names=None, last_actions=None, bot_ids=None):
  names = names or {}
  last_actions = last_actions or {}
  bot_ids = set(bot_ids or [])
  people = state["players"]
  seats = "".join(seat_html(item, state, names.get(item["player_id"], f"Player {item['player_id']}") , i, len(people), last_actions.get(item["player_id"], ""), item["player_id"] in bot_ids) for i, item in enumerate(people))
  board = "".join(card_html(card) for card in state["board"])
  board += "".join(card_html(empty=True) for _ in range(max(0, 5 - len(state["board"]))))
  current = state["current_player"]
  status = "Pots settled" if state["hand_over"] else f"{names.get(current, f'Player {current}') if current else 'Players'} to act"
  replacements = {
    "__HAND__": str(state["hand_number"]),
    "__PHASE_LABEL__": PHASE_NAMES.get(state["phase"], state["phase"]),
    "__POT__": f"{state['pot']:,}",
    "__BOARD__": board,
    "__SEATS__": seats,
    "__STATUS__": html.escape(status),
    "__BLINDS__": f"{state['small_blind']:,} / {state['big_blind']:,}",
    "__PLAYERS_LEFT__": str(sum(p["stack"] > 0 or (p["in_hand"] and not p["folded"]) for p in people))
  }
  markup = TEMPLATE
  for key, value in replacements.items():
    markup = markup.replace(key, value)
  return markup
