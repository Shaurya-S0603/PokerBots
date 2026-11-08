def new_stats():
  return {"hands": 0, "wins": 0, "net": 0, "vpip": 0, "pfr": 0, "showdowns": 0, "showdown_wins": 0, "all_ins": 0, "largest_pot": 0}


def action_event(action, player_id, state_before, player_after):
  prior = next(item for item in state_before["players"] if item["player_id"] == player_id)
  contribution = player_after.total_bet - prior["total_bet"]
  raised = action == "raise" or (action == "all_in" and prior["current_bet"] + contribution > state_before["table_bet"])
  return {
    "hand": state_before["hand_number"],
    "phase": state_before["phase"],
    "player_id": player_id,
    "action": action,
    "amount": contribution,
    "raised": raised
  }


def settle_stats(stats, history, hand_start_stacks, state):
  actions = [event for event in history if event["hand"] == state["hand_number"]]
  for item in state["players"]:
    player_id = item["player_id"]
    if not item["in_hand"]:
      continue
    result = stats[player_id]
    personal = [event for event in actions if event["player_id"] == player_id]
    preflop = [event for event in personal if event["phase"] == "preflop"]
    result["hands"] += 1
    result["wins"] += int(player_id in state["winners"])
    result["net"] += item["stack"] - hand_start_stacks.get(player_id, item["stack"])
    result["vpip"] += int(any(event["action"] in ("call", "raise", "all_in") for event in preflop))
    result["pfr"] += int(any(event["raised"] and event["action"] in ("raise", "all_in") for event in preflop))
    result["showdowns"] += int(player_id in state["showdown_hands"])
    result["showdown_wins"] += int(player_id in state["showdown_hands"] and player_id in state["winners"])
    result["all_ins"] += int(any(event["action"] == "all_in" for event in personal))
    result["largest_pot"] = max(result["largest_pot"], int(state["payouts"].get(player_id, 0)))
  return stats
