import json

from train_equity import CHAMPION_PATH, train


def test_saved_champion_reproduces_the_completed_tournament():
  record = json.loads(CHAMPION_PATH.read_text())
  assert train(record["source"], record["training"]["seed"]) == record
  final = [row for row in record["training"]["results"] if row["final_chips"]]
  assert len(final) == 1
  assert final[0]["model"] == record["champion"]
