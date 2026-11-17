"""Single Streamlit decision policy using v2 and the v3 shallow checkpoint."""

from functools import lru_cache
import json
from pathlib import Path

from pokerbots_sdk.betting_line import preflop_strength
from pokerbots_sdk.hive_policy import adaptive_river_value_pressure, hive_mind

CHECKPOINT = Path(__file__).with_name("ashwing-v3-checkpoint.json")
ACTIONS = ("fold", "call", "all_in")
SHALLOW_LIMIT_BB = 5
MIN_BUCKET_SAMPLES = 12


@lru_cache(maxsize=1)
def _buckets():
  checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
  return {tuple(key): (count, weights) for key, count, weights in checkpoint["buckets"]}


def decide(view, rng, *, history=None):
  """Select one legal action from the public table observation."""
  call = view.legal["call_amount"]
  effective = min(view.stack + view.current_bet, view.effective_raise_total or view.table_bet)
  if (not view.board and len(view.stacks) == 2 and view.opponents == 1
      and 0 < effective <= SHALLOW_LIMIT_BB * view.big_blind and call):
    strength = min(7, int(max(0., preflop_strength(view.hole) - .26) / .077))
    price = min(3, int(8 * call / (view.pot + call)))
    jam = bool(view.legal["all_in"] and view.stack > call)
    key = (strength, True, bool(view.late_position), price, jam)
    count, weights = _buckets().get(key, (0, ()))
    if count >= MIN_BUCKET_SAMPLES:
      legal_weights = [weight if view.legal[action] and (action != "all_in" or jam) else 0.
                      for action, weight in zip(ACTIONS, weights, strict=True)]
      if any(legal_weights):
        return rng.choices(ACTIONS, weights=legal_weights)[0], None
  if history is not None and len(view.stacks) == 2 and len(view.board) == 5:
    return adaptive_river_value_pressure(view, rng, history)
  return hive_mind(view, rng)
