import json

from arena import EquityProfile
from train_equity import CHAMPION_PATH, train
from train_generation import paired_report, play, profile_strategy


def test_previous_generation_is_preserved():
  previous = json.loads(CHAMPION_PATH.with_name("generation-1.json").read_text())
  result = train(previous["source"], previous["training"]["seed"])
  assert result["training"] == previous["training"]
  assert EquityProfile(**result["profile"]) == EquityProfile(**previous["profile"])


def test_saved_champion_reproduces_the_final_and_evaluation_uses_separate_seeds():
  record = json.loads(CHAMPION_PATH.read_text())
  final = record["training"]
  strategies = {row["model"]: profile_strategy(EquityProfile(**record["candidate_profiles"][row["model"]]))
    for row in final["results"]}
  assert play(strategies, final["seed"], full_game=True)[0] == final
  winner, = [row for row in final["results"] if row["final_chips"]]
  assert winner["model"] == record["champion"]
  assert record["profile"] == record["candidate_profiles"][record["champion"]]
  assert len(record["screening"]["self_play"]) == 5
  assert record["evaluation"]["seed_start"] > final["seed"]


def test_paired_evaluation_counts_two_hands_per_seed():
  result = paired_report([20, 20])
  assert result == {"pairs": 2, "bb_per_100": 100.0, "interval_95": [100.0, 100.0]}
