"""Adversarial red-team of the live anchor — can a hallucination slip through to PASS?

The bar: a claim whose value the sources do NOT assert must NEVER reach PASS. It must be
REFUSE (a source contradicts) or UNVERIFIABLE (nothing corroborates it). The ONLY way a false
claim PASSes is if a SOURCE itself asserts the false value — trust-root poisoning, the
comparator-not-oracle limit, mitigated by hard-to-forge sources + per-key cross-ref, NOT by
this logic. Every test tries an attack and asserts the anchor did not get fooled.
"""
from verity.anchor import anchor, Source, PASS, REFUSE, UNVERIFIABLE


class Src(Source):
    def __init__(self, id, facts):
        self.id = id
        self._f = facts

    def fetch(self, claim, proof):
        return dict(self._f) if self._f is not None else None


class Boom(Source):
    id = "boom"

    def fetch(self, claim, proof):
        raise RuntimeError("source is down")


C = {"name": "x", "v": 0.50}   # the claim under attack


def test_no_source_cannot_pass():
    assert anchor(C, [], min_sources=1).verdict == UNVERIFIABLE


def test_ungrounded_field_cannot_pass():
    # the source asserts a different field; the claimed 'v' is unsupported
    assert anchor(C, [Src("a", {"other": 1})], min_sources=1).verdict == UNVERIFIABLE


def test_one_supporter_under_min_cannot_pass():
    assert anchor(C, [Src("a", {"v": 0.50})], min_sources=2).verdict == UNVERIFIABLE


def test_consensus_cannot_launder_a_lie():
    # 3 agreeing yes-men + 1 real contradictor -> REFUSE. Agreement counts for nothing.
    srcs = [Src("a", {"v": 0.50}), Src("b", {"v": 0.50}), Src("c", {"v": 0.50}), Src("real", {"v": 0.99})]
    assert anchor(C, srcs, min_sources=2).verdict == REFUSE


def test_numeric_vs_garbage_cannot_false_pass():
    # junk for a numeric field is silent (not support) -> cannot PASS, and is not a false REFUSE
    assert anchor(C, [Src("a", {"v": float("nan")})], min_sources=1).verdict == UNVERIFIABLE


def test_crashing_source_cannot_be_grounding():
    assert anchor(C, [Boom()], min_sources=1).verdict == UNVERIFIABLE


def test_tolerance_just_outside_is_refuse():
    assert anchor(C, [Src("a", {"v": 0.99})], min_sources=1).verdict == REFUSE


def test_bool_flip_cannot_pass():
    assert anchor({"name": "b", "ok": True}, [Src("a", {"ok": False})], min_sources=1).verdict == REFUSE


def test_mixed_panel_one_contradictor_still_refuses():
    # a supporter + a silent + a contradictor -> REFUSE (contradiction beats support beats silent)
    srcs = [Src("ok", {"v": 0.50}), Src("mute", {}), Src("liar", {"v": 0.10})]
    assert anchor(C, srcs, min_sources=1).verdict == REFUSE


def test_control_genuine_corroboration_does_pass():
    # not just refusing everything: a truly corroborated claim PASSes (no blanket false-negatives)
    assert anchor(C, [Src("a", {"v": 0.50}), Src("b", {"v": 0.50})], min_sources=2).verdict == PASS
