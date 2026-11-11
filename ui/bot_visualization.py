from pathlib import Path
import json

import streamlit as st

from arena import EquityProfile

TRAINING = json.loads((Path(__file__).resolve().parents[1] / "training" / "champion.json").read_text())
CHAMPION = TRAINING["champion"]
PROFILE = EquityProfile(**TRAINING["profile"])


def render_bot_visualization(records, completed_hands, stats, names):
  st.title("Bot visualization")
  simulation, training = st.tabs(["Simulation", "Training match"])
  with simulation:
    eligible = {hand: turns for hand, turns in records.items() if hand in completed_hands}
    st.caption("Decision estimates become available after each hand settles.")
    if not eligible:
      st.info("Finish a hand against the champion or an Equity bot in the Arena to see its decisions.")
    else:
      hand = st.selectbox("Completed hand", sorted(eligible, reverse=True),
        format_func=lambda value: f"Hand {value}")
      turns = eligible[hand]
      index = st.selectbox("Bot decision", range(len(turns)),
        format_func=lambda i: f"{i + 1}. {names.get(turns[i]['seat'], 'Bot')} · "
          f"{turns[i]['phase'].capitalize()} · {turns[i]['action'].replace('_', ' ')}",
        key=f"bot_decision_{hand}")
      turn = turns[index]
      st.text(f"{turn['model']} · {turn['method']}")
      board = " ".join(f"{rank}{suit}" for rank, suit in turn["board"]) or "Preflop"
      st.text(f"{board} · Pot {turn['pot']:,} chips")
      if turn["method"] == "Tight fallback":
        st.caption("The bot used Tight for this partial call or multiway all-in.")
      else:
        outcomes = {"Win": turn["wins"], "Tie": turn["ties"], "Loss": turn["losses"]}
        total = sum(outcomes.values())
        columns = st.columns(3)
        columns[0].metric("Win rate", f"{turn['wins'] / total:.1%}")
        columns[1].metric("Equity (pot share)", f"{turn['equity']:.1%}")
        columns[2].metric("Outcomes checked", f"{total:,}")
        st.bar_chart([{"Outcome": key, "Count": value} for key, value in outcomes.items()],
          x="Outcome", y="Count")
        if turn["curve"]:
          st.line_chart(turn["curve"], x="Trials", y=["Equity", "Win rate"])
        st.caption("Estimates use the bot's cards and the board at the time of its decision, with uniformly sampled unknown cards. Equity credits ties with a share of the pot.")
      actual = stats.get(turn["seat"])
      if actual and actual["hands"]:
        st.caption(f"Actual session hands won or split: {actual['wins']}/{actual['hands']} "
          f"({actual['wins'] / actual['hands']:.1%}).")
  with training:
    match = TRAINING["training"]
    st.subheader(CHAMPION)
    st.caption(f"Latest training winner · seed {match['seed']} · {match['hands']} hands")
    st.dataframe([{"Model": row["model"], "Final chips": row["final_chips"],
      "Hands": row["hands"], "Hands won or split": row["hands_won"],
      "Hand win rate": f"{row['hands_won'] / row['hands']:.1%}" if row["hands"] else "—"}
      for row in match["results"]], hide_index=True)
    if "evaluation" in TRAINING:
      st.subheader("Held-out evaluation")
      st.dataframe([{"Opponent": label, "Seed pairs": result["pairs"], "bb/100": result["bb_per_100"],
        "95% interval": f"{result['interval_95'][0]:+.1f} to {result['interval_95'][1]:+.1f}"}
        for label, result in (
          ("Previous champion", TRAINING["evaluation"]["against_incumbent"]),
          ("Human-style practice bot", TRAINING["evaluation"]["against_human_style_proxy"]))], hide_index=True)
      st.caption("The practice bot uses public action frequencies from one uploaded game. Its results do not predict how you would play.")
    st.caption("Human vs Bots uses this tournament winner. One match does not establish which policy is strongest over many deals.")
