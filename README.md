# PokerBots

A local No-Limit Texas Hold'em browser game built in Streamlit with the original Python poker engine. The UI uses separate HTML, CSS, and JavaScript assets for the table and visual effects. Game rules and pot distribution remain on the Python side.

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit. Use **Local Pass-and-Play** for 2–10 human players sharing a device, or **Human vs Bots** to play as seat 1 against the latest Equity training match winner.

## Bot Arena

Select **Bot Arena** as the game mode. Pick a match seed and a strategy for each seat. **Step** plays one decision or deals the next hand after a payout. **Play** repeats those steps at the selected pace, and **Pause** returns control to you. Reuse the seed, strategies, stacks, and blinds to reproduce a match in the same app version. The hand history download includes the Arena seed and strategies.

The Arena includes Calling Station, Random, Tight, Loose-Aggressive, and Equity. All strategies use each bot's own cards and public table information.

**Equity** in Bot Arena uses position-based opening ranges when facing only the big blind. It uses equity for responses to raises and postflop decisions. The Arena opening rule is separate from the frozen benchmark and Human vs Bots training policies. **Equity** enumerates every opponent hand on a heads-up river. In other spots it samples uniformly from unseen cards using 256 trials against up to three opponents and 128 at larger tables. It uses equity for call and raise decisions, caps raise targets at effective stacks, and falls back to Tight when a partial call or multiway all-in makes simple pot odds unreliable.

## Training winner and bot visualization

Human vs Bots uses the winner saved in `training/champion.json`. To reproduce generation 3, run `python train_generation.py new-human-history.json` with the completed Human vs Bots export. The human defaults to seat 1. The trainer starts from the archived generation 2 champion, combines public human action counts from both games, and uses the newest game’s starting stack. To reproduce generation 2, use `--generation 2 arena-history.json human-history.json`. It rotates candidates through starting seats, runs paired screening matches, and promotes the winner of the final elimination match. Separate seed pairs check the winner against the previous champion and the practice opponent. The saved report contains aggregates and parameters rather than raw hand histories. Deploy the updated champion record to use the new winner.

Open **Bot visualization** from the menu or game sidebar. **Simulation** shows actual bot decision estimates for completed hands, including outcome counts and cumulative Monte Carlo win rate and pot share. Heads-up river decisions are enumerated exactly. **Training match** shows the latest tournament and its winner.

## Offline benchmarks

Run a single mirrored deal or compare all four frozen Update 4 baselines:

```bash
python benchmark.py --opponent "Calling Station" --pairs 1
python benchmark.py --split evaluation --pairs 100 --output evaluation.json
```

**Bot benchmarks** in the main menu shows a bundled evaluation and accepts reports from the runner. Each seed plays two hands with equal starting stacks and the bots swapped. A hash checks that the deal by seat is identical. Tuning uses even seeds and evaluation uses odd seeds. Use `--include-pairs` to keep each hand's outcome and deal hash in the export. Results show Equity's net big blinds per 100 hands, a 95% bootstrap interval sampled by seed pair, illegal actions, VPIP, PFR, and Equity's decision latency. If a strategy makes an illegal move, the runner reports it and exits with a nonzero status.

## Project structure

- `app.py` - Streamlit application, session and action controls
- `pokerroom.py` - original Texas Hold'em game rules, hand evaluation and pot logic
- `poker_engine.py` - stable import of engine API
- `poker_bot.py` - basic skill-level heuristics
- `ui/table.html` - HTML table template
- `ui/styles.css` - visual design and responsive rules
- `ui/effects.js` and `ui/effect.html` - nonessential action/winner celebration effect
- `ui/render.py` - data-to-HTML renderer with escaped player labels
- `tests/` - regression checks

## Hand history

Choose **Replay this hand** after a payout, or **Hand history** in the sidebar, to step through completed hands from the current game. The replay shows starting stacks, positions, actions, board changes, payouts, and final stacks.

