"""The ML-security / adversarial-robustness pack loads and is tuned: an honest robustness claim
(explicit threat model + adaptive attack + AutoAttack) PASSES, while the field's classic tells —
gradient masking / obfuscated gradients / security-through-obscurity, and weak FGSM-only /
non-adaptive evaluation — REFUSE. The non-adaptive case is the canonical-substring trap made
explicit: it must REFUSE even though the forbidden term "non-adaptive" embeds the canonical
substring "adaptive attack" (the bad claim avoids asserting that canonical phrasing)."""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "ml-security.yaml")


# An honest robustness claim: states a threat model, uses an adaptive attack, benchmarks with
# AutoAttack, and reports the strongest known attack. High robust accuracy is NOT auto-suspect here.
HONEST = {
    "accuracy": 0.62, "sample_size": 10000,
    "out_of_sample": False, "leakage_checked": False,
    "text": ("robust accuracy under a clearly stated threat model (Linf eps=8/255), evaluated "
             "with an adaptive attack designed against the defense and benchmarked with AutoAttack; "
             "we report accuracy under the strongest known attack"),
}


def test_ml_security_pack_passes_honest_robustness_claim():
    assert check(HONEST, _truth())["verdict"] == "PASS"


def test_ml_security_pack_refuses_gradient_masking():
    # The Athalye-et-al. failure mode: high "robust" accuracy via obfuscated gradients / gradient
    # masking / security through obscurity — broken under an adaptive attack. CRITICAL ground-truth.
    bad = {
        "accuracy": 0.95, "sample_size": 10000,
        "text": ("our defense reaches high robust accuracy via gradient masking; gradients are "
                 "obfuscated so attacks fail. security through obscurity, by design"),
    }
    r = check(bad, _truth())
    assert r["verdict"] == "REFUSE"
    assert any(i["check"] == "adaptive_threat_model" for i in r["issues"])


def test_ml_security_pack_refuses_weak_nonadaptive_eval_substring_trap():
    # THE TRAP: "non-adaptive" contains the canonical substring "adaptive attack" — so the matcher
    # would self-suppress the flag IF the claim also wrote that canonical phrasing. This bad claim
    # deliberately uses "non-adaptive, single-step attack only (fgsm-only)" and asserts NO canonical
    # evidence (no "threat model"/"adaptive attack"/"certified"/"AutoAttack"), so the forbidden
    # marker fires and the claim REFUSEs — proving the weakest-attack tell is caught, not laundered.
    bad = {
        "accuracy": 0.93, "sample_size": 10000,
        "text": ("robustness evaluated only with a non-adaptive, single-step attack only "
                 "(fgsm-only) against the perturbation defense"),
    }
    r = check(bad, _truth())
    assert r["verdict"] == "REFUSE"
    sec = [i for i in r["issues"] if i["check"] == "adaptive_threat_model"]
    assert sec, "the non-adaptive forbidden term must fire (canonical substring must NOT suppress it)"
    assert "non-adaptive" in sec[0]["detail"]


def test_ml_security_pack_passes_certified_defense():
    # A certified defense (randomized smoothing) is a legitimate canonical path — "certified"
    # grounds the claim, so an in-domain robustness claim with certified accuracy PASSES.
    certified = {
        "accuracy": 0.70, "sample_size": 5000,
        "text": ("certified robustness via randomized smoothing under an Linf threat model; "
                 "certified accuracy reported and cross-checked with AutoAttack"),
    }
    assert check(certified, _truth())["verdict"] == "PASS"


def test_ml_security_pack_does_not_fire_off_domain():
    # Domain-gating: an ordinary classifier claim with none of the adversarial keywords must not
    # trip the security fact (it would be governed by ml-classification.yaml instead).
    off_domain = {
        "accuracy": 0.62, "sample_size": 10000, "out_of_sample": False, "leakage_checked": False,
        "text": "tabular fraud classifier on a held-out test set; ordinary supervised evaluation",
    }
    r = check(off_domain, _truth())
    assert not any(i["check"] == "adaptive_threat_model" for i in r["issues"])
    assert r["verdict"] == "PASS"
