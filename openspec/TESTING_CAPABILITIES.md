# Testing Capabilities — easypunto_parkos

> Persisted per sdd-init Hard Rules. Update when a test runner lands.

**Strict TDD Mode**: disabled
**Detected**: 2026-08-30

## Test Runner

- Command: — (no runner)
- Framework: — (no framework)

## Test Layers

| Layer | Available | Tool |
|-------|-----------|------|
| Unit | ❌ | — |
| Integration | ❌ | — |
| E2E | ❌ | — |

## Coverage

- Available: ❌
- Command: —

## Quality Tools

| Tool | Available | Command |
|------|-----------|---------|
| Linter | ❌ | — |
| Type checker | ❌ | — |
| Formatter | ❌ | — |

## Strict TDD Reasoning

`strict_tdd: false` because **no test runner is detected** (no `pyproject.toml`, `package.json`, `pytest.ini`, `go.mod`, etc.). Per the sdd-init Decision Gates:

> no test runner → Set `strict_tdd: false` and explain unavailable.

## How to Re-Enable Strict TDD

1. Add a test runner (planned: `pytest` + `pytest-asyncio` for backend; `vitest` + RTL for frontend).
2. Re-run `sdd-init` to refresh testing capabilities.
3. Or use `/sdd-qa-plan` on a per-change basis to enforce TDD for that change.