**Download completed hands (JSON)** exports the current game's completed hands with seat numbers. It includes cards revealed at showdown and omits names, folded or otherwise unrevealed hole cards, and the deck. Download before starting another game or leaving the session to keep the history.

## Behavior and privacy

The game state lives in Streamlit session state. Press **Main menu** and **Resume current game** to navigate within the same session. A browser reload or a disconnected session is not guaranteed to preserve the game. There is no database, external lobby or account system.

Pass-and-play hides the previous player's cards until the next player taps **Reveal my cards**. This is meant for a trusted shared device, not secure network multiplayer. Bot opponents only receive their own private cards and publicly revealed community cards.

Raise controls show a **target total bet for the current street**. The UI converts that to the additional chips expected by `game.raise_bet(player, amount)`.

The game reports side-pot payouts after settlement. It does not attempt to recalculate side-pot eligibility in the browser.

## Testing

```bash
python -m pytest -q
```

The test suite covers hand starts, private cards, legal actions, rotating seats, short all-ins, chip conservation, winner payouts and view HTML escaping. To test browser rendering interactively, install Streamlit locally and run the app in a desktop and mobile browser.

## Scope

The bot difficulty settings are heuristics and have not been trained or optimized. Blind escalation, ante rules, tournament clocks, save-to-disk, network multiplayer and accounts are out of scope.

## Repository and deployment

This repository is the canonical project. Use feature branches and pull requests for updates rather than exchanging ZIP archives. GitHub Actions runs the existing test suite on pushes to main and pull requests.

Streamlit Community Cloud deployment settings:

- Repository: `Shaurya-S0603/PokerBots`
- Branch: `main`
- Entry point: `app.py`
- Python: `3.12`
- Dependencies: root `requirements.txt`

Merge tested changes into main to update the connected app. Configure any future secrets in Streamlit settings; `.streamlit/secrets.toml` is ignored. Repository privacy and deployed-app access are separate settings.

See [ROADMAP.md](ROADMAP.md) for the ordered browser-testing, persistence, AI and multiplayer milestones and their acceptance criteria.

## Chipzen competition

Open `PokerBots_Chipzen_Colab.ipynb` in Colab using a CPU runtime. Run setup and the offline conformance check, then use the bundled Value policy or train on fresh seeds. The final cell is opt-in and uses the Chipzen remote track with a bot ID and token stored in Colab Secrets. Test a friendly match before entering ranked play.

The competition trainer runs mirrored heads-up hands in parallel, keeps screening and held-out seeds separate, and saves a challenger only when its held-out interval against the incumbent clears zero. The bundled report is in `training/competition-policy.json`. It measures performance against local bots.

To reproduce the initial report locally:

```bash
python competition_train.py --pairs 24 --held-out 64 --output competition-policy.json
python -m pip install -r requirements-chipzen.txt
python tests/chipzen_conformance.py
```

For scheduled play, run the same adapter on a stable host. A Colab runtime can disconnect, which stops the bot's lobby connection.

### Write a strategy once

A strategy is a callable accepting `(state, rng)`. It receives a public
`pokerbots_sdk.Observation` with its own hole cards, the board, stacks, and
legal moves. The supplied RNG keeps seeded matches repeatable. Return
`(action, None)` for check, call, or fold, or `("raise", total)` for the
total street bet. The adapters validate the decision before sending it
to the engine or Chipzen. Use only moves listed in `state.legal`; the
Chipzen adapter exposes check, call, fold, and raise.

**Value** and **Button Pressure** are selectable in Bot Arena. To add a
custom callable to a scripted Arena, pass a mapping to
`BotArena(seed, styles, strategies={"My strategy": decide})` and use its
name in the seat list. In Colab or at the command line, put your Python
module in the project root, then reference its callable as
`my_bot:decide`. Compare it against Value before live play:

```bash
python strategy_matchup.py --candidate my_bot:decide --control Value
python chipzen_entry.py --strategy my_bot:decide
```

The remote command needs the same Chipzen credentials as the notebook.
