# Agent Skills for Weaver

Guide AI agents and development tools toward useful Weaver capabilities.

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

- [api-conformance](.agents/skills/api-conformance/) - Check OGC standards
- [api-info](.agents/skills/api-info/) - Get API metadata
- [api-version](.agents/skills/api-version/) - Get Weaver version

### CWL Tools

- [cwl-create-commandlinetool](.agents/skills/cwl-create-commandlinetool/)
- [cwl-debug-package](.agents/skills/cwl-debug-package/)
- [cwl-optimize-performance](.agents/skills/cwl-optimize-performance/)
- [cwl-understand-builtin](.agents/skills/cwl-understand-builtin/)
- [cwl-understand-docker](.agents/skills/cwl-understand-docker/)
- [cwl-understand-workflow](.agents/skills/cwl-understand-workflow/)
- [cwl-use-expressions](.agents/skills/cwl-use-expressions/)
- [cwl-validate-package](.agents/skills/cwl-validate-package/)

### Job Operations

- [job-dismiss](.agents/skills/job-dismiss/)
- [job-exceptions](.agents/skills/job-exceptions/)
- [job-execute](.agents/skills/job-execute/)
- [job-inputs](.agents/skills/job-inputs/)
- [job-list](.agents/skills/job-list/)
- [job-logs](.agents/skills/job-logs/)
- [job-monitor](.agents/skills/job-monitor/)
- [job-provenance](.agents/skills/job-provenance/)
- [job-results](.agents/skills/job-results/)
- [job-statistics](.agents/skills/job-statistics/)
- [job-status](.agents/skills/job-status/)

### Process Management

- [process-deploy](.agents/skills/process-deploy/)
- [process-describe](.agents/skills/process-describe/)
- [process-list](.agents/skills/process-list/)
- [process-package](.agents/skills/process-package/)
- [process-undeploy](.agents/skills/process-undeploy/)

### Provider Management

- [provider-list](.agents/skills/provider-list/)
- [provider-register](.agents/skills/provider-register/)
- [provider-unregister](.agents/skills/provider-unregister/)

### Setup & Maintenance

- [weaver-install](.agents/skills/weaver-install/)
- [weaver-skill-create](.agents/skills/weaver-skill-create/) - How to create skills
- [weaver-skills-update](.agents/skills/weaver-skills-update/)

### Vault

- [vault-upload](.agents/skills/vault-upload/)

## Learn More

- **Complete Skill Reference**: [.agents/README.md](.agents/README.md)
- **How to Create Skills**: [weaver-skill-create](.agents/skills/weaver-skill-create/)
- **Agent Skills Specification**: <https://agentskills.io/specification>
- **Weaver Documentation**: <https://pavics-weaver.readthedocs.io/>











