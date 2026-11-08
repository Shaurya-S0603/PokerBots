# PokerRoom audit and changelog

## Scope

The original upload is a Streamlit application (`app.py`) backed by Python game rules (`pokerroom.py`). The updated application keeps that model. It uses an external table template (`ui/table.html`), styles (`ui/styles.css`), animation script (`ui/effects.js`) and a small Streamlit UI adapter. JavaScript does not control betting or reveal secret cards.

## Error audit

| Category | Original location | Issue and cause | Applied fix |
|---|---|---|---|
| Layout | `app.py`, `_render_table()` | The felt `<div>` opened in one `st.markdown()` call and closed after independent `st.columns()` widgets. Streamlit blocks do not nest across these calls; seats do not sit inside the intended felt DOM container. | Render the full table and seats in one HTML fragment, using `ui/table.html`, `ui/render.py` and responsive CSS. |
| Error feedback | `app.py`, `_render_actions()` | `st.error()` appeared before an immediate `st.rerun()`, so users could not read rejected-action feedback. | Store errors in session state and render the message on the next run. |
| Statistics | `app.py`, `_record()` | VPIP incremented for every call, raise or all-in on any street rather than once per hand before the flop. The `chips` statistic added payouts but never deducted invested chips. | Separate action events and hand settlement in `ui/session.py`; compute per-hand VPIP, PFR, net chip changes and showdown results. |
| New-session reset | `app.py`, `_start_game()` | Stats, last action and completed-hand marker were not reset consistently, potentially carrying one game's results into another. | Reset all session-scoped counters and markers when starting a new game. |
| Champion | `app.py`, `_render_showdown()` | Game-over screen picked `winners[0]` from the most recent pot instead of the one player with a positive stack. | Derive the champion from surviving stack balances. |
| Raise UX | `app.py`, `_render_actions()` | The numeric control allowed an input above the stack when the only legal raise was a short all-in. A rejected action could look legal. | Bound target total-bet input to the engine's maximum and handle the all-in-only range. |
| Bot stability | `poker_bot.py`, `_raise_amount()` | `randint(min_raise_total, max_raise_total)` raised `ValueError` when short all-in raises had `min_raise_total > max_raise_total`. | Detect short all-ins and return the only legal extra-chip contribution. |
| Bot balance | `poker_bot.py`, `choose()` and `_strength()` | Easy/Medium/Hard shared almost the same decision strategy; Easy could make wildly oversized random bets and preflop strength used only category. | Add simple preflop hand-quality estimates, cap bet sizes, and vary aggression and bluff rates by difficulty. These are heuristic, not trained bots. |
| Private cards | `app.py`, `_render_table()` and `_render_actions()` | Hole-card displays depended on separate fragments and private handoff was difficult to distinguish visually. | Render a public table until the named player reveals, use `get_state(player_id)` only for that active player's view, and mark hidden cards explicitly. |
| HTML safety | `app.py`, `_render_showdown()` | Custom names were interpolated into HTML-like output without consistently escaping it. | Escape user-controlled name text and card labels in all generated table fragments. Keep winner summaries in native Streamlit widgets. |
| UI settings | `app.py`, `_render_sidebar()` | The sound toggle had no actual playback implementation. | Remove inert option; keep an operative reduced-motion option and functional CSS/JS visual action feedback. |
| Testing | `tests/` | Bare `pytest` could fail import discovery for top-level engine modules. Only three smoke tests existed. | Add `pytest.ini` and regression tests for chip conservation, short all-ins, side pots, odd chips, card visibility, bot legality and session metrics. |
| Navigation | `app.py`, `_render_sidebar()` | The Main Menu action erased the running game, making a simple navigation operation destructive. | Keep game object when visiting menu and provide Resume current game. A new game explicitly replaces it. |

## UI changes

- Premium dark navy and green-felt table with a restrained gold accent.
- Separate, reusable HTML/CSS presentation assets.
- Responsive mobile layout that moves seats into a two-column grid.
- Accessible button labels, focus rings, semantic card labels, status messages and reduced-motion support.
- Visible active seat, chip stacks, current bets, turn phase, blinds and all-in/fold status.
- Cleaner new-game form, name validation, pass-and-play handoff, onboarding, controls, history and statistics.

## Gameplay changes

- Action feedback survives Streamlit reruns.
- Contextual Raise to input with server-side conversion to extra chip amount.
- Human-vs-bot mode remains a basic heuristic baseline with less erratic bet sizing.
- Showdown displays revealed hands and separate pot payouts; early-fold victories do not reveal mucked cards.
- Hand-over screen and Next hand action preserve persistent stacks.

## Verification and limitations

- Static compilation of Python files: passed.
- `pytest -q`: 12 tests passed after adding `pytest.ini`.
- Random game simulations across 2–10 players, many hand restarts and mixed actions completed without a chip-conservation failure.
- Bot stress run completed over 600,000 action calls without rejected actions across the tested seeds, including short stacks.
- Streamlit itself was not installed in this execution environment and package download access was unavailable. Therefore, a live Streamlit rendering, browser-console and end-to-end keyboard/WCAG audit could **not** be completed here. Visual and contrast choices are accessibility-oriented but not a formal AA certification.
- No external navigation links exist in the supplied application, so there were no external links to repair.
- Save/load between browser sessions, real remote multiplayer, and tournament blind escalation remain optional additions.

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```
