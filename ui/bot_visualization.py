from pathlib import Path
import json

import streamlit as st

from arena import EquityProfile

TRAINING = json.loads((Path(__file__).resolve().parents[1] / "training" / "champion.json").read_text())
CHAMPION = TRAINING["champion"]
PROFILE = EquityProfile(**TRAINING["profile"])
BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"
REPORTS = {"Betting-line challengers · 100 BB": "betting-line-experiment.json",
  "Betting-line challengers · 15 BB": "betting-line-shallow.json",
  "River-call experiment": "river-experiment.json"}


def render_bot_visualization(records, completed_hands, stats, names):
  st.title("Bot visualization")
  simulation, training, replays = st.tabs(["Simulation", "Training match", "Replay comparison"])
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
      if turn.get("decision_basis"):
        st.caption(f"Decision rule · {turn['decision_basis']}")
      if "pot_odds" in turn:
        label = f"Pot odds {turn['pot_odds']:.1%}"
        if "call_threshold" in turn:
          label += f" · Call threshold {turn['call_threshold']:.1%}"
        st.caption(label)
      if "weighted_equity" in turn:
        st.metric("Weighted equity", f"{turn['weighted_equity']:.1%}")
      if turn["method"] == "Tight fallback":
        st.caption("The bot used Tight for this partial call or multiway all-in.")
      elif turn["method"] == "Preflop range":
        st.caption(f"Strength score {turn['preflop_strength']:.2f} · "
          f"Threshold {turn['preflop_strength_threshold']:.2f} · "
          f"Effective stack {turn['effective_stack_bb']:.1f} BB")
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
          series = ["Equity", "Win rate"]
          if "Weighted equity" in turn["curve"][0]:
            series.append("Weighted equity")
          st.line_chart(turn["curve"], x="Trials", y=series)
        st.caption("Estimates use the bot's cards and the board at the time of its decision, with uniformly sampled unknown cards. Equity credits ties with a share of the pot.")
      actual = stats.get(turn["seat"])
      if actual and actual["hands"]:
        st.caption(f"Actual session hands won or split: {actual['wins']}/{actual['hands']} "
          f"({actual['wins'] / actual['hands']:.1%}).")
  with training:
    match = TRAINING["training"]
    st.subheader(CHAMPION)
    st.caption(f"Generation {TRAINING.get('generation', 1)} winner · seed {match['seed']} · {match['hands']} hands · {match['starting_stack']:,} starting chips")
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
      games = len(TRAINING.get("human_sources", [TRAINING["human_source"]]))
      st.caption(f"The practice bot uses public action frequencies from {games} uploaded games. Its results do not predict how you would play.")
    st.caption("Human vs Bots uses this tournament winner. One match does not establish which policy is strongest over many deals.")

  with replays:
    render_river_experiment()


def render_river_experiment():
  available = {name: filename for name, filename in REPORTS.items() if (BENCHMARKS / filename).exists()}
  if not available:
    st.info("Run the offline river experiment to load the replay comparisons.")
    return
  experiment = st.selectbox("Experiment", list(available))
  report = json.loads((BENCHMARKS / available[experiment]).read_text())
  st.subheader("Chipzen decision fixtures")
  fixture = st.selectbox("Replay decision", report["fixtures"],
    format_func=lambda item: f"{item['opponent']} · Hand {item['hand']} · "
      f"{'River' if len(item['board'].split()) == 5 else 'Turn'}")
  st.caption(f"Hole cards {fixture['hole']} · Board {fixture['board']} · "
    f"Pot {fixture['pot']:,} · To call {fixture['call']:,} · Replay action {fixture['replay_action']}")
  st.link_button("Open Chipzen replay", fixture["source"])

  def percent(value):
    return f"{value:.1%}" if value is not None else "—"

  rows = []
  for name, decision in fixture["decisions"].items():
    action = decision["action"]
    if decision["raise_to"] is not None:
      action = f"raise to {decision['raise_to']:,}"
    rows.append({"Policy": name, "Action": action, "Pot odds": percent(decision["pot_odds"]),
      "Uniform equity": percent(decision["uniform_equity"]),
      "Weighted equity": percent(decision["weighted_equity"]),
      "Call threshold": percent(decision["call_threshold"])})
  st.dataframe(rows, hide_index=True)
  for name, decision in fixture["decisions"].items():
    if options := decision.get("bet_options"):
      st.caption(f"{name} · modeled EV assumes fold or call, then showdown.")
      st.dataframe([{"Action": row["action"], "Bet chips": row["amount"],
        "EV chips": round(row["ev_chips"], 1), "Worse calls": percent(row.get("worse_call_mass")),
        "Better calls": percent(row.get("better_call_mass")),
        "Better folds": percent(row.get("better_fold_mass"))} for row in options], hide_index=True)
      break

  st.subheader("Fresh seat-swapped deals")
  config = report["config"]
  st.caption(f"{config['pairs_per_opponent']} seed pairs per matchup · "
    f"{config['stack'] / config['big_blind']:g} BB starting stack")
  st.dataframe([{"Opponent": row["opponent"], "Policy": row["strategy"],
    "bb/100": f"{row['bb_per_100']:+.2f}",
    "95% interval": f"{row['interval_95'][0]:+.2f} to {row['interval_95'][1]:+.2f}",
    "Δ vs Value": f"{row['delta_vs_value']:+.2f}",
    "Δ 95% interval": f"{row['delta_interval_95'][0]:+.2f} to {row['delta_interval_95'][1]:+.2f}",
    "Turn chips lost": row["large_call_losses"]["turn"]["chips_paid_on_lost_hands"],
    "River chips lost": row["large_call_losses"]["river"]["chips_paid_on_lost_hands"],
    "p95 decision (ms)": round(row["decision_ms_p95"], 2)} for row in report["results"]], hide_index=True)
  st.caption("Chip losses count calls costing at least two-thirds of the pot before the latest opponent bet, "
    "on hands where the bot received no payout.")
  if "position" in report["results"][0]:
    st.subheader("Preflop and position")
    st.dataframe([{"Opponent": row["opponent"], "Policy": row["strategy"],
      "Button limp": percent(row["position"]["button_limp_rate"]),
      "Button open raise": percent(row["position"]["button_open_raise_rate"]),
      "Fold after limp and raise": percent(row["position"]["fold_after_limp_raise_rate"]),
      "Limp-raise opportunities": row["position"]["faced_raise_after_limp"],
      "Button bb/100": round(row["position"]["button_bb_per_100"], 2),
      "Big blind bb/100": round(row["position"]["big_blind_bb_per_100"], 2)}
      for row in report["results"]], hide_index=True)
