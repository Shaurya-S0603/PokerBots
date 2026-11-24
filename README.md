# Ashwing Poker

[Play Ashwing Poker](https://ashwingpoker.streamlit.app/) · [Ashwing_V4 on Chipzen](https://chipzen.ai/bots/62b649dc-516a-4883-89bc-269e68447a21)

Ashwing Poker is a no-limit Texas Hold’em game built with Python and Streamlit. Play against Ashwing at a table of 2–6 seats or use pass-and-play with 2–10 people on one device. Set the starting stacks and blinds in **Customize Room** before dealing.

The deployed policy is **Ashwing V4 (guarded)**. It keeps the tested v3 base and adds conservative range-conditioned flop/turn fold-or-call decisions facing large heads-up bets. It samples future boards, compares several opponent ranges and uses match-scoped public opponent history. Multiway and other ordinary decisions retain the v3 base.

The final local holdout covered 3,168 matches across 648 seed blocks. V4 won 101/192 directly against v3; improvement over released v2 and six-player fields remains uncertain. The deployed policy is the reviewed guarded candidate, not the broader experimental variants.

## Run locally

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Table controls and history

- Raise amounts are shown as the total bet for the current street.
- **Ashwing chat** keeps the full transcript. The table bubble holds its current line for at least three seconds while play continues.
- **History** replays completed hands from the current game and exports them as JSON. The export uses seat numbers and includes cards revealed at showdown.
- **Leave game** returns to the lobby. Use **Resume current game** in the same session or export your history before reloading.

## Project layout

| Path | Contents |
|---|---|
| `app.py` | Streamlit entry point used by the live deployment |
| `streamlit_app/` | Lobby, table, hand history, and UI tests |
| `ashwing_sdk/` | Poker engine, Ashwing strategy, Chipzen adapter, and validation |

## Test and package

```bash
python -m pytest -q
python ashwing_sdk/tests/chipzen_conformance.py Ashwing_V4
```

Install both `requirements.txt` and `ashwing_sdk/requirements-chipzen.txt` before running all tests. The **Chipzen upload** workflow packages `Ashwing_V4` for Linux AMD64. Download the `pokerbots-ashwing-v4-chipzen` artifact, extract the inner `.tar.gz`, and upload it to Chipzen.

To build the same image locally:

```bash
docker build --platform linux/amd64 -f ashwing_sdk/Dockerfile.chipzen -t pokerbots-ashwing-v4:chipzen ashwing_sdk
docker save pokerbots-ashwing-v4:chipzen | gzip > pokerbots-ashwing-v4-chipzen.tar.gz
```

Streamlit Community Cloud deploys `main/app.py` from this repository. See the [release notes](AUDIT_AND_CHANGELOG.md) and [roadmap](ROADMAP.md).
