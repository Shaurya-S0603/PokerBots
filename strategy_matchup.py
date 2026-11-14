"""Compare two SDK strategies on identical heads-up deals with swapped seats."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json

from pokerbots_sdk import load_strategy
from train_generation import paired, paired_report


def _play_batch(job):
  candidate, control, first_seed, pairs, stack = job
  return paired(load_strategy(candidate), load_strategy(control),
    range(first_seed, first_seed + pairs), stack=stack)


def compare_strategies(candidate, control, *, seed, pairs, stack, workers):
  if pairs < 2 or stack < 10 or workers < 1:
    raise ValueError("Use at least two seed pairs, a 10-chip stack and one worker")
  batches = [(candidate, control, seed + offset, min(16, pairs - offset), stack)
    for offset in range(0, pairs, 16)]
  if workers == 1:
    totals = [total for batch in batches for total in _play_batch(batch)]
  else:
    with ProcessPoolExecutor(max_workers=workers) as pool:
      totals = [total for batch in pool.map(_play_batch, batches) for total in batch]
  return {"candidate": candidate, "control": control, "seed": seed, "stack": stack,
    "small_blind": 5, "big_blind": 10, "hands": 2 * pairs, **paired_report(totals)}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--candidate", default="Button Pressure")
  parser.add_argument("--control", default="Value")
  parser.add_argument("--seed", type=int, default=27000)
  parser.add_argument("--pairs", type=int, default=128)
  parser.add_argument("--stack", type=int, default=1000)
  parser.add_argument("--workers", type=int, default=2)
  args = parser.parse_args()
  try:
    report = compare_strategies(**vars(args))
  except ValueError as error:
    parser.error(str(error))
  print(json.dumps(report, indent=2))


if __name__ == "__main__":
  main()
