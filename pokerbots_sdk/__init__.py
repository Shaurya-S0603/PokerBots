"""Write a strategy once and run it locally or through the Chipzen adapter."""

from .model import Observation, Strategy, validate_decision
from .strategies import TOOLKIT_STRATEGIES, button_pressure, value

__all__ = ["Observation", "Strategy", "TOOLKIT_STRATEGIES", "button_pressure",
  "validate_decision", "value"]


def load_strategy(spec: str) -> Strategy:
  """Resolve a built-in name or an importable module:callable."""
  from importlib import import_module

  if spec in TOOLKIT_STRATEGIES:
    return TOOLKIT_STRATEGIES[spec]
  module, separator, name = spec.partition(":")
  if not separator or not module or not name:
    raise ValueError(f"Unknown strategy {spec!r}. Use a built-in name or module:callable.")
  strategy = getattr(import_module(module), name, None)
  if not callable(strategy):
    raise ValueError(f"Strategy {spec!r} is not callable")
  return strategy


__all__.append("load_strategy")
