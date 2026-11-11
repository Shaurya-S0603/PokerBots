import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

URL = "http://127.0.0.1:8511"
ROOT = Path(__file__).resolve().parents[2]


def wait_for_server():
  deadline = time.monotonic() + 25
  while time.monotonic() < deadline:
    try:
      with urlopen(f"{URL}/_stcore/health", timeout=1) as response:
        if response.status == 200:
          return
    except (URLError, TimeoutError):
      time.sleep(0.25)
  raise RuntimeError("Streamlit failed to start")


def set_player_count(page, count):
  slider = page.get_by_role("slider")
  slider.press("Home")
  for _ in range(count - 2):
    slider.press("ArrowRight")


def check_table(browser, width):
  page = browser.new_page(viewport={"width": width, "height": 900}, has_touch=width < 500)
  errors = []
  page.on("pageerror", lambda error: errors.append(str(error)))
  page.goto(URL)
  expect(page.get_by_role("button", name="Deal the first hand")).to_be_visible()
  set_player_count(page, 2)
  page.get_by_role("button", name="Deal the first hand").click()
  page.get_by_role("button", name="Reveal my cards").click()
  expect(page.get_by_role("group", name="Your private hole cards")).to_be_visible()

  stage = page.locator(".table-stage").bounding_box()
  board = page.get_by_role("group", name="Community cards").bounding_box()
  assert board["x"] >= stage["x"] and board["x"] + board["width"] <= stage["x"] + stage["width"]
  assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
  page.get_by_role("button", name="Pot 30", exact=True).click()
  expect(page.get_by_role("group", name="Your private hole cards")).to_have_count(0)
  page.get_by_role("button", name="Reveal my cards").click()
  page.get_by_role("button", name="Fold", exact=True).click()
  expect(page.get_by_text("Uncalled bet returned to Player 1", exact=False)).to_be_visible()
  expect(page.get_by_role("button", name="Next hand")).to_be_visible()
  page.get_by_role("button", name="Replay this hand").click()
  expect(page.get_by_text("Blinds posted", exact=True)).to_be_visible()
  page.get_by_role("button", name="Next step").click()
  expect(page.get_by_text("Preflop · Player 1: raise · 25 chips", exact=True)).to_be_visible()
  page.get_by_role("button", name="Next step").click()
  expect(page.get_by_text("Preflop · Player 2: fold", exact=True)).to_be_visible()
  with page.expect_download() as download:
    page.get_by_role("button", name="Download completed hands (JSON)").click()
  history = json.loads(download.value.path().read_text(encoding="utf-8"))
  hand = history["hands"][0]
  assert hand["starting_stacks"] == {"1": 1000, "2": 1000}
  assert [seat["stack"] for seat in hand["steps"][-1]["table"]["players"]] == [1010, 990]
  assert all(not seat["hole_cards"] for step in hand["steps"] for seat in step["table"]["players"])
  page.get_by_role("button", name="Back to table").click()
  expect(page.get_by_role("button", name="Next hand")).to_be_visible()
  assert not errors, errors
  page.close()


def check_paced_bot(browser):
  page = browser.new_page(viewport={"width": 1440, "height": 900})
  page.goto(URL)
  expect(page.get_by_role("button", name="Deal the first hand")).to_be_visible()
  set_player_count(page, 3)
  page.get_by_test_id("stSelectbox").first.locator("input").click()
  page.get_by_text("Human vs Bots", exact=True).click()
  page.get_by_role("button", name="Deal the first hand").click()
  page.get_by_role("button", name="Fold", exact=True).click()
  expect(page.get_by_text("Player 2 is thinking…", exact=True)).to_be_visible()
  expect(page.get_by_role("button", name="Next hand")).to_be_visible(timeout=15000)
  page.close()


def check_arena(browser):
  page = browser.new_page(viewport={"width": 1440, "height": 900})
  page.goto(URL)
  expect(page.get_by_role("button", name="Deal the first hand")).to_be_visible()
  set_player_count(page, 2)
  page.get_by_test_id("stSelectbox").first.locator("input").click()
  page.get_by_text("Bot Arena", exact=True).click()
  page.get_by_role("button", name="Deal the first hand").click()
  expect(page.get_by_text("Bot Arena · Seed 42", exact=True)).to_be_visible()
  page.get_by_role("button", name="Play", exact=True).click()
  action = page.get_by_text("Last action: Seat 1 call · 5 chips", exact=True)
  expect(action).to_be_visible()
  page.get_by_role("button", name="Pause", exact=True).click()
  step = page.get_by_role("button", name="Step", exact=True).and_(page.locator("button:enabled"))
  expect(step).to_be_visible()
  expect(action).to_be_visible()
  step.click()
  expect(page.get_by_text("Last action: Seat 2 check", exact=True)).to_be_visible()
  page.close()


def check_benchmarks(browser):
  page = browser.new_page(viewport={"width": 1440, "height": 900})
  page.goto(URL)
  page.get_by_role("button", name="Bot benchmarks", exact=True).click()
  expect(page.get_by_role("heading", name="Bot benchmarks", exact=True)).to_be_visible()
  expect(page.get_by_test_id("stDataFrame")).to_be_visible()
  with page.expect_download() as download:
    page.get_by_role("button", name="Download benchmark report").click()
  report = json.loads(download.value.path().read_text(encoding="utf-8"))
  assert len(report["results"]) == 4 and report["config"]["split"] == "evaluation"
  page.get_by_role("button", name="Back to menu").click()
  expect(page.get_by_role("button", name="Deal the first hand")).to_be_visible()
  page.close()


if __name__ == "__main__":
  command = [sys.executable, "-m", "streamlit", "run", "app.py",
    "--server.port=8511", "--server.headless=true", "--browser.gatherUsageStats=false"]
  with subprocess.Popen(command, cwd=ROOT) as server:
    try:
      wait_for_server()
      with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("POKERBOTS_CHROMIUM"))
        check_table(browser, 1440)
        check_table(browser, 360)
        check_paced_bot(browser)
        check_arena(browser)
        check_benchmarks(browser)
    finally:
      server.terminate()
