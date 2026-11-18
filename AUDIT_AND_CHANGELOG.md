# Ashwing Poker release notes

## 18 November 2026

- Renamed the live app to **Ashwing Poker** and moved it to [ashwingpoker.streamlit.app](https://ashwingpoker.streamlit.app/).
- Added animated demon wings and a tail to the lobby title. The animation follows reduced-motion preferences.
- Held Ashwing’s current speech bubble for at least three seconds. The chat transcript records every line while the table continues to advance.
- Released Search with the short-stack equity policy in Streamlit. The hosted Chipzen entry is named `Ashwing_v2`.
- Removed archived benchmark outputs from the active branch. The engine, policy inputs, and replay fixtures used by the regression suite are tracked.

## Session and data behavior

Games and replays live in Streamlit session state. Export completed hands to keep them beyond a session. The export uses numbered seats and includes only cards revealed at showdown. Pass-and-play hides a seat’s private cards until its player reveals them on the shared device.
