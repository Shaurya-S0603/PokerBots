import random

from poker_engine import highest_hand


class PokerBot:
  def __init__(self, difficulty="Easy", bluff_frequency=None):
    self.difficulty = difficulty if difficulty in ("Easy", "Medium", "Hard") else "Easy"
    self.bluff_frequency = bluff_frequency if bluff_frequency is not None else {"Easy": 0.18, "Medium": 0.11, "Hard": 0.065}[self.difficulty]

  def _strength(self, player, state):
    cards = next(item["hole_cards"] for item in state["players"] if item["player_id"] == player.player_id)
    if len(cards) < 2:
      return 0.0
    board = state["board"]
    if not board:
      ranks = {value: index + 2 for index, value in enumerate(["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"])}
      high = max(ranks[card[0]] for card in cards)
      low = min(ranks[card[0]] for card in cards)
      pair = cards[0][0] == cards[1][0]
      suited = cards[0][1] == cards[1][1]
      connected = abs(high - low) <= 2
      if pair:
        return min(0.93, 0.52 + high / 35)
      return min(0.83, 0.12 + high / 39 + low / 75 + (0.07 if suited else 0) + (0.06 if connected else 0))
    category, comparison = highest_hand(cards + board)
    values = {
      "High Card": 0.16, "Pair": 0.39, "2 Pair": 0.59,
      "3 of a kind": 0.71, "Straight": 0.78, "Flush": 0.83,
      "Full House": 0.91, "4 of a kind": 0.97,
      "Straight Flush": 0.995, "Royal Flush": 1.0
    }
    return values[category]

  def _raise_amount(self, game, player, legal, strength):
    minimum = legal["min_raise_total"]
    maximum = legal["max_raise_total"]
    if minimum > maximum:
      return maximum - player.current_bet
    pot = game.pot
    if self.difficulty == "Easy":
      target = minimum + random.randint(0, max(0, game.big_blind))
    elif self.difficulty == "Medium":
      target = max(minimum, game.table_bet + max(game.big_blind, pot // 3))
    else:
      target = max(minimum, game.table_bet + max(game.big_blind, int(pot * (0.85 if strength >= 0.8 else 0.48))))
    return max(1, min(maximum, target) - player.current_bet)

  def choose(self, game, player):
    state = game.get_state(player.player_id)
    legal = game.legal_actions(player)
    strength = self._strength(player, state)
    call_amount = legal.get("call_amount", 0)
    pressure = call_amount / max(1, state["pot"] + call_amount)
    bluff = random.random() < self.bluff_frequency
    aggression = {"Easy": 0.22, "Medium": 0.28, "Hard": 0.38}[self.difficulty]
    tolerance = {"Easy": 0.16, "Medium": 0.09, "Hard": 0.04}[self.difficulty]

    if legal.get("check"):
      if legal.get("raise") and (strength > 0.72 or bluff) and random.random() < aggression:
        return "raise", self._raise_amount(game, player, legal, strength)
      return "check", None

    if legal.get("call") and (strength + tolerance >= pressure or bluff):
      if legal.get("raise") and strength > 0.83 and random.random() < aggression:
        return "raise", self._raise_amount(game, player, legal, strength)
      return "call", None

    if legal.get("raise") and strength > 0.86 and random.random() < aggression:
      return "raise", self._raise_amount(game, player, legal, strength)
    if legal.get("fold"):
      return "fold", None
    if legal.get("all_in"):
      return "all_in", None
    if legal.get("call"):
      return "call", None
    return "check", None

  def act(self, game, player):
    action, amount = self.choose(game, player)
    if action == "raise":
      return action, game.raise_bet(player, amount)
    return action, getattr(game, action)(player)
