from pokerbots_sdk.river_calls import RiverCallHistory


def test_river_gate_requires_more_small_bet_evidence_for_an_overbet():
  history = RiverCallHistory()
  assert not history.allows(75, 100)
  for _ in range(4):
    history.record(75, 100, "call")
  assert history.allows(75, 100)
  assert not history.allows(150, 100)
  for _ in range(5):
    history.record(75, 100, "call")
  assert history.allows(150, 100)
  assert history.estimate(150, 100)[1] < history.estimate(75, 100)[1]


def test_river_gate_counts_raises_and_folds_and_forgets_old_calls():
  history = RiverCallHistory()
  for _ in range(24):
    history.record(150, 100, "call")
  assert history.allows(150, 100)
  for _ in range(12):
    history.record(150, 100, "raise")
    history.record(150, 100, "fold")
  rate, evidence = history.estimate(150, 100)
  assert rate == 1 / 27
  assert evidence == 24
  assert not history.allows(150, 100)
