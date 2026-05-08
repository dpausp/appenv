---
lifecycle:
  requirements:
    completed_at: "2026-05-08T18:00:00+02:00"
    git_rev: "d0418d6"
  design:
    completed_at: "2026-05-08T19:00:00+02:00"
    git_rev: "d0418d6"
  plan:
  workflow:
  verify:
---

# docs-e2e-alignment

## Context

E2E tests and user documentation are misaligned. User docs list 3 UV discovery steps (code has 6), the recommended "download + init" workflow has no E2E coverage, and architecture.md misses the astral.sh direct-download step. Target state: every documented workflow has E2E coverage ("tested docs").

## Decisions

### init-e2e-coverage

#### Context

The recommended workflow in user docs is "download appenv + ./appenv init" but no E2E test exercises `./appenv init`. Four of five E2E jobs bypass init with manual pyproject.toml heredocs.

#### Decision

Adapt `debian-bookworm-pip` E2E job to use `./appenv init` via printf pipe instead of manual heredoc. The job already has pip installed (tests discovery step 5), so init adds coverage without a new CI job.

#### Alternatives

a. New dedicated E2E job — cleaner but adds CI minutes
b. Keep all tests as-is — no init coverage

#### Consequences

`debian-bookworm-pip` tests both pip discovery AND init command. Other four jobs stay unchanged (test specific discovery paths). Init uses `printf 'http\nhttpie\n\n\n\n3.12\n' | ./appenv init` — same approach as existing `ubuntu-uvx` job.

### python39-e2e

#### Context

Real-world scenario: users on older systems have Python 3.9 as default. Code claims `>=3.9` support but no E2E test covers this. httpie requires `>=3.7` so it works on 3.9.

#### Decision

Add `debian-bullseye-39` E2E job using `debian:bullseye` container (Python 3.9 as system default). Full E2E scope: printf-pipe init + update-lockfile + ./http --version. Uses `requires-python = ">=3.9"`.

#### Alternatives

a. Bullseye + source-compiled python3.10 for version mismatch — ~2min CI overhead, fragile
b. Ubuntu 20.04 + deadsnakes — not a Debian scenario

#### Consequences

Minimum Python version gets E2E coverage. No version mismatch test (system 3.9 vs project >=3.10) — that's a separate concern.

### discovery-docs-tiered

#### Context

User docs (`installation.md`) list 3 discovery steps but code has 6 (PATH, cached, nix-channel, nix-flake, pip, direct-download). architecture.md lists 5, missing step 6 (astral.sh direct-download).

#### Decision

Two-tier documentation: user docs stay brief (mention PATH, pip, "auto-download" with link to architecture.md). architecture.md gets updated to list all 6 steps. User docs add "or will be installed automatically" phrasing for the astral.sh download.

#### Alternatives

a. All 6 steps in user docs — overwhelming for users
b. Only "uv is auto-installed" — too vague

#### Consequences

architecture.md is the authoritative source for the full discovery chain. User docs give the 90% case with dev-docs link.

### platform-detection-docs

#### Context

The platform triple logic (`_uv_platform_triple`) maps machine+OS to UV release archives. Alpine (musl), macOS (darwin), and minimal Debian E2E jobs depend on this. Currently undocumented.

#### Decision

Add "Platform Detection" section to architecture.md with triple mapping table. Placed as subsection of "uv Management" since `_uv_platform_triple()` is used by the installer fallback.

#### Alternatives

a. Code comments only — scattered knowledge, harder to find

#### Consequences

Single authoritative source for platform triples. Developers adding architectures know where to look.

### test-strategy

#### Context

This work changes YAML workflows and documentation. No new Python code.

#### Decision

E2E-only testing. The E2E jobs in `.github/workflows/e2e.yml` ARE the tests. No unit tests needed since no Python code changes.

#### Alternatives

a. Unit tests for init pipe behavior — init code is unchanged, only the E2E invocation changes

#### Consequences

Test coverage is the E2E workflow itself. Six E2E jobs after completion: debian-bookworm-pip (init + pip), debian-bookworm-minimal (direct-download), ubuntu-uvx (uvx+init), alpine-musl (musl triple), macos-arm64 (darwin triple), debian-bullseye-39 (Python 3.9 minimum).

## Requirements

- `debian-bookworm-pip` job must use `printf` pipe to `./appenv init` instead of heredoc pyproject.toml
- `debian-bullseye-39` job: `debian:bullseye` container, `apt-get install python3 python3-pip ca-certificates`, full E2E with `requires-python >= ">=3.9"`, printf-pipe init with `3.9` as python version answer
- `installation.md` UV section: add "or will be downloaded automatically from astral.sh" phrasing with link to `architecture.md`
- `architecture.md` "uv Management" section: update from 5 to 6 steps, add "Platform Detection" subsection with triple table (x86_64/aarch64/armv7 × gnu/musl/darwin)
- All E2E jobs keep `APPENV_VERBOSE: "1"` env and `./appenv version` + `python3 --version` info display
