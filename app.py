"""Stable entry point for the existing Streamlit deployment."""

from pathlib import Path
from runpy import run_path
import sys

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
  sys.path[:0] = [str(ROOT / "streamlit_app"), str(ROOT / "ashwing_sdk")]
  run_path(str(ROOT / "streamlit_app" / "app.py"), run_name="__main__")
