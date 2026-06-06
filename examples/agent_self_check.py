"""An agent that refuses to fool itself.

verity's whole reason to exist as an MCP tool: an AI agent can gate its OWN result-claims before it
acts on them. This is that pattern — runnable and self-contained. A stand-in "agent" produces a
finding, runs it through ``verify()``, and *refuses to believe* a number that doesn't clear the bar.

    python examples/agent_self_check.py

The same call is available to any real agent over MCP (the ``verify`` tool), so a model can check
itself before reporting a number to you — which is the only way "95% accuracy!" stops being load-
bearing on a vibe.
"""
from __future__ import annotations

from verity import verify

# A domain bar the agent holds itself to (here: trading/quant — small edges, real samples).
TRUTH = {"thresholds": {"suspicious_accuracy": 0.65, "hard_min_sample": 30, "min_sample": 100,
                        "require_out_of_sample": True}, "facts": []}


def agent_acts_on(finding: dict) -> bool:
    """The pattern: verify BEFORE believing. Returns whether the agent will act on the finding."""
    v = verify(finding, truth=TRUTH)
    if v["verdict"] == "REFUSE":
        reasons = "; ".join(i["detail"] for i in v["issues"])
        print(f"  [agent] REFUSE — will NOT act on '{finding['name']}'\n          ↳ {reasons}")
        return False
    if v["verdict"] == "WARN":
        print(f"  [agent] WARN — acting on '{finding['name']}', but flagging caveats to the user")
        return True
    print(f"  [agent] PASS — acting on '{finding['name']}' (cleared the bar)")
    return True


# What an over-eager agent might "discover" and want to report …
HYPE = {"name": "found alpha 🚀", "accuracy": 0.95, "sample_size": 15, "out_of_sample": False,
        "text": "95% win-rate on a 15-trade backtest"}
# … versus an honest, well-powered finding.
HONEST = {"name": "modest directional signal", "accuracy": 0.56, "sample_size": 1200,
          "out_of_sample": True, "leakage_checked": True,
          "text": "56% hit-rate over 1200 out-of-sample, walk-forward trades"}


def main() -> int:
    print("agent reports a flashy 95%-on-15-trades 'edge':")
    acted_hype = agent_acts_on(HYPE)        # REFUSE: tiny sample, auto-suspect accuracy, not OOS
    print("\nagent reports a modest 56%-on-1200-OOS signal:")
    acted_honest = agent_acts_on(HONEST)    # PASS: powered, out-of-sample, not auto-suspect
    print("\nthe point: the agent believed the boring true thing and refused the exciting false one.")
    return 0 if (not acted_hype and acted_honest) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
