import json
from pathlib import Path
import sys

from chipzen.conformance import run_conformance_checks

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arena import EquityProfile
from chipzen_entry import CompetitionBot, DEFAULT_POLICY


def main():
  profile = EquityProfile(**json.loads(DEFAULT_POLICY.read_text())["profile"])
  results = run_conformance_checks(CompetitionBot(profile, seed=42), timeout_s=3)
  for result in results:
    print(f"{result.severity}: {result.name}: {result.message}")
  return 0 if results and all(result.severity == "pass" for result in results) else 1


if __name__ == "__main__":
  raise SystemExit(main())
