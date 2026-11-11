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
    finally:
      server.terminate()
