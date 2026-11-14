"""The public decision boundary shared by local and remote players."""

from dataclasses import dataclass
from random import Random
from typing import Protocol


@dataclass(frozen=True)
class Observation:
  hole: tuple
  board: tuple
  stack: int
  stacks: tuple
  current_bet: int
  table_bet: int
  big_blind: int
  pot: int
  late_position: bool
  opponents: int
  legal: dict
  effective_raise_total: int
  has_all_in_opponent: bool


class Strategy(Protocol):
  """Return an action and an optional raise-to total in chips."""

  def __call__(self, state: Observation, rng: Random, /) -> tuple[str, int | None]:
    ...


def validate_decision(state, action, target):
  if not state.legal.get(action) or action not in ("check", "call", "fold", "raise", "all_in"):
    raise ValueError(f"Bot selected an illegal action: {action}")
  if action == "raise":
    maximum = state.legal["max_raise_total"]
    minimum = min(state.legal["min_raise_total"], maximum)
    if type(target) is not int or not minimum <= target <= maximum:
      raise ValueError("Bot selected an illegal raise target")
  elif target is not None:
    raise ValueError("Only a raise accepts a target")
