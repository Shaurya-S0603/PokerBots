"""Entrants and the selected Arena policy."""

from functools import lru_cache, partial
import json
from pathlib import Path

from baseline_v4 import BASELINES

from .equity_policy import EquityProfile, equity_bot
from .strategies import TOOLKIT_STRATEGIES

TRAINING = Path(__file__).resolve().parents[1] / "training"
TITLE = "One Above All"
SELECTION = TRAINING / "one-above-all.json"


@lru_cache(maxsize=1)
def roster():
  entrants = {**BASELINES, "Equity": partial(equity_bot, arena_opening=True),
    **{name: policy for name, policy in TOOLKIT_STRATEGIES.items() if name != TITLE}}
  seen = set()
  for filename in ("champion.json", "generation-2.json", "generation-1.json"):
    archive = json.loads((TRAINING / filename).read_text())
    profiles = {**archive.get("candidate_profiles", {}), archive["champion"]: archive["profile"]}
    for name, config in profiles.items():
      profile = EquityProfile(**config)
      if profile in seen:
        continue
      seen.add(profile)
      label = name if name not in entrants else f"{name} (generation {archive['generation']})"
      entrants[label] = partial(equity_bot, profile=profile)
  return entrants


@lru_cache(maxsize=1)
def selection():
  return json.loads(SELECTION.read_text())


def one_above_all(view, rng, *, diagnostics=None):
  """Use the finalists selected for heads-up and multiway play."""
  mode = "heads_up" if len(view.stacks) == 2 else "multiway"
  entrant = selection()[mode]["selected"]
  strategy = roster()[entrant]
  if strategy in BASELINES.values():
    action = strategy(view, rng)
    if diagnostics is not None:
      diagnostics.update(method="Rule-based", decision_basis=entrant)
    return action
  action = strategy(view, rng, diagnostics=diagnostics)
  if diagnostics is not None:
    diagnostics["champion_entrant"] = entrant
  return action
