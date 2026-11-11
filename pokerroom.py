import random
ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
suits = ["♣️","♦️","♠️","♥️"]

def set_deck():
  deck = [(rank,suit) for rank in ranks for suit in suits]
  random.shuffle(deck)
  return deck

def hole_cards(deck):
  hand = random.sample(deck, 2)
  for i in range(2):
    deck.remove(hand[i])
  return hand

def flop(deck):
  flop_deal = random.sample(deck, 3)
  for i in range(3):
    deck.remove(flop_deal[i])
  return flop_deal

def turn(deck):
  turn_deal = random.sample(deck, 1)
  deck.remove(turn_deal[0])
  return turn_deal

def river(deck):
  river_deal = random.sample(deck, 1)
  deck.remove(river_deal[0])
  return river_deal

def set_table(deck):
  table = flop(deck) + turn(deck) + river(deck)
  return table

def cards_on_table(table, hand):
  cards = hand + table
  return cards

def rules(cards):
  highcard = max(cards, key=lambda x: ranks.index(x[0]))
  pair = False
  pair_card = []
  twopair = False
  twopair_card = []
  threeofakind = False
  threeofakind_card = []
  fourofakind = False
  fourofakind_card = []
  straight = False
  straight_cards = []
  flush = False
  flush_cards = []
  fullhouse = False
  fullhouse_cards = []
  straightflush = False
  straightflush_cards = []
  royalflush = False
  royalflush_cards = []

  royalflush_compare_cards = []
  straightflush_compare_cards = []
  fourofakind_compare_card = []
  fullhouse_compare_cards = []
  flush_compare_cards = []
  straight_compare_cards = []
  threeofakind_compare_card = []
  twopair_compare_card = []
  pair_compare_card = []
  highcard_compare = []

  frequency = {"A":0,"2":0,"3":0,"4":0,"5":0,"6":0,"7":0,"8":0,"9":0,"10":0,"J":0,"Q":0,"K":0}
  for card in cards:
    frequency[card[0]] += 1

  for key in frequency:
    if frequency[key] == 2:
      pair = True
      pair_card.append(key)
    if frequency[key] == 3:
      threeofakind = True
      threeofakind_card.append(key)
    if frequency[key] == 4:
      fourofakind = True
      fourofakind_card.append(key)

  if (threeofakind and pair) or (len(threeofakind_card) == 2) or (fourofakind and threeofakind) or (fourofakind and pair):
    fullhouse = True
    cards_full = [max([card for card in frequency if frequency[card] >= 3], key=lambda x: ranks.index(x)), max(pair_card, key=lambda x: ranks.index(x)) if pair_card else max([card for card in frequency if frequency[card] >= 2 and card != max([c for c in frequency if frequency[c] >= 3], key=lambda x: ranks.index(x))], key=lambda x: ranks.index(x))]
    fullhouse_cards.extend(cards_full)

  if len(pair_card) >= 2:
    twopair = True
    twopair_card.extend(sorted(pair_card, key=lambda x: ranks.index(x), reverse = True)[0:2])

  for card in cards:
    if card[0] not in straight_cards:
      straight_cards.append(card[0])

  straight_cards.sort(key=lambda x: ranks.index(x))

  AceLow = straight_cards.copy()

  while len(straight_cards)>=5:
    for i in range(len(straight_cards)-1,len(straight_cards)-5,-1):
      if ranks.index(straight_cards[i]) == ranks.index(straight_cards[i-1])+1:
        straight = True
      else:
        straight = False
        break
    if straight:
      break
    else:
      straight_cards.pop(-1)

  if straight and len(straight_cards) >= 5:
    straight_cards = straight_cards[-5:]

  if not straight:
    reqd = ["A","2","3","4","5"]
    if all(card in AceLow for card in reqd):
      straight = True
      straight_cards = ["A","2","3","4","5"]
    else:
      straight = False
      straight_cards = []

  frequency_suits = {"♣️":0,"♦️":0,"♠️":0,"♥️":0}
  for card in cards:
    frequency_suits[card[1]] += 1

  if frequency_suits["♣️"] >= 5 or frequency_suits["♦️"] >= 5 or frequency_suits["♠️"] >= 5 or frequency_suits["♥️"] >= 5:
    flush = True
    straightflush_cards.extend([card[0] for card in cards if card[1] in [suit for suit in frequency_suits if frequency_suits[suit] >= 5]])
    flush_cards.extend(sorted([card for card in cards if card[1] in [suit for suit in frequency_suits if frequency_suits[suit] >= 5]], key=lambda x: ranks.index(x[0]), reverse = True)[:5])

  straightflush_cards.sort(key=lambda x: ranks.index(x))
  AceLowFlush = straightflush_cards.copy()
  while len(straightflush_cards)>=5:
    for i in range(len(straightflush_cards)-1,len(straightflush_cards)-5,-1):
      if ranks.index(straightflush_cards[i]) == ranks.index(straightflush_cards[i-1])+1:
        straightflush = True
      else:
        straightflush = False
        break
    if straightflush:
      break
    else:
      straightflush_cards.pop(-1)

  if straightflush and len(straightflush_cards) >= 5:
    straightflush_cards = straightflush_cards[-5:]

  if not straightflush:
    reqd = ["A","2","3","4","5"]
    if all(card in AceLowFlush for card in reqd):
      straightflush = True
      straightflush_cards = ["A","2","3","4","5"]
    else:
      straightflush = False
      straightflush_cards = []

  if straightflush:
    reqd = ["A","K","Q","J","10"]
    if all(card in straightflush_cards for card in reqd):
      royalflush = True
      royalflush_cards.extend(straightflush_cards)

  highcard_compare = [card[0] for card in sorted(cards, key=lambda x: ranks.index(x[0]), reverse=True)[:5]]
  if pair:
    pair_compare_card = [max([card for card in frequency if frequency[card] == 2], key=lambda x: ranks.index(x))] + sorted([card for card in frequency if frequency[card]>0 and card != max([card for card in frequency if frequency[card] == 2], key=lambda x: ranks.index(x))], key=lambda x: ranks.index(x), reverse = True)[:3]

  if twopair:
    twopair_compare_card = sorted(twopair_card, key=lambda x: ranks.index(x), reverse = True)[:2]+[max([card for card in frequency if frequency[card] > 0 and card not in twopair_card], key=lambda x: ranks.index(x))]

  if threeofakind:
    threeofakind_compare_card = [max([card for card in frequency if frequency[card] == 3], key=lambda x: ranks.index(x))] + sorted([card for card in frequency if frequency[card]>0 and card != max([card for card in frequency if frequency[card] == 3], key=lambda x: ranks.index(x))], key=lambda x: ranks.index(x), reverse = True)[:2]

  if fourofakind:
    fourofakind_compare_card = [max([card for card in frequency if frequency[card] == 4], key=lambda x: ranks.index(x))] + sorted([card for card in frequency if frequency[card]>0 and card != max([card for card in frequency if frequency[card] == 4], key=lambda x: ranks.index(x))], key=lambda x: ranks.index(x), reverse = True)[:1]

  if fullhouse:
    fullhouse_compare_cards = fullhouse_cards.copy()

  if straight:
    straight_compare_cards = [straight_cards[-1]]

  if straightflush:
    straightflush_compare_cards = [straightflush_cards[-1]]

  if flush:
    flush_compare_cards = [card[0] for card in flush_cards]

  if royalflush:
    royalflush_compare_cards = [royalflush_cards[-1]]

  detected = {"Royal Flush": royalflush, "Straight Flush": straightflush, "4 of a kind": fourofakind, "Full House": fullhouse, "Flush": flush, "Straight": straight, "3 of a kind": threeofakind, "2 Pair": twopair, "Pair": pair, "High Card": True}
  detected_cards = {"Royal Flush": royalflush_compare_cards, "Straight Flush": straightflush_compare_cards, "4 of a kind": fourofakind_compare_card, "Full House": fullhouse_compare_cards, "Flush": flush_compare_cards, "Straight": straight_compare_cards, "3 of a kind": threeofakind_compare_card, "2 Pair": twopair_compare_card, "Pair": pair_compare_card, "High Card": highcard_compare}
  return [detected, detected_cards]

