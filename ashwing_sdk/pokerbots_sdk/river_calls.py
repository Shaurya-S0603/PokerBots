"""Public, per-opponent river response history for the sizing experiment."""

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RiverCallProfile:
  min_evidence: float = 4
  min_call_rate: float = .70
  smaller_bucket_discount: float = .70


def size_bucket(amount, pot):
  """Bucket an opening bet by its fraction of the pot before the bet."""
  if amount <= 0 or pot <= 0:
    raise ValueError("River bet and pot must be positive")
  if amount * 4 <= pot * 3:
    return 0
  return 1 if amount <= pot else 2


class RiverCallHistory:
  """Store the first response to our opening river bet in each completed hand."""

  def __init__(self, profile=RiverCallProfile()):
    self.profile = profile
    self.responses = deque(maxlen=24)

  def record(self, amount, pot, response):
    if response not in {"call", "fold", "raise", "all_in"}:
      raise ValueError(f"Unexpected river response: {response}")
    self.responses.append((size_bucket(amount, pot), response == "call"))

  def estimate(self, amount, pot):
    target = size_bucket(amount, pot)
    # Smaller bets provide weaker evidence for an overbet. The prior
    # contributes one call and two non-calls before any data is observed.
    weights = [(self.profile.smaller_bucket_discount ** max(0, target - bucket), called)
      for bucket, called in self.responses]
    evidence = sum(weight for weight, _ in weights)
    calls = sum(weight for weight, called in weights if called)
    return (1 + calls) / (3 + evidence), evidence

  def allows(self, amount, pot):
    rate, evidence = self.estimate(amount, pot)
    return evidence >= self.profile.min_evidence and rate >= self.profile.min_call_rate
