"""verity over HTTP — the verification gate, as a tiny verify-as-a-service.

The same Reality Anchor the MCP server exposes, reachable over plain HTTP for any
caller that can't speak MCP (a CI step on another host, a non-Python service, a
browser ``fetch``). One ``POST /verify`` in, one JSON verdict out::

    $ verity-serve                                   # listens on :8848
    $ curl -s localhost:8848/verify -d '{"claim":{"accuracy":0.72,"sample_size":18,
          "out_of_sample":false,"leakage_checked":false}}'
    {"verdict": "REFUSE", "dimensions": {...}, "issues": [...]}

STDLIB ONLY — ``http.server`` / ``BaseHTTPRequestHandler``, no web framework. The
handler is the thinnest possible shell over ``verify.verify``: it parses the JSON
body, resolves ground truth, calls ``verify``, and serialises the SAME verdict dict
(``{"verdict","dimensions","issues"}``) the library already returns. It adds no
verdict logic and no second vocabulary — the one gate ladder is the only authority.

Routes:
  * ``POST /verify``  — body ``{claim, truth?, evidence?, prior?, sources?}`` (truth is an
                        optional YAML *path* string or an inline resolved dict; omitted →
                        the packaged default, exactly like the CLI / MCP) → ``200`` verdict.
  * ``GET  /health``  — liveness probe → ``200 {"ok": true}``.
  * malformed JSON / wrong shape → ``400`` ``{"error": ...}``; unknown route → ``404``.

Deterministic and side-effect-free per request: like ``verify``, sources are treated
as caller-supplied resolved facts/text, NEVER fetched or crawled — the no-I/O rule of
the verifier holds across the wire too. (The only I/O is reading a ``truth`` YAML path
if the caller passes one, mirroring ``load_truth``.)
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .gate import load_truth
from .verify import verify

# The packaged default truth — the same one mcp.py / verify / the CLI fall back to.
_DEFAULT_TRUTH = Path(__file__).resolve().parent / "truth.yaml"


def _resolve_truth(spec) -> dict:
    """Turn the request's optional ``truth`` field into a resolved truth dict.

    Three shapes, matching how every other surface accepts truth:
      * ``None`` / missing  → the packaged default pack (``load_truth(_DEFAULT_TRUTH)``).
      * a string            → a YAML *path* to load (the CLI/MCP ``--truth`` / ``truth_path``).
      * a dict              → an already-resolved ``{thresholds, facts}`` pack, used as-is so a
                              caller can POST an inline domain pack without a file on the server.
    Anything else is ignored and falls back to the default — a weird ``truth`` value must not
    crash the request (``verify`` itself also tolerates a non-dict truth defensively).
    """
    if isinstance(spec, dict):
        return spec
    if isinstance(spec, str) and spec:
        return load_truth(spec)
    return load_truth(_DEFAULT_TRUTH)


def _verify_payload(body: dict) -> dict:
    """Run ``verify`` over a parsed request body and return the JSON-serialisable verdict.

    Pulls ``claim`` (required) plus the optional ``evidence`` / ``prior`` / ``sources`` /
    ``truth`` exactly as ``verify``'s keyword surface expects them — supplied-ness is preserved
    (a key present-but-``null`` is passed through as ``None``, "not supplied"). The returned dict
    is ``verify``'s own ``{"verdict","dimensions","issues"}``, which is already pure JSON.
    """
    claim = body.get("claim")
    return verify(
        claim,
        evidence=body.get("evidence"),
        prior=body.get("prior"),
        sources=body.get("sources"),
        truth=_resolve_truth(body.get("truth")),
    )


class _Handler(BaseHTTPRequestHandler):
    """The verify-as-a-service request handler. One method per supported route; everything else 404s.

    Kept deliberately small: parse → ``verify`` → serialise. All write paths go through ``_send``
    so a body is emitted exactly once with a correct ``Content-Length`` (a half-written response is
    its own kind of un-verifiable output). Errors are caught and turned into a structured 4xx/5xx
    JSON body rather than a stack-trace HTML page, so a programmatic client always gets parseable
    output.
    """

    server_version = "verity-serve/0.1"

    def _send(self, status: int, payload: dict) -> None:
        """Serialise ``payload`` as JSON and write it with the right status + Content-Length."""
        # default=str so a non-serialisable field inside an issue detail can never crash the
        # response writer — the verifier must stay up even on a weird value (same stance as gate.check).
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        """Read + parse the request body as a JSON object, or raise ValueError with a clear reason.

        A missing/oversized/garbled body, or a JSON value that isn't an object, is a client error —
        the caller is asking us to verify something that isn't a request. We raise here and the POST
        handler turns it into a 400; we never guess at a malformed body.
        """
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b""
        obj = json.loads(raw.decode("utf-8"))   # ValueError on malformed JSON → 400 upstream
        if not isinstance(obj, dict):
            raise ValueError("request body must be a JSON object")
        return obj

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's required casing
        if self.path.rstrip("/") in ("/health", ""):
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": f"no such route: GET {self.path}"})

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's required casing
        if self.path.rstrip("/") != "/verify":
            self._send(404, {"error": f"no such route: POST {self.path}"})
            return
        try:
            body = self._read_json()
        except ValueError as e:
            # malformed JSON / non-object body — a client error, reported as 400, never a 500.
            self._send(400, {"error": f"invalid JSON body: {e}"})
            return
        try:
            self._send(200, _verify_payload(body))
        except Exception as e:  # the verifier is defensive, but never 500 the service on a surprise
            self._send(400, {"error": f"could not verify claim: {e}"})

    def log_message(self, *_args) -> None:  # noqa: D401 — silence the default stderr access log
        """Suppress the noisy per-request stderr line; the service is a library primitive, not a daemon."""


def make_server(port: int = 0) -> HTTPServer:
    """Build (but don't start) the verify-as-a-service HTTP server bound on ``port``.

    ``port=0`` binds an EPHEMERAL port the OS chooses — read it back via ``srv.server_address[1]``.
    That is what tests use to run on a free port with zero collision risk. Call ``serve_forever()``
    on the returned server to run it, or ``handle_request()`` to serve exactly one request.
    """
    return HTTPServer(("127.0.0.1", port), _Handler)


def run(port: int = 8848) -> None:  # pragma: no cover — blocking entrypoint for the console script
    """Console-script entry: serve the gate over HTTP on ``port`` until interrupted (Ctrl-C)."""
    srv = make_server(port)
    host, bound = srv.server_address[0], srv.server_address[1]
    print(f"verity-serve listening on http://{host}:{bound}  "
          f"(POST /verify · GET /health) — Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":  # pragma: no cover
    run()
