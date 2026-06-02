# Agent Skills for Weaver

Guide AI agents and development tools toward useful Weaver capabilities.

## Boundaries

| Area                 | Constraint                                                                                                              |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Scope                | Use skills in [`.agents/skills/`](.agents/skills/) for Weaver development, testing, packaging, and API work.            |
| Out of Scope         | Do not perform unrelated system administration, modify external repositories, or change files outside this workspace.   |
| Destructive Actions  | Do not delete files, drop databases, undeploy production processes, or overwrite user data unless explicitly requested. |
| Secrets and Security | Never expose credentials, tokens, private keys, or sensitive environment values in logs, outputs, or generated files.   |
| Execution Limits     | Prefer targeted commands and scoped checks; avoid long-running/background operations unless requested and monitored.    |
| Change Control       | Avoid broad refactors or dependency upgrades unless explicitly requested; keep edits minimal and task-focused.          |
| Validation           | Verify changes with the smallest relevant lint/test command before completion when feasible.                            |

## Quick Navigation

Skills are defined in the [`.agents/`](.agents/) directory.
See [.agents/README.md](.agents/README.md) for general information on the Agent Skills framework, or directly
refer to the specific skill documentation in respective directories under [`.agents/skills/`](.agents/skills/).

| Location | Purpose |
| --- | --- |
| **[.agents/README.md](.agents/README.md)** | Complete skills reference with full catalog |
| **[.agents/skills/](.agents/skills/)** | All skill definitions organized by domain as shown below |

## Project Directory Structure

| Directory | Purpose |
| --- | --- |
| **[.agents/](.agents/)** | Agent Skills framework and skill definitions |
| **[weaver/](weaver/)** | Core Python implementation (CLI, API, processes, utilities) |
| **[docs/](docs/)** | Sphinx documentation source and build |
| **[tests/](tests/)** | Test suite (pytest) |
| **[config/](config/)** | Configuration templates and examples |
| **[docker/](docker/)** | Docker build files and container orchestration |
| **[.github/](.github/)** | GitHub workflows, issue templates, PR templates |

### Root-Level Files

| File | Purpose |
| --- | --- |
| **[README.rst](README.rst)** | Project overview and quick start |
| **[AGENTS.md](AGENTS.md)** | This file - Agent Skills navigation |
| **[setup.py](setup.py)** | Python package configuration |
| **[Makefile](Makefile)** | Build automation and development tasks |
| **[setup.cfg](setup.cfg)** | Package metadata and build settings |
| **[SECURITY.md](SECURITY.md)** | Security policy |
| **[CHANGES.rst](CHANGES.rst)** | Changelog and release notes |
| **[AUTHORS.rst](AUTHORS.rst)** | Project contributors |
| **[LICENSE.txt](LICENSE.txt)** | Apache 2.0 License |

## Skill Categories

Complete skill catalog organized by domain:

### API Information

- [api-conformance](.agents/skills/api-conformance/SKILL.md) - Check OGC standards
- [api-info](.agents/skills/api-info/SKILL.md) - Get API metadata
- [api-version](.agents/skills/api-version/SKILL.md) - Get Weaver version

### CWL Tools

- [cwl-create-commandlinetool](.agents/skills/cwl-create-commandlinetool/SKILL.md)
- [cwl-debug-package](.agents/skills/cwl-debug-package/SKILL.md)
- [cwl-optimize-performance](.agents/skills/cwl-optimize-performance/SKILL.md)
- [cwl-understand-builtin](.agents/skills/cwl-understand-builtin/SKILL.md)
- [cwl-understand-docker](.agents/skills/cwl-understand-docker/SKILL.md)
- [cwl-understand-workflow](.agents/skills/cwl-understand-workflow/SKILL.md)
- [cwl-use-expressions](.agents/skills/cwl-use-expressions/SKILL.md)
- [cwl-validate-package](.agents/skills/cwl-validate-package/SKILL.md)

### Job Operations

- [job-dismiss](.agents/skills/job-dismiss/SKILL.md)
- [job-exceptions](.agents/skills/job-exceptions/SKILL.md)
- [job-execute](.agents/skills/job-execute/SKILL.md)
- [job-inputs](.agents/skills/job-inputs/SKILL.md)
- [job-list](.agents/skills/job-list/SKILL.md)
- [job-logs](.agents/skills/job-logs/SKILL.md)
- [job-monitor](.agents/skills/job-monitor/SKILL.md)
- [job-provenance](.agents/skills/job-provenance/SKILL.md)
- [job-results](.agents/skills/job-results/SKILL.md)
- [job-statistics](.agents/skills/job-statistics/SKILL.md)
- [job-status](.agents/skills/job-status/SKILL.md)

### Process Management

- [process-deploy](.agents/skills/process-deploy/SKILL.md)
- [process-describe](.agents/skills/process-describe/SKILL.md)
- [process-list](.agents/skills/process-list/SKILL.md)
- [process-package](.agents/skills/process-package/SKILL.md)
- [process-undeploy](.agents/skills/process-undeploy/SKILL.md)

### Provider Management

- [provider-list](.agents/skills/provider-list/SKILL.md)
- [provider-register](.agents/skills/provider-register/SKILL.md)
- [provider-unregister](.agents/skills/provider-unregister/SKILL.md)

### Setup & Maintenance

- [weaver-install](.agents/skills/weaver-install/SKILL.md) - Install Weaver and its dependencies
- [weaver-ci-validate](.agents/skills/weaver-ci-validate/SKILL.md) - Run tests, lint checks and fixes with Makefile
  targets
- [weaver-skill-create](.agents/skills/weaver-skill-create/SKILL.md) - How to create Agent Skills for Weaver
  codebase
- [weaver-skills-update](.agents/skills/weaver-skills-update/SKILL.md) - Update Agent Skills related to Weaver
  or its codebase

### Vault

- [vault-upload](.agents/skills/vault-upload/SKILL.md)

## Learn More

- **Complete Skill Reference**: [.agents/README.md](.agents/README.md)
- **How to Create Skills**: [weaver-skill-create](.agents/skills/weaver-skill-create/SKILL.md)
- **Agent Skills Specification**: <https://agentskills.io/specification>
- **Weaver Documentation**: <https://pavics-weaver.readthedocs.io/>











