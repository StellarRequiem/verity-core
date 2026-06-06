"""The HTTP surface — verify-as-a-service answers the ONE gate ladder over real HTTP.

These are end-to-end tests against a live server bound on an EPHEMERAL port (``port=0``,
so there is no fixed-port collision risk) and driven through actual ``urllib`` requests —
not the handler in isolation. They prove the wire contract the README/CLI promise: a
fabrication-class claim comes back REFUSE, an honest claim PASS, ``/health`` is live, and a
malformed body is a clean 400 (not a 500 / stack trace). STDLIB only, like the server.
"""
import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager

from verity.server import make_server, run  # run() must be importable for the console script


@contextmanager
def _serving():
    """Start the server on an OS-chosen port in a daemon thread; yield its base URL; tear down.

    Uses ``handle_request`` in a loop rather than ``serve_forever`` so the thread exits cleanly the
    moment we close the socket — no hung daemon between tests. The bound port is read back from
    ``server_address`` (the whole point of ``port=0``).
    """
    srv = make_server(port=0)
    host, port = srv.server_address[0], srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)


def _post(base: str, path: str, payload):
    """POST ``payload`` (raw bytes if bytes, else JSON) to ``base+path``; return ``(status, body)``.

    A non-2xx is delivered by urllib as ``HTTPError`` — we catch it and return its code + body so a
    test can assert on a 400 exactly as it asserts on a 200 (the error body is JSON we want to read).
    """
    data = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def _get(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def test_health_is_live():
    with _serving() as base:
        status, body = _get(base, "/health")
        assert status == 200
        assert body == {"ok": True}


def test_post_verify_refuses_a_junk_claim():
    # tiny sample + impossible-to-trust 72% + nothing affirmed → CRITICAL noise floor → REFUSE
    claim = {"name": "junk", "accuracy": 0.72, "sample_size": 8,
             "out_of_sample": False, "leakage_checked": False}
    with _serving() as base:
        status, body = _post(base, "/verify", {"claim": claim})
        assert status == 200
        assert body["verdict"] == "REFUSE"
        # the verdict carries the real gate output, not a stub: a structural issue is present.
        assert any(i["source"] == "structural" for i in body["issues"])


def test_post_verify_passes_an_honest_claim():
    claim = {"name": "honest", "accuracy": 0.51, "sample_size": 300,
             "out_of_sample": True, "leakage_checked": True,
             "text": "daily directional, walk-forward holdout, no look-ahead"}
    with _serving() as base:
        status, body = _post(base, "/verify", {"claim": claim})
        assert status == 200
        assert body["verdict"] == "PASS"
        assert body["dimensions"]["empirical"]["verdict"] == "PASS"


def test_post_verify_runs_evidence_dimension_over_the_wire():
    # claims 72% but recomputed evidence says 58% → fabrication-class CRITICAL → REFUSE,
    # and the evidence dimension must show up in the JSON (proves the extra args cross the wire).
    with _serving() as base:
        status, body = _post(base, "/verify", {
            "claim": {"name": "inflated", "accuracy": 0.72, "sample_size": 400,
                      "out_of_sample": True, "leakage_checked": True},
            "evidence": {"accuracy": 0.58},
            "sources": ["recomputed.csv"],
        })
        assert status == 200
        assert body["verdict"] == "REFUSE"
        assert "evidence" in body["dimensions"]


def test_malformed_json_body_is_a_clean_400():
    with _serving() as base:
        status, body = _post(base, "/verify", b"{not valid json}")
        assert status == 400
        assert "error" in body                       # structured error, not an HTML stack trace


def test_unknown_route_404s():
    with _serving() as base:
        status, body = _post(base, "/nope", {"claim": {}})
        assert status == 404 and "error" in body


def test_run_is_importable_for_the_console_script():
    # the wiring target 'verity-serve = verity.server:run' must resolve to a callable.
    assert callable(run)