def highest_hand(cards):
  win_ranks = {"High Card": 1, "Pair": 2, "2 Pair": 3, "3 of a kind": 4, "Straight": 5, "Flush": 6, "Full House": 7, "4 of a kind": 8, "Straight Flush": 9, "Royal Flush": 10}
  detected, detected_cards = rules(cards)
  valid = []
  for i in detected.keys():
    if detected[i]:
      valid.append(i)

  return max(valid, key=lambda x: win_ranks[x]), detected_cards[max(valid, key=lambda x: win_ranks[x])]

def compare(hands):
  if not hands:
    print("Game Could Not Start")
    return

  categories = {"Royal Flush": 0, "Straight Flush": 0, "4 of a kind": 0, "Full House": 0, "Flush": 0, "Straight": 0, "3 of a kind": 0, "2 Pair": 0, "Pair": 0, "High Card": 0}
  for hand in hands.values():
    categories[hand[0]] += 1

  highest_play = ""
  for i in categories.keys():
    if categories[i]>0:
      highest_play = i
      break

  valid_hands = [hand for hand in hands.values() if hand[0] == highest_play]

  rank_values = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}
  compare_tuples = []
  for hand in valid_hands:
    t = ()
    for i in hand[1]:
      t+=(rank_values[i],)
    compare_tuples.append(t)

  max_strength = max(compare_tuples)
  winning_hands = [hand for hand in hands.keys() if tuple(rank_values[card] for card in hands[hand][1]) == max_strength and hands[hand][0] == highest_play]

  return winning_hands

