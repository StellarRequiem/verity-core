"""The agent-self-check example must demonstrate the real pattern, not just narrate it:
the agent REFUSES the flashy-but-false finding and ACTS on the honest, well-powered one."""
import importlib.util
from pathlib import Path

_ex = Path(__file__).resolve().parent.parent / "examples" / "agent_self_check.py"
_spec = importlib.util.spec_from_file_location("_agent_self_check", _ex)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_agent_refuses_hype_acts_on_honest():
    assert _mod.agent_acts_on(_mod.HYPE) is False     # 95% on 15 trades -> REFUSE
    assert _mod.agent_acts_on(_mod.HONEST) is True    # 56% on 1200 OOS  -> PASS


def test_example_self_check_passes():
    assert _mod.main() == 0                            # the example's own assertion holds
