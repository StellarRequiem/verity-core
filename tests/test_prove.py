"""Proof-carrying claims: a claim PASSES only if its `proof` command re-derives
the claimed number. No proof, a failing command, unparseable output, or a
mismatch must all REFUSE — a verifier that believes a number it can't reproduce
is the bug this whole module exists to kill."""
import sys

from verity.prove import prove, prove_batch, extract_value, format_prove_block

PY = sys.executable  # the running interpreter — portable across CI/host


def _proof(expr: str) -> str:
    """A proof command that prints `expr` to stdout, using this interpreter."""
    return f'{PY} -c "print({expr})"'


# ---- the happy path: the number reproduces ----
def test_pass_when_value_reproduces():
    claim = {"name": "acc", "metric": "accuracy", "value": 0.94, "proof": _proof("0.94")}
    r = prove(claim)
    assert r["verdict"] == "PASS"
    assert r["reproduced"] == 0.94 and r["returncode"] == 0


def test_pass_within_tolerance():
    claim = {"name": "t", "value": 0.940, "proof": _proof("0.9405"), "tolerance": 0.001}
    assert prove(claim)["verdict"] == "PASS"


def test_pass_json_keyed_by_metric():
    # argv list avoids shell/JSON double-escaping; prints {"auc": 0.88, "loss": 0.3}
    claim = {"name": "j", "metric": "auc", "value": 0.88,
             "proof": [PY, "-c", "print('{\"auc\": 0.88, \"loss\": 0.3}')"]}
    r = prove(claim)
    assert r["verdict"] == "PASS" and r["reproduced"] == 0.88


def test_pass_argv_list_proof():
    claim = {"name": "argv", "value": 0.5, "proof": [PY, "-c", "print(0.5)"]}
    assert prove(claim)["verdict"] == "PASS"


# ---- the refusals: every way a proof can fail to back the claim ----
def test_refuse_no_proof():
    r = prove({"name": "x", "value": 0.9})
    assert r["verdict"] == "REFUSE" and "not re-runnable" in r["detail"]


def test_refuse_mismatch():
    claim = {"name": "lie", "value": 0.99, "proof": _proof("0.50")}
    r = prove(claim)
    assert r["verdict"] == "REFUSE"
    assert r["reproduced"] == 0.50 and "≠" in r["detail"]


def test_refuse_command_errors():
    claim = {"name": "boom", "value": 0.9, "proof": f'{PY} -c "import sys; sys.exit(3)"'}
    r = prove(claim)
    assert r["verdict"] == "REFUSE" and r["returncode"] == 3 and "exited 3" in r["detail"]


def test_refuse_unparseable_output():
    claim = {"name": "noisy", "value": 0.9, "proof": _proof("'all done, no numbers here'")}
    assert prove(claim)["verdict"] == "REFUSE"


def test_refuse_no_claimed_value():
    r = prove({"name": "blank", "proof": _proof("0.9")})
    assert r["verdict"] == "REFUSE" and "no claimed value" in r["detail"]


def test_refuse_command_not_found():
    r = prove({"name": "missing", "value": 0.9, "proof": "definitely-not-a-real-binary-xyz --go"})
    assert r["verdict"] == "REFUSE" and r["returncode"] is None


def test_refuse_nonnumeric_claim():
    r = prove({"name": "str", "value": "high", "proof": _proof("0.9")})
    assert r["verdict"] == "REFUSE" and "not numeric" in r["detail"]


# ---- value extraction: JSON, labelled line, last-number fallback ----
def test_extract_bare_number():
    assert extract_value("0.91\n") == 0.91


def test_extract_last_number_is_headline():
    assert extract_value("epoch 1 loss 2.0\nepoch 2 loss 1.0\naccuracy 0.93") == 0.93


def test_extract_labelled_line_beats_trailing_noise():
    # labelled metric wins over a later unrelated number
    assert extract_value("accuracy: 0.87\nelapsed 42s", metric="accuracy") == 0.87


def test_extract_scientific_notation():
    assert extract_value("p = 1.2e-09") == 1.2e-09


def test_extract_none_when_empty():
    assert extract_value("") is None


def test_extract_json_bool_is_not_a_metric():
    # `true` must not be read as 1.0
    assert extract_value("true") is None


# ---- batch + formatting ----
def test_prove_batch_worst_and_order():
    claims = [
        {"name": "ok", "value": 0.5, "proof": _proof("0.5")},
        {"name": "bad", "value": 0.9, "proof": _proof("0.1")},
    ]
    results = prove_batch(claims)
    assert [r["verdict"] for r in results] == ["PASS", "REFUSE"]


def test_format_block_one_line():
    r = prove({"name": "fmt", "value": 0.5, "proof": _proof("0.5")})
    line = format_prove_block(r)
    assert line.strip().startswith("[PASS") and "fmt" in line
