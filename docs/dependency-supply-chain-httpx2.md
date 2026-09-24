# Dependency Supply-Chain Note: `httpx2` and the `starlette` test-client migration

Status: resolved. The test extra now depends on `httpx2` (option C in the
table below): the behavioral audit found no malicious code, the fork is
stewarded by Pydantic Services Inc. with the original `httpx` author listed
as package author, `starlette`'s test client prefers it, and staying on
official `httpx` meant a deprecated fallback path plus an unmaintained
transport (no release since 0.28.1 of 2024-12). This note records the
verification that preceded the switch and the residual structural caveats.

An earlier revision of this note attributed the httpx2 migration to
`starlette` 1.4, claimed `starlette>=1.4` silently pulls `httpx2` into
`uv sync`, described the trust anchor as a personal PyPI account, and
recommended pinning `starlette<1.4`. All four claims were wrong; the
corrections are folded into this revision, and the decision history is
recorded under "Decision".

## What changed upstream

The `starlette` test-client migration to `httpx2` happened across two releases
in the first half of 2026, not in 1.4:

- `starlette` 1.2.0 (2026-05-28) — "Support httpx2 in the test client" (#3291).
- `starlette` 1.2.1 (2026-05-31) — use `httpx2` for type checking in the
  testclient module (#3304).
- `starlette` 1.3.0 (2026-06-11) — add `httpx2` to the `full` extra (#3323),
  and adjust testclient typing and warnings (#3322).
- `starlette` 1.3.1 (2026-06-12) — FormParser `max_fields`/`max_part_size`
  enforcement (DoS hardening, unrelated to httpx2).
- `starlette` 1.4.0/1.4.1 (2026-08-05) — GZip middleware changes only
  (threaded compression, `thread_minimum_size` default); nothing to do with
  httpx2.

`httpx2` is an **optional** dependency of `starlette` in every one of these
releases: on PyPI, `httpx2` appears only under the `full` extra, and the
unconditional runtime dependencies are just `anyio` and `typing-extensions`.
`starlette` never pulls `httpx2` (or `httpx`) in by itself.

The testclient in `starlette>=1.2` imports `httpx2` first and falls back to
`httpx` with a deprecation warning when `httpx2` is absent:

    StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is
    deprecated; install `httpx2` instead.

Our `httpx2`/`httpcore2`/`truststore` resolution was originally self-inflicted:
the test extra in `pyproject.toml` declared `httpx2>=2,<3` without evaluation.
PR #27 first removed that declaration in favor of official `httpx`, then, after
the verification below, deliberately switched back to `httpx2` — the difference
being that the current declaration is an audited, documented decision rather
than an accident of dependency resolution.

## What we verified

### Hashes match PyPI (no tampering of what we install)

`starlette 1.4.1`, `fastapi 0.141.1`, and the installed `httpx`/`httpcore`
versions were compared against the PyPI JSON API: sdist and wheel `sha256`
values in `uv.lock` match PyPI exactly, and the installed `starlette` tree is
byte-identical to the official wheel (24/24 files, 0 mismatches). These
packages are authentic PyPI releases, not modified copies.

### `httpx2` is a renamed fork of `httpx`, and the code is clean

`httpx2` 2.9.1 (36 source files) was audited for malicious behavior. None found:

- no `eval`/`exec`/`__import__` dynamic execution;
- no `subprocess`/`os.system`;
- no hard-coded outbound URLs (the seven "telemetry" regex hits are all RFC
  reference comments pointing at `ietf.org`, not beacons);
- no hard-coded certificate-verification bypass;
- environment-variable reads are limited to `SSL_CERT_FILE`/`SSL_CERT_DIR`,
  the standard TLS behavior gated by `trust_env`;
- the only `base64` use is the WebSocket handshake nonce.

Core files are 90–98% textually similar to official `httpx 0.28.1`, confirming
`httpx2` is a renamed fork that adds features (e.g. a `websockets` module)
rather than a hostile rewrite. The current resolution is `httpx2` 2.12.0 with
`httpcore2==2.12.0` (exact pin) and `truststore>=0.10`.

### Stewardship moved from `encode` to the `pydantic` organization

`httpx2`'s PyPI maintainer is "Pydantic Services Inc."
(`engineering@pydantic.dev`); the original `httpx` author (Tom Christie) is
listed as the package author. The stated motivation is that official `httpx`
has been stagnant (no release after 0.28.1 of 2024-12, minimal commits, closed
issues, a large PR backlog), and pydantic took stewardship under the new name
to provide maintenance and timely security updates. This is a corporate
takeover of maintenance, not an anonymous hijack. On balance the stewardship
is now arguably *stronger* than the official package's: an actively resourced
company is releasing timely updates where `encode/httpx` has effectively
stopped.

## Why caution is still warranted

The residual risk is structural, not evidence of malice:

1. **The migration bypassed community process.** There was no RFC, no
   deprecation notice on `httpx` itself, and no documented migration path from
   the old package name. Dependent projects discovered the change through a
   `StarletteDeprecationWarning`.
2. **Concentrated trust anchor.** `httpx2` pins `httpcore2` to an exact
   version (`httpcore2==2.12.0` in current releases) and requires
   `truststore`, so the whole chain (starlette testclient → httpx2 →
   httpcore2 → truststore) resolves to the `pydantic` organization. The
   account is a company, which is better than an unknown individual, but the
   org's Owner role currently has a single member — a smaller trust base than
   the multi-maintainer, community-audited history behind
   `encode/httpx`/`encode/httpcore`.
3. **Renamed-package confusion.** A fork that keeps the API but not the name
   is the shape dependency-confusion attacks take; we verified this
   particular package is benign, but the verification effort itself is the
   cost of the rename.

## Options

| Option | Action | Trade-off |
| --- | --- | --- |
| A. Pin `starlette<1.2` | Cap below the entire httpx2 migration so the fallback import path and warning never exist. | Rejects 1.2+ features; in particular loses the 1.3.1 FormParser `max_fields`/`max_part_size` DoS hardening and the 1.4.x GZip fixes — a real security downgrade to avoid a warning. Not recommended. |
| B. Keep official `httpx` and monitor | Keep `httpx>=0.27,<1` in the test extra; nothing in the dependency set asks starlette for `httpx2` (it's optional), so the chain never resolves. Watch `pydantic/httpx2` releases and diff against upstream `httpx` before any adoption. | Works today, but rides a fallback import path that starlette deprecates and may remove, on top of a transport that has had no release since 2024-12. |
| C. Adopt `httpx2` (current state) | Switch the test extra to `httpx2>=2,<3` to follow starlette's preferred path. | Accepts the renamed-fork chain (httpx2 → httpcore2 → truststore) after audit; relies on the pydantic org's stewardship and its single-member Owner role for continued integrity. |

## Decision

We take **option C**. The audit found no malicious behavior, the steward is a
reputable organization with the original author attached, and starlette's
test client — the only consumer in this repository — treats `httpx2` as the
primary path. Official `httpx` remains functionally identical today, but
choosing it long-term would mean combining a deprecated import path with an
unmaintained transport, which is its own supply-chain liability.

History: the test extra originally declared `httpx2>=2,<3` by accident.
PR #27 first switched to official `httpx` on supply-chain caution (option B)
and an earlier revision of this note recommended pinning `starlette<1.4`;
fact-checking showed that pin would be ineffective (the migration is in
1.2.0/1.3.0, not 1.4) and that the "silent pull-in" concern was unfounded
(`httpx2` is optional for starlette). With those corrected facts, the
deliberate adoption of `httpx2` (this revision) is the same dependency as the
accidental one, but chosen on verified evidence rather than resolver default.

Revisit if `pydantic/httpx2` stewardship changes hands, if `httpx` resumes
active multi-maintainer maintenance under `encode`, or if starlette's
test client gains a third transport option.
