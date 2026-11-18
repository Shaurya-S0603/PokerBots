# Ashwing Poker

[Play Ashwing Poker](https://ashwingpoker.streamlit.app/) · [Ashwing_v2 on Chipzen](https://chipzen.ai/bots/49375fc1-7b6d-4b7e-966f-44600ed28fb5)

Ashwing Poker is a no-limit Texas Hold’em game built with Python and Streamlit. Play against Ashwing at a table of 2–6 seats or use pass-and-play with 2–10 people on one device. Set the starting stacks and blinds in **Customize Room** before dealing.

Ashwing combines Search for general play with a short-stack equity policy. In eligible heads-up preflop spots at 10 big blinds or less, it samples opponent holdings and board runouts to compare the value of folding, calling, and going all-in.

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
python -m pip install -r ashwing_sdk/requirements-chipzen.txt
python ashwing_sdk/tests/chipzen_conformance.py Ashwing
```

The **Chipzen upload** workflow packages the current `Ashwing` policy for Linux AMD64. Download the `pokerbots-ashwing-chipzen` artifact, extract the inner `.tar.gz`, and upload it to Chipzen.

To build the same image locally:

```bash
docker build --platform linux/amd64 -f ashwing_sdk/Dockerfile.chipzen -t pokerbots-ashwing:chipzen ashwing_sdk
docker save pokerbots-ashwing:chipzen | gzip > pokerbots-ashwing-chipzen.tar.gz
```

Streamlit Community Cloud deploys `main/app.py` from this repository. See the [release notes](AUDIT_AND_CHANGELOG.md) and [roadmap](ROADMAP.md).
