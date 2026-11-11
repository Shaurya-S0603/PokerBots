import random
from html.parser import HTMLParser

from poker_bot import PokerBot
from poker_engine import start_game
from pokerroom import GameManager, Player
from ui.render import card_html, table_html
from ui.session import action_event, new_stats, settle_stats


class HTMLChecker(HTMLParser):
  def error(self, message):
    raise AssertionError(message)


def test_rendered_table_is_valid_and_escapes_names():
  game = start_game(5)
  markup = table_html(game.get_state(), {1: '<script>alert("x")</script>'})
  assert "<script>alert" not in markup
  assert "&lt;script&gt;" in markup
  assert markup.count('class="seat') >= 5
  assert 'aria-label="Community cards"' in markup
  assert markup.count('aria-label="Empty card slot"') == 5
  HTMLChecker().feed(markup)


def test_private_cards_only_in_private_state():
  game = start_game(4)
  public = table_html(game.get_state())
  secret = game.players[0].hole_cards
  assert len(secret) == 2
  assert all(not item['hole_cards'] for item in game.get_state()['players'])
  private = game.get_state(1)
  assert sum(bool(item['hole_cards']) for item in private['players']) == 1
  assert private['players'][0]['hole_cards'] == secret
  assert 'Face-down card' in public


def test_html_cards_have_readable_labels():
  assert 'Ace of spades' in card_html(('A', '♠️'))
  assert 'play-card--red' in card_html(('Q', '♥️'))
  assert 'Face-down card' in card_html(hidden=True)


def test_action_record_does_not_turn_payout_into_negative_bet():
  game = start_game(2)
  before = game.get_state()
  actor = game.players[game.current_player]
  assert game.call(actor)
  event = action_event('call', actor.player_id, before, actor)
  assert event['amount'] == before['table_bet'] - next(p['current_bet'] for p in before['players'] if p['player_id'] == actor.player_id)
  assert event['hand'] == 1


def test_statistics_are_once_per_hand_and_net_not_gross():
  state = {
    'hand_number': 1, 'hand_over': True,
    'players': [
      {'player_id': 1, 'in_hand': True, 'stack': 1100},
      {'player_id': 2, 'in_hand': True, 'stack': 900}
    ],
    'winners': [1], 'showdown_hands': {1: ('Pair',['A']), 2: ('High Card',['K'])},
    'payouts': {1: 200},
  }
  history = [
    {'hand': 1, 'phase': 'preflop', 'player_id': 1, 'action': 'call', 'amount': 10, 'raised': False},
    {'hand': 1, 'phase': 'flop', 'player_id': 1, 'action': 'call', 'amount': 20, 'raised': False},
    {'hand': 1, 'phase': 'turn', 'player_id': 1, 'action': 'raise', 'amount': 30, 'raised': True},
    {'hand': 1, 'phase': 'preflop', 'player_id': 2, 'action': 'raise', 'amount': 20, 'raised': True}
  ]
  stats = {1: new_stats(), 2: new_stats()}
  settle_stats(stats, history, {1: 1000, 2: 1000}, state)
  assert stats[1]['vpip'] == 1
  assert stats[1]['pfr'] == 0
  assert stats[1]['net'] == 100
  assert stats[2]['pfr'] == 1
  assert stats[2]['net'] == -100
  assert sum(v['net'] for v in stats.values()) == 0


def test_main_and_side_pots_correct_eligibility():
  players = [Player(1, 50), Player(2, 100), Player(3, 200)]
  game = GameManager(players)
  assert game.start_round()
  board = [('2','♣️'),('3','♦️'),('7','♠️'),('9','♣️'),('J','♥️')]
  hands = [[('A','♣️'),('A','♦️')],[('K','♣️'),('K','♦️')],[('Q','♣️'),('Q','♦️')]]
  for player, total, cards in zip(players, [50,100,200], hands):
    player.in_hand = True
    player.folded = False
    player.total_bet = total
    player.hole_cards = cards
    player.stack = 0
    player.all_in = True
  game.board = board
  game.phase = 'showdown'
  game.pot = 350
  game.hand_over = False
  assert game.showdown()
  assert [p['amount'] for p in game.pot_results] == [150,100]
  assert game.payouts == {1:150,2:100}
  assert game.get_state()['uncalled_returns'] == {3:100}
  assert players[2].stack == 100
  assert 3 not in game.winners
  assert game.pot == 0


