"""Hold'em policy with a precomputed heads-up response to limps."""

from bisect import bisect_right
from functools import lru_cache
import json
from pathlib import Path

from .adaptive_policy import ashwing_adaptive
from .betting_line import preflop_strength


TITLE = "Ashwing Search"
BLIND_PATH = Path(__file__).resolve().parents[1] / "training" / "ashwing-blind-blueprint.json"
DEPTHS = (25, 100)

def depth_bucket(view, cuts):
  depth = min(view.stack + view.current_bet, view.effective_raise_total) / view.big_blind
  if depth < 15 or depth > 125:
    return None
  return min(DEPTHS, key=lambda anchor: abs(depth - anchor)), bisect_right(cuts, preflop_strength(view.hole))


def limp_bucket(view):
  if (view.board or view.opponents != 1 or len(view.stacks) != 2 or view.late_position
      or view.table_bet != view.big_blind or not view.legal["check"] or len(view.betting_line) != 1):
    return None
  limp = view.betting_line[0]
  if not limp.opponent or limp.street != "preflop" or limp.action != "call":
    return None
  return depth_bucket(view, (.54, .66))

@lru_cache(maxsize=1)
def blind_blueprint():
  return json.loads(BLIND_PATH.read_text())["blind_raise_bb"]


def ashwing_search(view, rng, *, history=None, diagnostics=None):
  bucket = limp_bucket(view)
  if bucket is not None:
    depth, strength = bucket
    target = blind_blueprint()[str(depth)][strength] * view.big_blind
    maximum = min(view.effective_raise_total, view.legal["max_raise_total"])
    if view.legal["raise"] and view.legal["min_raise_total"] <= target <= maximum:
      if diagnostics is not None:
        diagnostics.update(method=TITLE, depth_bb=depth, strength_bucket=strength)
      return "raise", target
  return ashwing_adaptive(view, rng, history=history, diagnostics=diagnostics)