"""# **Gameplay Flow**"""

class Player:
  def __init__(self, player_id, starting_chips=1000):
    self.player_id = player_id
    self.stack = starting_chips
    self.hole_cards = []
    self.current_bet = 0
    self.total_bet = 0
    self.folded = False
    self.all_in = False
    self.in_hand = False
    self.acted_bet = None

class GameManager:
  def __init__(self, players, small_blind=5, big_blind=10) -> None:
    if not 2 <= len(players) <= 10:
      raise ValueError("Number of players must be between 2 and 10")

    if len(set(p.player_id for p in players)) != len(players):
      raise ValueError("Player IDs must be unique")

    if any(type(p.stack) is not int or p.stack < 0 for p in players):
      raise ValueError("Player stacks must be nonnegative integers")

    if sum(p.stack > 0 for p in players) < 2:
      raise ValueError("At least two players must have chips")

    if type(small_blind) is not int or type(big_blind) is not int or not 0 < small_blind < big_blind:
      raise ValueError("Invalid blind amounts")

    self.players = players
    self.deck = []
    self.board = []
    self.burned_cards = []
    self.pot = 0
    self.small_blind = small_blind
    self.big_blind = big_blind
    self.phase = "not_started"
    self.dealer_index = self.players.index(min([p for p in players if p.stack > 0], key=lambda x: x.player_id))
    self.sb_index = None
    self.bb_index = None
    self.current_player = None
    self.min_raise_increment = big_blind
    self.table_bet = 0
    self.pending_to_act = set()
    self.winners = []
    self.payouts = {}
    self.uncalled_returns = {}
    self.pot_results = []
    self.showdown_hands = {}
    self.blind_posted = False
    self.hand_over = True
    self.game_over = False
    self.hand_number = 0
    self.round_ready = False
    self.full_bet_made = False
    self.last_error = ""

  def seated_players(self):
    return [p for p in self.players if p.in_hand]

  def remaining_players(self):
    return [p for p in self.players if p.in_hand and not p.folded]

  def able_to_bet(self):
    return [p for p in self.remaining_players() if not p.all_in and p.stack > 0]

  def next_seated_index(self, index, allowed=None):
    if allowed is None:
      allowed = {p for p in self.players if p.stack > 0}

    for step in range(1, len(self.players) + 1):
      next_index = (index + step) % len(self.players)
      if self.players[next_index] in allowed:
        return next_index

    return None

  def assign_positions(self, rotate=False):
    active_players = [p for p in self.players if p.stack > 0]

    if len(active_players) < 2:
      self.game_over = True
      return False

    active = set(active_players)

    if rotate or self.players[self.dealer_index] not in active:
      self.dealer_index = self.next_seated_index(self.dealer_index, active)

    if len(active_players) == 2:
      self.sb_index = self.dealer_index
      self.bb_index = self.next_seated_index(self.sb_index, active)
      self.current_player = self.sb_index
    else:
      self.sb_index = self.next_seated_index(self.dealer_index, active)
      self.bb_index = self.next_seated_index(self.sb_index, active)
      self.current_player = self.next_seated_index(self.bb_index, active)

    return True

  def restart_game(self):
    if self.hand_number > 0 and (not self.hand_over or self.pot != 0):
      return False

    if sum(p.stack > 0 for p in self.players) < 2:
      self.game_over = True
      return False

    if not self.assign_positions(self.hand_number > 0):
      return False

    self.deck = set_deck()
    self.board = []
    self.burned_cards = []
    self.pot = 0
    self.phase = "preflop"
    self.table_bet = 0
    self.min_raise_increment = self.big_blind
    self.pending_to_act.clear()
    self.winners = []
    self.payouts = {}
    self.uncalled_returns = {}
    self.pot_results = []
    self.showdown_hands = {}
    self.blind_posted = False
    self.hand_over = False
    self.full_bet_made = True
    self.round_ready = True
    self.last_error = ""

    for player in self.players:
      player.hole_cards = []
      player.current_bet = 0
      player.total_bet = 0
      player.folded = player.stack == 0
      player.all_in = False
      player.in_hand = player.stack > 0
      player.acted_bet = None

    return True

  def commit_chips(self, player, amount):
    if type(amount) is not int or amount < 0 or amount > player.stack:
      return False

    player.stack -= amount
    player.current_bet += amount
    player.total_bet += amount
    self.pot += amount

    if player.stack == 0:
      player.all_in = True

    return True

  def post_blind(self):
    if self.blind_posted or self.phase != "preflop" or self.hand_over:
      return False

    sb = self.players[self.sb_index]
    bb = self.players[self.bb_index]
    self.commit_chips(sb, min(sb.stack, self.small_blind))
    self.commit_chips(bb, min(bb.stack, self.big_blind))
    self.table_bet = self.big_blind
    self.min_raise_increment = self.big_blind
    self.full_bet_made = True
    self.blind_posted = True
    return True

  def deal_hole_cards(self):
    if not self.blind_posted or any(p.hole_cards for p in self.players):
      return False

    seats = set(self.seated_players())
    first_index = self.sb_index

    for i in range(2):
      for step in range(len(self.players)):
        index = (first_index + step) % len(self.players)
        player = self.players[index]
        if player in seats:
          player.hole_cards.append(self.deck.pop())

    return True

  def start_round(self):
    if not self.round_ready and not self.restart_game():
      return False

    if self.hand_over or self.blind_posted:
      return False

    self.round_ready = False
    self.post_blind()
    self.deal_hole_cards()
    self.pending_to_act = set(self.able_to_bet())

    self._skip_uncontested_action()

    if self.pending_to_act:
      first = self.players[self.current_player]
      self.current_player = self.players.index(self.next_active_player(first, include_start=True))
    else:
      self.current_player = None

    self.hand_number += 1
    self.update_game_state()
    return True

  def start_next_round(self):
    if self.hand_number == 0 or not self.hand_over:
      return False

    return self.start_round()

  def next_active_player(self, player, include_start=False):
    start_index = self.players.index(player)
    first_step = 0 if include_start else 1

    for step in range(first_step, len(self.players)):
      next_index = (start_index + step) % len(self.players)
      candidate = self.players[next_index]

      if candidate in self.pending_to_act and candidate in self.able_to_bet():
        return candidate

    return None

  def betting_round_complete(self):
    if self.hand_over:
      return True

    if self.pending_to_act:
      return False

    active_players = self.able_to_bet()

    if len(active_players) < 2:
      return True

    return all(p.current_bet == self.table_bet for p in active_players)

  def advance_phase(self):
    if self.hand_over or not self.betting_round_complete():
      return False

    if self.phase == "preflop":
      self.burned_cards.append(self.deck.pop())
      self.board.extend(self.deck.pop() for i in range(3))
      self.phase = "flop"
    elif self.phase == "flop":
      self.burned_cards.append(self.deck.pop())
      self.board.append(self.deck.pop())
      self.phase = "turn"
    elif self.phase == "turn":
      self.burned_cards.append(self.deck.pop())
      self.board.append(self.deck.pop())
      self.phase = "river"
    elif self.phase == "river":
      self.phase = "showdown"
      return self.showdown()
    else:
      return False

    for player in self.players:
      player.current_bet = 0
      player.acted_bet = None

    self.table_bet = 0
    self.min_raise_increment = self.big_blind
    self.full_bet_made = False
    self.pending_to_act = set(self.able_to_bet()) if len(self.able_to_bet()) >= 2 else set()
    self.current_player = None

    if self.pending_to_act:
      for step in range(1, len(self.players) + 1):
        index = (self.dealer_index + step) % len(self.players)
        if self.players[index] in self.pending_to_act:
          self.current_player = index
          break

    return True

  def update_game_state(self):
    if self.hand_over:
      return self.phase

    remaining = self.remaining_players()

    if len(remaining) == 1:
      self.showdown()
      return self.phase

    if self.phase in ("showdown", "hand_over"):
      return self.phase

    while self.betting_round_complete() and not self.hand_over:
      if not self.advance_phase():
        break

    return self.phase

  def _reject(self, message):
    self.last_error = message
    return False

  def can_act(self, player):
    return (not self.hand_over and self.current_player is not None
      and player is self.players[self.current_player]
      and player in self.pending_to_act
      and player in self.able_to_bet())

  def _call_amount(self, player):
    target = self.table_bet
    if len(self.able_to_bet()) == 1:
      # A short blind can set a nominal bring-in only while betting is possible.
      target = max(p.current_bet for p in self.remaining_players())
    return max(0, target - player.current_bet)

  def _skip_uncontested_action(self):
    able = self.able_to_bet()
    if not able or (len(able) == 1 and self._call_amount(able[0]) == 0):
      self.pending_to_act.clear()

  def finish_action(self, player, raised=False):
    self.last_error = ""

    if raised:
      self.pending_to_act = {
        p for p in self.able_to_bet()
        if p is not player and (p.current_bet < self.table_bet or p in self.pending_to_act)
      }
    else:
      self.pending_to_act.discard(player)

    self._skip_uncontested_action()
    next_player = self.next_active_player(player)
    self.current_player = self.players.index(next_player) if next_player is not None else None
    self.update_game_state()
    return True

  def fold(self, player):
    if not self.can_act(player):
      return self._reject("Player cannot fold right now")

    player.folded = True
    player.acted_bet = self.table_bet
    return self.finish_action(player)

  def check(self, player):
    if not self.can_act(player):
      return self._reject("Player cannot check right now")

    if self._call_amount(player):
      return self._reject("Cannot check: chips still owed")

    player.acted_bet = self.table_bet
    return self.finish_action(player)

  def call(self, player):
    if not self.can_act(player):
      return self._reject("Player cannot call right now")

    call_amount = self._call_amount(player)

    if call_amount == 0:
      return self._reject("Nothing to call. Use check instead")

    self.commit_chips(player, min(player.stack, call_amount))
    player.acted_bet = self.table_bet
    return self.finish_action(player)

  def raise_bet(self, player, amount):
    if not self.can_act(player):
      return self._reject("Player cannot raise right now")

    if type(amount) is not int or amount <= 0:
      return self._reject("Invalid raise amount")

    if amount > player.stack:
      return self._reject("Insufficient chips")

    other_active = [p for p in self.able_to_bet() if p is not player]

    if not other_active:
      return self._reject("No opponent available to respond")

    if player.acted_bet is not None and self.table_bet - player.acted_bet < self.min_raise_increment:
      return self._reject("Betting has not reopened for this player")

    new_total = player.current_bet + amount

    if new_total <= self.table_bet:
      return self._reject("Raise must increase the table bet")

    minimum_total = self.table_bet + self.min_raise_increment if self.full_bet_made else self.big_blind
    full_raise = new_total >= minimum_total
    all_in_raise = amount == player.stack

    if not full_raise and not all_in_raise:
      return self._reject(f"Minimum total bet required: {minimum_total}")

    previous_table_bet = self.table_bet
    self.commit_chips(player, amount)
    self.table_bet = new_total
    player.acted_bet = self.table_bet

    if full_raise:
      self.min_raise_increment = new_total - previous_table_bet if self.full_bet_made else new_total
      self.full_bet_made = True

    return self.finish_action(player, raised=True)

  def all_in(self, player):
    if not self.can_act(player):
      return self._reject("Player cannot go all-in right now")

    if player.stack <= 0:
      return self._reject("Player has no chips")

    if player.stack <= self._call_amount(player):
      return self.call(player)

    return self.raise_bet(player, player.stack)

  def clockwise_winners(self, winners):
    winning_set = set(winners)
    ordered = []

    for step in range(1, len(self.players) + 1):
      index = (self.dealer_index + step) % len(self.players)
      player = self.players[index]
      if player in winning_set:
        ordered.append(player)

    return ordered

  def distribute_pot(self, amount, winners):
    ordered = self.clockwise_winners(winners)

    if not ordered:
      return {}

    share = amount // len(ordered)
    leftover = amount % len(ordered)
    awarded = {}

    for i, player in enumerate(ordered):
      chips = share + (1 if i < leftover else 0)
      player.stack += chips
      self.payouts[player.player_id] = self.payouts.get(player.player_id, 0) + chips
      awarded[player.player_id] = chips

    return awarded

  def showdown(self):
    if self.hand_over:
      return False

    remaining = self.remaining_players()

    if self.phase != "showdown" and len(remaining) != 1:
      return False

    if not remaining:
      return False

    if len(remaining) > 1 and len(self.board) != 5:
      return False

    contributions = {p: p.total_bet for p in self.players}
    largest, second = sorted(contributions.values(), reverse=True)[:2]
    if largest > second:
      player = next(p for p, amount in contributions.items() if amount == largest)
      refund = largest - second
      contributions[player] -= refund
      self.pot -= refund
      player.stack += refund
      self.uncalled_returns[player.player_id] = refund

    if len(remaining) == 1:
      player = remaining[0]
      self.distribute_pot(self.pot, [player])
      self.pot_results.append({"amount":self.pot,"eligible":[player.player_id],"winners":[player.player_id],"payouts":{player.player_id:self.pot}})
    else:
      self.showdown_hands = {
        p.player_id:highest_hand(p.hole_cards + self.board)
        for p in remaining
      }
      levels = sorted({amount for amount in contributions.values() if amount > 0})
      previous_level = 0

      for level in levels:
        contributing = [p for p in self.players if contributions[p] >= level]
        amount = (level - previous_level) * len(contributing)
        eligible = [p for p in remaining if contributions[p] >= level]

        if not eligible:
          eligible = remaining

        if len(eligible) == 1:
          winners = eligible
        else:
          hands = {p.player_id:self.showdown_hands[p.player_id] for p in eligible}
          winning_ids = compare(hands)
          winners = [p for p in eligible if p.player_id in winning_ids]

        awarded = self.distribute_pot(amount, winners)
        self.pot_results.append({"amount":amount,"eligible":[p.player_id for p in eligible],"winners":[p.player_id for p in winners],"payouts":awarded})
        previous_level = level

    self.winners = [p.player_id for p in self.clockwise_winners([p for p in self.players if self.payouts.get(p.player_id, 0) > 0])]
    self.pot = 0
    self.pending_to_act.clear()
    self.current_player = None
    self.phase = "hand_over"
    self.hand_over = True
    self.game_over = sum(p.stack > 0 for p in self.players) < 2
    return True

  def get_state(self, player_id=None):
    players = []

    for player in self.players:
      players.append({
        "player_id":player.player_id,
        "stack":player.stack,
        "current_bet":player.current_bet,
        "total_bet":player.total_bet,
        "folded":player.folded,
        "all_in":player.all_in,
        "in_hand":player.in_hand,
        "hole_cards":player.hole_cards.copy() if (player.player_id == player_id or (self.hand_over and player.player_id in self.showdown_hands)) else []
      })

    return {
      "hand_number":self.hand_number,
      "phase":self.phase,
      "dealer":self.players[self.dealer_index].player_id,
      "small_blind_player":self.players[self.sb_index].player_id if self.sb_index is not None else None,
      "big_blind_player":self.players[self.bb_index].player_id if self.bb_index is not None else None,
      "current_player":self.players[self.current_player].player_id if self.current_player is not None else None,
      "small_blind":self.small_blind,
      "big_blind":self.big_blind,
      "table_bet":self.table_bet,
      "min_raise_increment":self.min_raise_increment,
      "pot":self.pot,
      "board":self.board.copy(),
      "players":players,
      "pending_to_act":[p.player_id for p in self.players if p in self.pending_to_act],
      "winners":self.winners.copy(),
      "payouts":self.payouts.copy(),
      "uncalled_returns":self.uncalled_returns.copy(),
      "pot_results":self.pot_results.copy(),
      "showdown_hands":self.showdown_hands.copy() if self.hand_over else {},
      "hand_over":self.hand_over,
      "game_over":self.game_over,
      "last_error":self.last_error
    }

  def legal_actions(self, player=None):
    if player is None and self.current_player is not None:
      player = self.players[self.current_player]

    if player is None or not self.can_act(player):
      return {"fold":False,"check":False,"call":False,"raise":False,"all_in":False}

    call_amount = self._call_amount(player)
    min_total = self.table_bet + self.min_raise_increment if self.full_bet_made else self.big_blind
    other_active = any(p is not player for p in self.able_to_bet())
    can_reopen = player.acted_bet is None or self.table_bet - player.acted_bet >= self.min_raise_increment
    max_total = player.current_bet + player.stack
    can_raise = other_active and can_reopen and max_total > self.table_bet

    return {
      "fold":True,
      "check":call_amount == 0,
      "call":call_amount > 0,
      "call_amount":min(player.stack, call_amount),
      "raise":can_raise,
      "all_in":player.stack > 0 and (call_amount >= player.stack or can_raise),
      "min_raise_total":min_total if can_raise else None,
      "max_raise_total":max_total if can_raise else None
    }

