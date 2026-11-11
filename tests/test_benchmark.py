from benchmark import Config, benchmark, play_pair, summarize


def test_mirrored_calling_station_pair_has_the_same_deal_and_reproducible_results():
  pair, timings = play_pair(1, "Calling Station", Config())
  first, second = pair["hands"]
  assert [first["equity_seat"], second["equity_seat"]] == [1, 2]
  assert first["deal_hash"] == second["deal_hash"]
  assert pair == play_pair(1, "Calling Station", Config())[0]
  assert timings


def test_summary_uses_hands_for_bb100_and_whole_pairs_for_interval():
  def hand(net):
    return {"net_chips": net, "illegal_actions": 0, "vpip": True, "pfr": False}
  pairs = [{"hands": [hand(-5), hand(25)]}, {"hands": [hand(-8), hand(28)]}]
  result = summarize(pairs, [1, 2, 3], 10, 200, 1)
  assert result["bb_per_100"] == 100
  assert result["interval_95"] == [100, 100]
  assert result["hands"] == 4
  assert result["vpip"] == 1
  assert result["pfr"] == 0


def test_evaluation_and_tuning_use_disjoint_seed_pairs():
  def pair_ids(split):
    report = benchmark(["Calling Station"], Config(), start=5, pairs=2,
      split=split, bootstrap=20, version="test", include_pairs=True)
    return [pair["pair_id"] for pair in report["results"][0]["pair_results"]]
  assert pair_ids("tuning") == [10, 12]
  assert pair_ids("evaluation") == [11, 13]
