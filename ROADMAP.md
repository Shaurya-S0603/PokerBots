# PokerBots roadmap

GitHub is the source of truth. Develop each milestone on a branch, validate it, then merge into main. Streamlit deploys main/app.py. Keep credentials in Streamlit secrets, never in Git.

## 1. Desktop and mobile browser validation

- Exercise setup, every legal action, bot turns, pass-and-play privacy, showdown, side pots, next hand, and restart in actual browsers.
- Cover desktop, tablet and phone widths, touch targets, keyboard navigation, focus, contrast and reduced motion.
- Record reproducible failures and add browser regression tests alongside the engine suite.
- Done when critical flows finish without console errors, hidden-card leaks, clipping, or chip conservation failures.

## 2. Save and resume across sessions

- Define a versioned JSON game-state schema and validate cards, stacks, contributions, action order and pot eligibility on restore. Never deserialize user-supplied pickle.
- Add downloadable saves first, with explicit save/load controls and malformed-save tests.
- Add durable server-side storage and authenticated ownership for automatic cross-device resume. Streamlit session state and local disk are not the durable database.
- Preserve stacks, dealer rotation, board, deck, bets and pending action; prevent duplicate actions/payouts and concurrent overwrite.
- Done when reload/restart can restore a mid-hand state exactly, corrupt saves are rejected, and one user cannot read another user's private game.

## 3. Stronger poker AI

- Introduce a decision interface using only the bot's hole cards, public board, betting history and legal actions.
- Add Monte Carlo equity, pot odds, position-aware ranges and bounded bet sizing; keep inference time within a measured UI budget.
- Benchmark seeded tournaments against the current heuristic bot and report uncertainty, action legality and latency.
- Done when the new bot demonstrably improves the benchmark without hidden information or illegal actions. Do not label heuristics or simulations as GTO.

## 4. Authenticated online multiplayer

- Build a server-authoritative room/action service with verified identity and per-seat authorization; do not trust client-supplied player IDs.
- Store transactions durably; use action version numbers, idempotency, reconnect handling, turn timers and private per-player views.
- Choose a realtime client/backend transport before implementation. Streamlit can remain the prototype or lobby; shared session state is not a multiplayer server.
- Test concurrent actions, stale requests, disconnects, spectators, all-ins, side pots and multi-winner payouts.
- Done when separate authenticated devices can complete and resume hands without leaking hole cards, double actions or double payouts.

## Release checklist

- Engine and UI tests pass.
- No secrets, session saves or personal data committed.
- Deployment smoke check passes after merging.
- Update README and changelog with behavior changes and known limitations.
