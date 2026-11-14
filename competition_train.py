"""CPU-parallel paired policy search for heads-up Hold'em."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
import json
from pathlib import Path

from arena import EquityProfile
from baseline_v4 import BASELINES
from train_generation import paired, paired_report, profile_strategy

ROOT = Path(__file__).resolve().parent
DEFAULT_INCUMBENT = ROOT / "training" / "champion.json"


def candidates(incumbent):
  return {
    "Incumbent": incumbent,
    "Value": replace(incumbent, value_edge=.19, pot_fraction=.72),
    "Pressure": replace(incumbent, value_edge=.13, position_bonus=.17, pot_fraction=.55),
    "River Defense": replace(incumbent, river_call_margin=-.05, call_cushion=.03),
    "Selective": replace(incumbent, call_cushion=.07, river_call_margin=.04),
  }


def matchup(job):
  name, profile, opponent, incumbent, start, pairs, stack = job
  other = profile_strategy(incumbent) if opponent == "Incumbent" else BASELINES[opponent]
  totals = paired(profile_strategy(profile), other, range(start, start + pairs), stack=stack)
  return name, opponent, paired_report(totals)


def train(output, *, pairs, held_out, workers, stack, seed, incumbent_path=DEFAULT_INCUMBENT, progress=print):
  incumbent = EquityProfile(**json.loads(incumbent_path.read_text())["profile"])
  variants = candidates(incumbent)
  opponents = ("Incumbent", "Tight", "Loose-Aggressive", "Calling Station")
  def jobs(profiles, start, count):
    return [(name, profile, opponent, incumbent, start, count, stack)
      for name, profile in profiles.items() for opponent in opponents]
  def collect(pool, tasks, stage):
    rows = {}
    for name, opponent, result in pool.map(matchup, tasks):
      rows.setdefault(name, {})[opponent] = result
      progress(f"{stage}: {name} vs {opponent}: {result['bb_per_100']:+.2f} bb/100", flush=True)
    return rows
  with ProcessPoolExecutor(max_workers=workers) as pool:
    screening = collect(pool, jobs(variants, seed, pairs), "Screen")
    def score(name):
      return sum(screening[name][opp]["bb_per_100"] for opp in opponents) / len(opponents)
    candidate = max(variants, key=score)
    holdout_start = seed + pairs
    evaluation = collect(pool, jobs({candidate: variants[candidate]}, holdout_start, held_out), "Holdout")
  edge = evaluation[candidate]["Incumbent"]["interval_95"][0]
  selected = candidate if candidate != "Incumbent" and edge > 0 else "Incumbent"
  report = {"profile": asdict(variants[selected]), "selected": selected, "candidate": candidate,
    "candidate_profile": asdict(variants[candidate]), "screening": screening, "evaluation": evaluation,
    "config": {"seed": seed, "screening_pairs": pairs, "holdout_seed": holdout_start,
      "held_out_pairs": held_out, "stack": stack, "small_blind": 5, "big_blind": 10}}
  output.parent.mkdir(parents=True, exist_ok=True)
  temp = output.with_suffix(".tmp")
  temp.write_text(json.dumps(report, indent=2) + "\n")
  temp.replace(output)
  return report


def main():
  args = argparse.ArgumentParser(description=__doc__)
  args.add_argument("--pairs", type=int, default=24)
  args.add_argument("--held-out", type=int, default=64)
  args.add_argument("--workers", type=int, default=2)
  args.add_argument("--stack", type=int, default=1000)
  args.add_argument("--seed", type=int, default=20000)
  args.add_argument("--incumbent", type=Path, default=DEFAULT_INCUMBENT)
  args.add_argument("--output", type=Path, default=Path("competition-policy.json"))
  config = args.parse_args()
  if min(config.pairs, config.held_out) < 2 or config.workers < 1 or config.stack < 10:
    args.error("Use at least two pairs, one worker, and a 10-chip stack")
  report = train(config.output, pairs=config.pairs, held_out=config.held_out,
    workers=config.workers, stack=config.stack, seed=config.seed, incumbent_path=config.incumbent)
  print(f"Selected {report['selected']} | saved {config.output}")


if __name__ == "__main__":
  main()