def start_game(player_count=5, starting_chips=1000, small_blind=5, big_blind=10):
  if type(player_count) is not int or not 2 <= player_count <= 10:
    raise ValueError("Number of players must be between 2 and 10")

  if type(starting_chips) is not int or starting_chips <= 0:
    raise ValueError("Starting chips must be a positive integer")

  players = [Player(i+1, starting_chips) for i in range(player_count)]
  startgame = GameManager(players, small_blind, big_blind)
  startgame.start_round()
  return startgame

'''
POKERROOM - PLAYABLE INTERFACE REFERENCE

1. STARTING A GAME

start_game(player_count)
  - Creates a new GameManager object.
  - Initializes players with their starting chips.
  - Shuffles the deck and deals hole cards.
  - Assigns the dealer, small blind and big blind.
  - Posts blinds and initializes the first betting round.
  - Returns a GameManager object.
  - Call when the user clicks "New Game".

Example:
  game = start_game(5)


2. RETRIEVING GAME INFORMATION

game.get_state()
  - Returns the public game state as a dictionary.
  - Call whenever the interface needs to refresh.

game.get_state(player_id)
  - Returns the game state with the specified player's private cards visible.
  - Use only for that player's private view.

Important state fields:
  hand_number         - Current hand number
  phase               - preflop, flop, turn, river or hand_over
  dealer              - Dealer player ID
  small_blind_player  - Small blind player ID
  big_blind_player    - Big blind player ID
  current_player      - Player ID whose turn it is
  pot                 - Total chips in the pot
  board               - Community cards
  players             - Player stacks, bets and statuses
  table_bet           - Current highest bet for this street
  pending_to_act      - Players still required to act
  winners             - Winning player IDs
  payouts             - Chips awarded to each winner
  pot_results         - Main pot and side-pot results
  showdown_hands      - Evaluated hands at showdown
  hand_over           - Whether the hand has ended
  game_over           - Whether the game has ended
  last_error          - Most recent error message


3. CHECKING AVAILABLE ACTIONS

game.legal_actions(player)
  - Returns a dictionary of available actions.
  - Call whenever displaying the current player's controls.
  - Use the results to enable or disable buttons.

Important fields:
  fold                - Whether the player can fold
  check               - Whether the player can check
  call                - Whether the player can call
  call_amount         - Chips required to call
  raise               - Whether the player can raise
  all_in              - Whether the player can go all-in
  min_raise_total     - Minimum permitted total bet
  max_raise_total     - Maximum permitted total bet

Example:
  player = game.players[game.current_player]
  legal = game.legal_actions(player)


4. PLAYER ACTIONS

game.fold(player)
  - Fold button.
  - Removes the player from the current hand.
  - Returns True on success, otherwise False.

game.check(player)
  - Check button.
  - Passes without betting when no chips are owed.
  - Returns True on success, otherwise False.

game.call(player)
  - Call button.
  - Matches the current bet or commits remaining chips
    when the player cannot afford the full call.
  - Returns True on success, otherwise False.

game.raise_bet(player, amount)
  - Raise button.
  - The amount is ADDITIONAL chips contributed,
    not the final total bet.
  - Validates minimum raises and available stack.
  - Returns True on success, otherwise False.

Example:
  game.raise_bet(player, 30)

game.all_in(player)
  - All-in button.
  - Commits the player's remaining chips.
  - Handles full raises and short all-ins.
  - Returns True on success, otherwise False.

IMPORTANT:
  After a successful action, refresh get_state().
  Do not manually update stacks, pots, bets or turns.


5. STARTING THE NEXT HAND

game.start_next_round()
  - Call when the player clicks "Next Hand".
  - Only allowed after the current hand finishes.
  - Preserves player stacks.
  - Rotates the dealer and assigns new blind positions.
  - Skips eliminated players.
  - Creates a new deck and deals fresh hole cards.
  - Posts blinds and starts preflop.
  - Returns True on success, otherwise False.


6. FUNCTIONS THE INTERFACE SHOULD NOT CALL DIRECTLY

GameManager.__init__()
restart_game()
start_round()
assign_positions()
post_blind()
deal_hole_cards()
commit_chips()
next_active_player()
betting_round_complete()
advance_phase()
update_game_state()
finish_action()
can_act()
showdown()
distribute_pot()
clockwise_winners()
rules()
highest_hand()
compare()
set_deck()
hole_cards()
flop()
turn()
river()

These functions are used internally by the game engine.
The interface should not manually control dealing,
turn advancement, showdown or pot distribution.


7. INTERFACE GAME LOOP

STEP 1:
  Start a new session using start_game(player_count).

STEP 2:
  Store the returned GameManager object.
  For Streamlit, use st.session_state.

STEP 3:
  Call get_state() to display:
    - Player stacks
    - Pot
    - Community cards
    - Dealer and blinds
    - Current betting phase
    - Current player's turn

STEP 4:
  For the current player:
    - Call get_state(player_id) for private cards.
    - Call legal_actions(player).
    - Display the allowed action buttons.

STEP 5:
  When an action button is clicked:
    - Call the corresponding GameManager method.
    - Check whether it returned True.
    - Refresh the game state.
    - If False, display game.last_error.

STEP 6:
  Repeat until hand_over becomes True.
  The engine automatically advances betting streets,
  reveals community cards, evaluates hands and pays pots.

STEP 7:
  Display:
    - Winners
    - Hand rankings
    - Pot and side-pot payouts
    - Remaining player stacks

STEP 8:
  If game_over is False:
    - Display the Next Hand button.
    - Call start_next_round() when clicked.

  If game_over is True:
    - Display the final winner.
    - Offer a New Game button.


8. IMPORTANT INTERFACE RULES

- Never change player.stack directly.
- Never change game.pot directly.
- Never manually change game.phase.
- Never call showdown() from a button.
- Never call post_blind() from the interface.
- Never deal cards manually.
- Never recreate GameManager after each action.
- Never expose other players' private hole cards.
- Never allow actions when hand_over is True.
- Always check legal_actions() before enabling controls.
- Store the GameManager object between UI refreshes.

For pass-and-play:
  Hide the previous player's cards before revealing
  the next player's cards.

For online multiplayer:
  Keep GameManager on a trusted server.
  Never trust a player_id supplied by the client
  without verifying the player's identity and turn.


9. TOTAL PUBLIC INTERFACE FUNCTIONS

1. start_game(player_count)
2. game.get_state(player_id=None)
3. game.legal_actions(player)
4. game.fold(player)
5. game.check(player)
6. game.call(player)
7. game.raise_bet(player, amount)
8. game.all_in(player)
9. game.start_next_round()

Everything else is managed automatically.

INTERFACE RESPONSIBILITY:
  Display information, collect player input,
  call the appropriate method and refresh the screen.

GAME ENGINE RESPONSIBILITY:
  Enforce poker rules, update stacks, rotate turns,
  deal cards, calculate pots, evaluate hands,
  determine winners and distribute payouts.
'''