---
name: weaver-ci-validate
description: |
  Run Weaver code test and lint validations through Makefile targets.
  Prefer `make check*` and `make test*` commands over direct tool calls to stay
  aligned with project CI behavior and environment setup.
license: Apache-2.0
compatibility: Requires Make, Python environment dependencies, and Weaver repository access.
metadata:
  category: setup-operations
  version: "1.0.0"
  keywords:
    - makefile
    - lint
    - tests
    - validation
    - ci
  author: fmigneault
---

# Validate Tests and Lint with Makefile

Guide validation tasks toward `Makefile` targets for consistent local and CI checks.

## When to Use

- Before opening a pull request.
- After modifying Python modules, tests, docs, or configuration.
- When investigating lint failures reported by CI.
- When selecting focused checks to reduce local turnaround time.

## Core Rule

Use `make` targets first. Do not call `pytest`, `pylint`, `flake8`, or related tools directly unless a `Makefile`
target does not exist for the needed scope.

## Validation Workflow

1. Run a focused target for the area you changed.
2. If needed, run broader lint checks.
3. Run aggregate `-only` targets to mirror broader validation without triggering install steps.

## Recommended Targets

### Lint and Style

```shell
make check-only
make check-lint-only
make check-pep8-only
make check-imports-only
make check-docstring-only
make check-docf-only
make check-fstring-only
make check-security-only
make check-security-code-only
make check-security-deps-only
make check-doc8-only
make check-dist-doc-only
make check-links-only
make check-css-only
make check-md-only
```

`make check-only` runs all enabled check families through their `-only` variants.

### Test Suites

```shell
make test-only
make test-unit-only
make test-func-only
make test-cli-only
make test-workflow-only
make test-online-only
make test-offline-only
make test-no-tb14-only
make test-code-sprint-only
make test-spec-only SPEC='pattern'
make test-coverage-only
```

`make test-only` runs all tests with no dependency-install pre-step.

## Pytest Marker Patterns

The marker registry is defined in `setup.cfg` under `[tool:pytest]`.

### Predefined markers

- `cli`
- `code_sprint`
- `testbed14`
- `functional`
- `server`
- `quotation`
- `workflow`
- `online`
- `slow`
- `remote`
- `builtin`
- `vault`
- `format`
- `html`
- `prov`
- `kvp`
- `oap_part1`
- `oap_part2`
- `oap_part3`
- `oap_part4`
- `openeo`
- `wps`

### Predefined make target patterns

These wrap common marker expressions:

- `test-unit-only` -> `-m "not slow and not online and not functional"`
- `test-func-only` -> `-m "functional and not code_sprint"`
- `test-cli-only` -> `-m "cli"`
- `test-workflow-only` -> `-m "workflow"`
- `test-online-only` -> `-m "online"`
- `test-offline-only` -> `-m "not online"`
- `test-no-tb14-only` -> `-m "not testbed14"`
- `test-code-sprint-only` -> `-m "code_sprint"`

### Flexible marker expressions

Use `TEST_XARGS` to append custom pytest expressions while still using `make`:

```shell
make test-unit-only TEST_XARGS='-m "oap_part1 and functional and not remote"'
make test-func-only TEST_XARGS='-m "(workflow or quotation) and not slow"'
make test-offline-only TEST_XARGS='-m "vault and not online and not remote"'
```

## Specific Test Selection Examples

Select a specific file while keeping a make target wrapper:

```shell
make test-unit-only TEST_XARGS='tests/functional/code_sprint/test_server.py'
```

Select one test function in a file:

```shell
make test-unit-only TEST_XARGS='tests/functional/code_sprint/test_server.py -k test_landing_page_links'
```

Select tests by substring expression only:

```shell
make test-spec-only SPEC='landing_page and conformance'
```

## Target Discovery

```shell
make help
make check-info
```

Use these to discover current targets and any `CHECKS_EXCLUDE` behavior.

## Notes and Constraints

- Prefer scoped targets first to keep feedback fast.
- Use `test-code-sprint-only` only when required environment variables (for example `TEST_SERVER`) are defined.
- Default pytest options in `setup.cfg` already apply `-m "not online and not remote"` unless overridden.
- Keep validation commands consistent with `Makefile` to preserve CI parity.

## Related Skills

- [weaver-install](../weaver-install/) - Setup dependencies and local environment.
- [weaver-skills-update](../weaver-skills-update/) - Maintain skills when Makefile targets evolve.




