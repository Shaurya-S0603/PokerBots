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
ROOT = Path(__file__).resolve().parents[3]


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
  height = 740 if width < 500 else 900
  page = browser.new_page(viewport={"width": width, "height": height}, has_touch=width < 500)
  errors = []
  page.on("pageerror", lambda error: errors.append(str(error)))
  page.goto(URL)
  expect(page.get_by_role("button", name="Play Ashwing")).to_be_visible()
  expect(page.get_by_role("slider")).to_have_count(0)
  page.get_by_role("button", name="Pass-and-play").click()
  expect(page.get_by_role("heading", name="Customize Room")).to_be_visible()
  expect(page.get_by_role("spinbutton", name="Starting stack")).to_have_value("1000")
  expect(page.get_by_role("region", name="No-Limit Texas Hold'em poker table")).to_have_count(0)
  page.get_by_role("button", name="Deal the first hand").click()
  expect(page.get_by_text("Dealing you in…", exact=True)).to_be_visible()
  page.get_by_role("button", name="Reveal my cards").click()
  expect(page.get_by_role("group", name="Your private hole cards")).to_be_visible()
  expect(page.get_by_role("timer")).to_be_visible()
  pot_button = page.get_by_role("button", name="Pot 30", exact=True).bounding_box()
  assert pot_button["y"] + pot_button["height"] <= height, pot_button
  clock_bar = page.locator(".room-clock > div").bounding_box()
  assert pot_button["y"] - (clock_bar["y"] + clock_bar["height"]) >= 8
  if width >= 800:
    fold_button = page.get_by_role("button", name="Fold", exact=True).bounding_box()
    assert abs(fold_button["y"] - pot_button["y"]) < 5

  stage = page.locator(".table-stage").bounding_box()
  board = page.get_by_role("group", name="Community cards").bounding_box()
  assert board["x"] >= stage["x"] and board["x"] + board["width"] <= stage["x"] + stage["width"]
  assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
  page.get_by_role("button", name="Pot 30", exact=True).click()
  expect(page.get_by_role("group", name="Your private hole cards")).to_have_count(0)
  page.get_by_role("button", name="Reveal my cards").click()
  page.get_by_role("button", name="Fold", exact=True).click()
  expect(page.get_by_role("button", name="Next hand", exact=True)).to_have_count(0)
  expect(page.get_by_role("heading", name="Preflop Hand 2")).to_be_visible(timeout=5000)
  page.get_by_role("button", name="History", exact=True).click()
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
  expect(page.get_by_role("button", name="Next hand", exact=True)).to_have_count(0)
  expect(page.get_by_role("button", name="Reveal my cards")).to_be_visible()
  assert not errors, errors
  page.close()


def check_paced_bot(browser, width, count):
  page = browser.new_page(viewport={"width": width, "height": 900})
  page.goto(URL)
  page.get_by_role("button", name="Play Ashwing", exact=True).click()
  expect(page.get_by_role("heading", name="Customize Room")).to_be_visible()
  expect(page.get_by_role("textbox", name="Your name")).to_be_visible()
  set_player_count(page, count)
  page.get_by_role("button", name="Deal the first hand").click()
  expect(page.get_by_text("Dealing you in…", exact=True)).to_be_visible()
  expect(page.get_by_role("button", name="History", exact=True)).to_be_visible()
  expect(page.get_by_role("button", name="Bot logs", exact=True)).to_have_count(0)
  label = "Ashwing" if count == 2 else "Ashwing 1"
  expect(page.get_by_role("article", name=label, exact=False).first).to_be_visible()
  avatar = page.locator(".seat .ashwing-avatar").first
  expect(avatar).to_be_visible()
  assert avatar.evaluate("(img) => img.complete && img.naturalWidth === 192")
  speech = page.get_by_role("status", name="Ashwing speaks")
  expect(speech).to_contain_text("I have a title to defend.")
  if width < 500:
    pot_button = page.get_by_role("button", name="Pot 30", exact=True).bounding_box()
    assert pot_button["y"] + pot_button["height"] <= 740
  elif count == 2:
    expect(page.locator(".seat__identity .room-speech__bubble")).to_be_visible()
    assert speech.bounding_box()["x"] > avatar.bounding_box()["x"]
  expect(page.get_by_role("timer")).to_be_visible()
  assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
  if count == 2:
    page.get_by_role("button", name="Call 5", exact=True).click()
  else:
    page.get_by_role("button", name="Fold", exact=True).click()
  page.get_by_text("Hand action log", exact=True).click()
  expect(page.locator(".room-events").get_by_text(label, exact=False).first).to_be_visible(timeout=15000)
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
        check_paced_bot(browser, 1440, 2)
        check_paced_bot(browser, 1440, 3)
        check_paced_bot(browser, 360, 2)
    finally:
      server.terminate()