def test_odd_chip_is_awarded_to_clockwise_eligible_winner():
  players = [Player(1, 10), Player(2, 10), Player(3, 10)]
  game = GameManager(players)
  assert game.start_round()
  for player in players:
    player.total_bet = 5
    player.stack = 5
    player.in_hand = True
    player.folded = False
  players[2].folded = True
  players[0].hole_cards = [('2','♣️'),('3','♣️')]
  players[1].hole_cards = [('4','♣️'),('5','♣️')]
  players[2].hole_cards = [('7','♣️'),('8','♣️')]
  game.board = [('A','♦️'),('K','♣️'),('Q','♥️'),('J','♦️'),('10','♠️')]
  game.phase = 'showdown'
  game.pot = 15
  game.hand_over = False
  assert game.showdown()
  assert game.payouts == {2:8,1:7}
  assert 3 not in game.payouts


def test_multiple_hands_preserve_all_chips_and_do_not_accept_restart_mid_hand():
  random.seed(3433)
  for count in (2,3,5,10):
    for starting in (12,20,100):
      game = start_game(count, starting, 5, 10)
      chips = count * starting
      assert game.start_next_round() is False
      for _ in range(40):
        limit = 0
        while not game.hand_over:
          limit += 1
          assert limit <= 200
          player = game.players[game.current_player]
          legal = game.legal_actions(player)
          options = [action for action in ('fold','check','call','raise','all_in') if legal.get(action)]
          action = random.choice(options)
          if action == 'raise':
            target = min(legal['min_raise_total'], legal['max_raise_total'])
            assert game.raise_bet(player, target - player.current_bet)
          else:
            assert getattr(game, action)(player)
          assert sum(p.stack for p in game.players) + game.pot == chips
        assert sum(p.stack for p in game.players) == chips
        if game.game_over:
          assert game.start_next_round() is False
          break
        previous_dealer = game.dealer_index
        expected = game.next_seated_index(previous_dealer, {p for p in game.players if p.stack > 0})
        assert game.start_next_round()
        assert game.dealer_index == expected


def test_bot_actions_stay_legal_with_short_all_ins():
  for difficulty in ('Easy','Medium','Hard'):
    for count in (2,4,8):
      for seed in range(25):
        random.seed(seed + count * 25)
        game = start_game(count, 13, 5, 10)
        bot = PokerBot(difficulty)
        for _ in range(500):
          if game.hand_over:
            break
          player = game.players[game.current_player]
          action, ok = bot.act(game, player)
          assert ok, (difficulty, count, action, game.last_error)
        assert game.hand_over


def test_lone_player_calls_only_the_chips_posted_by_short_blinds():
  players = [Player(1, 100), Player(2, 5), Player(3, 7)]
  game = GameManager(players)
  assert game.start_round()
  assert game.legal_actions(players[0])['call_amount'] == 7
  assert not game.legal_actions(players[0])['raise']
  assert game.call(players[0])
  assert game.hand_over
  assert players[0].total_bet == 7
  assert [pot['amount'] for pot in game.pot_results] == [15, 4]
  stacks = [p.stack for p in players]
  assert not game.showdown()
  assert not game.call(players[0])
  assert [p.stack for p in players] == stacks


def test_runout_skips_big_blind_when_no_one_can_bet_against_them():
  players = [Player(1, 100), Player(2, 5), Player(3, 100), Player(4, 100)]
  game = GameManager(players)
  assert game.start_round()
  assert game.fold(players[3])
  assert game.fold(players[0])
  assert game.hand_over
  assert len(game.board) == 5
  assert game.get_state()['current_player'] is None


def test_cumulative_short_all_ins_reopen_betting_only_at_full_raise_size():
  players = [Player(1, 100), Player(2, 100), Player(3, 29), Player(4, 100), Player(5, 25)]
  game = GameManager(players)
  assert game.start_round()
  assert game.raise_bet(players[3], 20)
  assert game.all_in(players[4])
  assert game.call(players[0])
  assert game.call(players[1])
  assert game.all_in(players[2])

  legal = game.legal_actions(players[3])
  assert legal['call_amount'] == 9
  assert not legal['raise']
  assert not game.raise_bet(players[3], 19)
  assert game.call(players[3])

  players = [Player(1, 100), Player(2, 100), Player(3, 30), Player(4, 100), Player(5, 25)]
  game = GameManager(players)
  assert game.start_round()
  assert game.raise_bet(players[3], 20)
  assert game.all_in(players[4])
  assert game.call(players[0])
  assert game.call(players[1])
  assert game.all_in(players[2])
  assert game.legal_actions(players[3])['min_raise_total'] == 40
  assert game.raise_bet(players[3], 20)
