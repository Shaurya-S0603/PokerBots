from base64 import b64encode
import html
import math
from pathlib import Path

TEMPLATE = (Path(__file__).parent / "table.html").read_text(encoding="utf-8")
AVATAR_DATA = b64encode(Path(__file__).with_name("ashwing-avatar.webp").read_bytes()).decode("ascii")
SUIT_NAMES = {"♣️": "clubs", "♦️": "diamonds", "♠️": "spades", "♥️": "hearts"}
RANK_NAMES = {"A": "Ace", "K": "King", "Q": "Queen", "J": "Jack", "10": "Ten"}


def ashwing_avatar():
  return f'<img class="ashwing-avatar" src="data:image/webp;base64,{AVATAR_DATA}" alt="" width="192" height="192">'


def card_html(card=None, hidden=False, empty=False, highlight=False, reveal=False):
  if empty:
    return '<span class="play-card play-card--empty" role="img" aria-label="Empty card slot"></span>'
  if hidden or not card:
    return '<span class="play-card play-card--back" role="img" aria-label="Face-down card"><span aria-hidden="true">♠</span></span>'
  rank, suit = card
  readable = RANK_NAMES.get(rank, rank)
  readable = readable if readable != rank or not rank.isdigit() else rank
  color = " play-card--red" if suit in ("♦️", "♥️") else ""
  if highlight:
    color += " play-card--used"
  if reveal:
    color += " play-card--reveal"
  label = html.escape(f"{readable} of {SUIT_NAMES.get(suit, suit)}", quote=True)
  return (f'<span class="play-card{color}" role="img" aria-label="{label}">'
    f'<span class="play-card__rank" aria-hidden="true">{html.escape(rank)}</span>'
    f'<span class="play-card__suit" aria-hidden="true">{html.escape(suit)}</span></span>')


def _ashwing_speech(line, *, beside_seat=False):
  placement = "room-speech--seat" if beside_seat else "room-speech--strip"
  portrait = "" if beside_seat else ashwing_avatar()
  return (f'<div class="room-speech {placement}">{portrait}'
    f'<p class="room-speech__bubble" role="status" aria-label="Ashwing speaks">{html.escape(line)}</p></div>')


def seat_html(player, state, name, index, total, last_action="", is_bot=False, bot_line=""):
  seat_id = player["player_id"]
  angle = math.pi + (2 * math.pi * index / total)
  left = 50 + 37 * math.sin(angle)
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
    marker.append(("D", "Dealer"))
  if seat_id == state["small_blind_player"]:
    marker.append(("SB", "Small blind"))
  if seat_id == state["big_blind_player"]:
    marker.append(("BB", "Big blind"))
  if is_bot:
    marker.append(("BOT", "Bot"))
  marker_html = "".join(f'<span class="seat__badge" title="{label}" aria-label="{label}">{item}</span>' for item, label in marker)
  if player["folded"] and player["in_hand"]:
    status = "Folded"
  elif player["all_in"]:
    status = "All-in"
  elif not player["in_hand"]:
    status = "Out"
  elif state["current_player"] == seat_id:
    status = "Acting now"
  else:
    status = last_action
  if player["in_hand"]:
    cards = player["hole_cards"] if player["hole_cards"] else [None, None]
    card_markup = "".join(card_html(card, hidden=card is None) for card in cards)
  else:
    card_markup = '<span class="seat__footer">No cards</span>'
  revealed = bool(player["hole_cards"]) and not state["hand_over"]
  private = ' role="group" aria-label="Your private hole cards"' if revealed else ""
  cards_class = "seat__cards seat__cards--revealed" if revealed else "seat__cards"
  safe_name = html.escape(str(name), quote=True)
  safe_status = html.escape(str(status), quote=True)
  details = [str(name), f"{player['stack']} chips", f"{player['current_bet']} bet", *(label for _, label in marker)]
  if status:
    details.append(status)
  accessible = html.escape(", ".join(details), quote=True)
  speech = _ashwing_speech(bot_line, beside_seat=True) if bot_line else ""
  bet = f'<span>{player["current_bet"]:,} bet</span>' if player["current_bet"] else ""
  return (f'<article class="{" ".join(classes)}" style="--seat-x:{left:.2f}%;--seat-y:{top:.2f}%" aria-label="{accessible}">'
    f'<div class="seat__identity">{ashwing_avatar() if is_bot else ""}<div class="seat__player">'
    f'<span class="seat__name" title="{safe_name}">{safe_name}</span>'
    f'<div class="seat__stack"><strong>{player["stack"]:,}</strong> chips</div></div>{speech}</div>'
    f'<div class="{cards_class}"{private}>{card_markup}</div>'
    f'<div class="seat__footer">{marker_html}{bet}<span>{safe_status}</span></div></article>')


def table_html(state, names=None, last_actions=None, bot_ids=None, *, reveal_board_from=None, bot_line=""):
  names = names or {}
  last_actions = last_actions or {}
  bot_ids = set(bot_ids or [])
  people = state["players"]
  seats = []
  for index, player in enumerate(people):
    player_id = player["player_id"]
    is_bot = player_id in bot_ids
    seats.append(seat_html(player, state, names.get(player_id, f"Player {player_id}"), index, len(people),
      last_actions.get(player_id, ""), is_bot,
      bot_line=bot_line if len(people) == 2 and is_bot else ""))
  board = "".join(card_html(card, reveal=reveal_board_from is not None and index >= reveal_board_from)
    for index, card in enumerate(state["board"]))
  board += "".join(card_html(empty=True) for _ in range(max(0, 5 - len(state["board"]))))
  current = state["current_player"]
  status = "Pots settled" if state["hand_over"] else f"{names.get(current, f'Player {current}') if current else 'Players'} to act"
  replacements = {
    "__SEAT_LAYOUT__": " data-heads-up" if len(people) == 2 else " data-many-seats" if len(people) > 6 else "",
    "__POT__": f"{state['pot']:,}",
    "__BOARD__": board,
    "__SEATS__": "".join(seats),
    "__BANTER__": _ashwing_speech(bot_line) if bot_ids and bot_line else "",
    "__STATUS__": html.escape(status),
    "__BLINDS__": f"{state['small_blind']:,} / {state['big_blind']:,}",
    "__PLAYERS_LEFT__": str(sum(p["stack"] > 0 or (p["in_hand"] and not p["folded"]) for p in people))
  }
  markup = TEMPLATE
  for key, value in replacements.items():
    markup = markup.replace(key, value)
  return markup
