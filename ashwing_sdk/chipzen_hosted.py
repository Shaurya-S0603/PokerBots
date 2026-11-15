"""Entrypoint for the selected hosted Chipzen strategy."""

import asyncio
import logging
import os

from chipzen import run_bot

from chipzen_entry import CompetitionBot
from pokerbots_sdk import load_strategy


def main():
  url = os.environ.get("CHIPZEN_WS_URL") or os.environ.get("CHIPZEN_URL")
  if not url:
    raise SystemExit("Chipzen must provide CHIPZEN_WS_URL")
  logging.basicConfig(level=logging.INFO)
  strategy = load_strategy(os.environ.get("POKERBOTS_STRATEGY", "Value"))
  asyncio.run(run_bot(url, CompetitionBot(strategy=strategy), token=os.environ.get("CHIPZEN_TOKEN"),
    ticket=os.environ.get("CHIPZEN_TICKET")))


if __name__ == "__main__":
  main()
