from collections import Counter
from dataclasses import dataclass
from random import Random

from equity import exact_river_equity, sample_equity
from poker_engine import highest_hand


@dataclass(frozen=True)
class Observation:
  hole: tuple
  board: tuple
  stack: int
  stacks: tuple
  current_bet: int
  table_bet: int
  big_blind: int
  pot: int
  late_position: bool
  opponents: int
  legal: dict
  effective_raise_total: int
  has_all_in_opponent: bool


def calling_station(view, rng):
  if view.legal["check"]:
    return "check", None
  if view.legal["call"]:
    return "call", None
  raise ValueError("Calling Station requires a legal check or call")


def observe(game, player):
  state = game.get_state(player.player_id)
  seats = [seat for seat in state["players"] if seat["in_hand"]]
  ids = [seat["player_id"] for seat in seats]
  dealer_index = ids.index(state["dealer"])
  late_seats = {state["dealer"]}
  if len(ids) >= 4:
    late_seats.add(ids[dealer_index - 1])
  own = next(seat for seat in seats if seat["player_id"] == player.player_id)
  opponents = [seat for seat in seats if not seat["folded"] and seat["player_id"] != player.player_id]
  respond_to = max((seat["current_bet"] + seat["stack"]
    for seat in opponents if not seat["all_in"]), default=0)
  return Observation(
    hole=tuple(own["hole_cards"]), board=tuple(state["board"]), stack=own["stack"],
    stacks=tuple((seat["player_id"], seat["stack"]) for seat in seats),
    current_bet=own["current_bet"], table_bet=state["table_bet"],
    big_blind=state["big_blind"], pot=state["pot"], late_position=player.player_id in late_seats,
    opponents=len(opponents), legal=game.legal_actions(player),
    effective_raise_total=min(own["current_bet"] + own["stack"], respond_to),
    has_all_in_opponent=any(seat["all_in"] for seat in opponents),
  )


class BotArena:
  def __init__(self, seed, styles):
    self.seed = seed
    self.styles = tuple(styles)
    seeds = Random(seed)
    self.deck_rng = Random(seeds.getrandbits(64))
    self.bot_rngs = [Random(seeds.getrandbits(64)) for _ in self.styles]

  def act(self, game, player):
    seat = player.player_id - 1
    view = observe(game, player)
    action, target = STRATEGIES[self.styles[seat]](view, self.bot_rngs[seat])
    if not view.legal.get(action):
      raise ValueError(f"Bot selected an illegal action: {action}")
    if action == "raise":
      minimum = min(view.legal["min_raise_total"], view.legal["max_raise_total"])
      if type(target) is not int or not minimum <= target <= view.legal["max_raise_total"]:
        raise ValueError("Bot selected an illegal raise target")
      return action, game.raise_bet(player, target - view.current_bet)
    return action, getattr(game, action)(player)


def _min_raise(view):
  return "raise", min(view.legal["min_raise_total"], view.legal["max_raise_total"])


def random_bot(view, rng):
  actions = [action for action in ("check", "call", "fold", "raise", "all_in")
    if view.legal[action]]
  action = rng.choice(actions)
  return _min_raise(view) if action == "raise" else (action, None)


RANKS = {rank: value for value, rank in enumerate("2 3 4 5 6 7 8 9 10 J Q K A".split(), 2)}


def _preflop(view, loose):
  high, low = sorted((RANKS[rank] for rank, _ in view.hole), reverse=True)
  suited = view.hole[0][1] == view.hole[1][1]
  if high == low >= 10 or (high == 14 and (low >= 12 or (low == 11 and suited))):
    return "strong"
  if loose and view.late_position and view.table_bet == view.big_blind:
    if (high == low and high >= 6) or (suited and (high == 14 or (low >= 6 and high - low == 1))):
      return "strong"
  return "weak"


def _postflop(view):
  category, score = highest_hand(list(view.hole + view.board))
  if len(view.board) == 5 and highest_hand(list(view.board)) == (category, score):
    return "weak"
  counts = Counter(rank for rank, _ in view.board)
  hole_ranks = {rank for rank, _ in view.hole}
  if category == "High Card":
    return "weak"
  if category == "Pair":
    return "medium" if score[0] in hole_ranks else "weak"
  if category in ("2 Pair", "3 of a kind", "4 of a kind"):
    required = {"2 Pair": (2, 2), "3 of a kind": (3,), "4 of a kind": (4,)}[category]
    return "strong" if any(counts[rank] < size for rank, size in zip(score, required)) else "medium"
  return "strong"


def _has_draw(view):
  cards = view.hole + view.board
  suits = Counter(suit for _, suit in cards)
  if any(suits[suit] == 4 for _, suit in view.hole):
    return True
  board_ranks = {RANKS[rank] for rank, _ in view.board}
  all_ranks = {RANKS[rank] for rank, _ in cards}
  for low in range(1, 11):
    window = {14, 2, 3, 4, 5} if low == 1 else set(range(low, low + 5))
    if len(window & all_ranks) == 4 and window & (all_ranks - board_ranks):
      return True
  return False


def _value_strategy(view, rng, loose):
  strength = _postflop(view) if view.board else _preflop(view, loose)
  can_raise = view.legal["raise"]
  if strength == "strong" and can_raise:
    return _min_raise(view)
  if loose and can_raise and view.board and view.legal["check"] and view.opponents == 1:
    draw = len(view.board) < 5 and _has_draw(view)
    if rng.random() < (0.45 if draw else 0.08):
      return _min_raise(view)
  if view.legal["check"]:
    return "check", None
  affordable = view.legal["call_amount"] <= min(view.stack // 4, view.pot // 3)
  if view.legal["call"] and (strength == "strong" or (strength == "medium" and affordable)):
    return "call", None
  return "fold", None


def tight(view, rng):
  return _value_strategy(view, rng, loose=False)


def loose_aggressive(view, rng):
  return _value_strategy(view, rng, loose=True)


def equity_bot(view, rng):
  legal = view.legal
  call = legal["call_amount"]
  # A partial call or multiway all-in can expose less than the displayed pot.
  if call < view.table_bet - view.current_bet or (view.opponents > 1 and view.has_all_in_opponent):
    return tight(view, rng)

  if len(view.board) == 5 and view.opponents == 1:
    share = exact_river_equity(view.hole, view.board).equity
  else:
    trials = 256 if view.opponents <= 3 else 128
    share = sample_equity(view.hole, view.board, view.opponents, trials, rng).equity

  cushion = 0.04 if len(view.board) < 5 else 0
  if legal["call"] and share < call / (view.pot + call) + cushion:
    return "fold", None

  value_threshold = max(0.35, 1 / (view.opponents + 1) + 0.17)
  if not view.board and view.late_position and view.table_bet == view.big_blind:
    value_threshold -= 0.06

  if legal["raise"] and share >= value_threshold:
    minimum = min(legal["min_raise_total"], legal["max_raise_total"])
    maximum = min(legal["max_raise_total"], view.effective_raise_total)
    if minimum <= maximum:
      raise_size = max(view.big_blind, (view.pot + call) * 2 // 3)
      return "raise", min(maximum, max(minimum, view.table_bet + raise_size))
  return calling_station(view, rng)


STRATEGIES = {
  "Calling Station": calling_station,
  "Random": random_bot,
  "Tight": tight,
  "Loose-Aggressive": loose_aggressive,
  "Equity": equity_bot,
}
