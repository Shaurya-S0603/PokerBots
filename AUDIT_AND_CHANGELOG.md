# Ashwing Poker release notes

## 24 November 2026 — Ashwing V4

- Selected the reviewed **guarded V4** policy for Streamlit and the Chipzen build workflow. The policy and training files match the frozen benchmark source; broad experimental routing stays disabled.
- Added public commitment metadata and match-scoped public action history to the Streamlit adapter, with duplicate-hand protection. Opponent-specific river learning is only supplied against the human it observed.
- V4's final local holdout ran 3,168 matches on 648 seed blocks: 101/192 wins directly versus v3, with improvement against released v2 and six-player fields still uncertain. Deployment was explicitly approved after review.
- Uploaded the tested Linux AMD64 image to Chipzen as `Ashwing_V4`, replacing the approved-for-deletion `Ashwing_v2` entry. Uploaded archive SHA-256: `8ce7e271589941ba4c0fe3dbe27e00f7a4647819a22f3e39456e04f72048fc34`.
- Validation: 91 repository tests and four SDK conformance checks passed. The original image also passed its packaged-runtime and legal-action checks. Actual hosted processing status is managed by Chipzen.

## 18 November 2026

- Renamed the live app to **Ashwing Poker** and moved it to [ashwingpoker.streamlit.app](https://ashwingpoker.streamlit.app/).
- Added animated demon wings and a tail to the lobby title. The animation follows reduced-motion preferences.
- Held Ashwing’s current speech bubble for at least three seconds. The chat transcript records every line while the table continues to advance.
- Released Search with the short-stack equity policy in Streamlit. The hosted Chipzen entry is named `Ashwing_v2`.
- Removed archived benchmark outputs from the active branch. The engine, policy inputs, and replay fixtures used by the regression suite are tracked.

## Session and data behavior

Games and replays live in Streamlit session state. Export completed hands to keep them beyond a session. The export uses numbered seats and includes only cards revealed at showdown. Pass-and-play hides a seat’s private cards until its player reveals them on the shared device.
