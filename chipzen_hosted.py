"""Entrypoint for the hosted Chipzen Value bot."""

import asyncio
import logging
import os

from chipzen import run_bot

from chipzen_entry import CompetitionBot


def main():
  url = os.environ.get("CHIPZEN_WS_URL") or os.environ.get("CHIPZEN_URL")
  if not url:
    raise SystemExit("Chipzen must provide CHIPZEN_WS_URL")
  logging.basicConfig(level=logging.INFO)
  asyncio.run(run_bot(url, CompetitionBot(), token=os.environ.get("CHIPZEN_TOKEN"),
    ticket=os.environ.get("CHIPZEN_TICKET")))


if __name__ == "__main__":
  main()
