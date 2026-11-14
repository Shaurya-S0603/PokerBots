from pathlib import Path
import sys

from chipzen.conformance import run_conformance_checks

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chipzen_entry import CompetitionBot
from pokerbots_sdk import TOOLKIT_STRATEGIES


def main():
  ok = True
  for name, strategy in TOOLKIT_STRATEGIES.items():
    results = run_conformance_checks(CompetitionBot(strategy=strategy, seed=42), timeout_s=3)
    for result in results:
      print(f"{name}: {result.severity}: {result.name}: {result.message}")
    ok = ok and bool(results) and all(result.severity == "pass" for result in results)
  return 0 if ok else 1


if __name__ == "__main__":
  raise SystemExit(main())
