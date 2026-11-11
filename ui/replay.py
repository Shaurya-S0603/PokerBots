from copy import deepcopy
import json

TABLE_FIELDS = (
  "hand_number", "phase", "dealer", "small_blind_player", "big_blind_player",
  "current_player", "small_blind", "big_blind", "pot", "board", "hand_over",
  "game_over", "winners", "payouts", "uncalled_returns", "pot_results", "showdown_hands",
)
SEAT_FIELDS = ("player_id", "stack", "current_bet", "total_bet", "folded", "all_in", "in_hand")


def _snapshot(state):
  table = {key: state[key] for key in TABLE_FIELDS}
  revealed = state["showdown_hands"] if state["hand_over"] else {}
  table["players"] = [
    {**{key: player[key] for key in SEAT_FIELDS},
      "hole_cards": player["hole_cards"] if player["player_id"] in revealed else []}
    for player in state["players"]
  ]
  table["showdown_hands"] = revealed
  return deepcopy(table)


def start_record(state, starting_stacks):
  record = {"hand_number": state["hand_number"], "starting_stacks": starting_stacks.copy(), "steps": []}
  record_step(record, state)
  return record


def record_step(record, state, action=None):
  steps = record["steps"]
  prior_board = steps[-1]["table"]["board"] if steps else []
  board_changes = [
    {"street": street, "cards": state["board"][start:end]}
    for street, start, end in (("Flop", 0, 3), ("Turn", 3, 4), ("River", 4, 5))
    if len(prior_board) < end <= len(state["board"])
  ]
  steps.append({"action": action.copy() if action else None,
    "board_changes": board_changes, "table": _snapshot(state)})


def export_history(records):
  completed = [record for record in records.values() if record["steps"][-1]["table"]["hand_over"]]
  return json.dumps({"schema_version": 1, "hands": completed}, ensure_ascii=False, indent=2)
