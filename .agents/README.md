# Weaver Agent Skills

This directory contains [Agent Skills](https://agentskills.io/) - a standardized format for describing capabilities that
can be discovered and used by AI agents, IDEs, and automated systems.

## What are Agent Skills?

Agent Skills provide a structured way to document and expose Weaver's capabilities in a format that LLMs and AI agents
can easily understand and utilize. Each skill is self-contained with:

- **Frontmatter metadata** (YAML) describing the skill
- **Markdown documentation** explaining usage
- **Optional supporting files** (scripts, references, assets)

## Directory Structure

```
.agents/
└── skills/
    ├── weaver-skill-create/
    │   └── SKILL.md
    ├── process-deploy/
    │   └── SKILL.md
    ├── job-monitor/
    │   └── SKILL.md
    └── ...
```

## Project Structure & Skill Integration

For a complete overview of the Weaver project structure and how Agent Skills integrate with the codebase, see [/AGENTS.md](/AGENTS.md).

### Quick Reference: Skills to Code Mapping

| Skill Category                        | Code Location         | Interface          |
|---------------------------------------|-----------------------|--------------------|
| **job-**, **process-**, **provider-** | `weaver/cli.py`       | CLI commands       |
| **API skills**                        | `weaver/wps_restapi/` | REST endpoints     |
| **process-**                          | `weaver/processes/`   | Process operations |
| **cwl-**                              | `weaver/`             | CWL support        |

## Available Skills

All skills are organized by category for easy discovery:

### API Information

- **[api-conformance](skills/api-conformance/)** - Check OGC standards conformance
- **[api-info](skills/api-info/)** - Get API metadata and endpoints
- **[api-version](skills/api-version/)** - Get Weaver version information

### CWL Comprehension

- **[cwl-create-commandlinetool](skills/cwl-create-commandlinetool/)** - Create CWL CommandLineTool packages from
  scratch
- **[cwl-debug-package](skills/cwl-debug-package/)** - Debug CWL package deployment and execution issues
- **[cwl-optimize-performance](skills/cwl-optimize-performance/)** - Optimize CWL performance and resource usage
- **[cwl-understand-builtin](skills/cwl-understand-builtin/)** - Use Weaver's built-in utility processes
- **[cwl-understand-docker](skills/cwl-understand-docker/)** - Master Docker requirements in CWL packages
- **[cwl-understand-workflow](skills/cwl-understand-workflow/)** - Create multi-step CWL workflows
- **[cwl-use-expressions](skills/cwl-use-expressions/)** - Use JavaScript expressions for dynamic behavior
- **[cwl-validate-package](skills/cwl-validate-package/)** - Validate CWL syntax before deployment

### Job Operations

- **[job-dismiss](skills/job-dismiss/)** - Cancel running or pending jobs
- **[job-exceptions](skills/job-exceptions/)** - Get detailed error information
- **[job-execute](skills/job-execute/)** - Run processes with inputs (async/sync)
- **[job-inputs](skills/job-inputs/)** - Retrieve job input parameters
- **[job-list](skills/job-list/)** - List jobs with filtering and pagination
- **[job-logs](skills/job-logs/)** - View execution logs for debugging
- **[job-monitor](skills/job-monitor/)** - Wait for job completion with polling
- **[job-provenance](skills/job-provenance/)** - Get W3C PROV lineage metadata
- **[job-results](skills/job-results/)** - Retrieve output results
- **[job-statistics](skills/job-statistics/)** - Retrieve resource usage metrics
- **[job-status](skills/job-status/)** - Check job execution status

### Process Management

- **[process-deploy](skills/process-deploy/)** - Deploy CWL application packages
- **[process-describe](skills/process-describe/)** - Get process details and capabilities
- **[process-get-package](skills/process-get-package/)** - Retrieve CWL package definitions
- **[process-list](skills/process-list/)** - Discover available processes
- **[process-undeploy](skills/process-undeploy/)** - Remove deployed processes

### Provider Management

- **[provider-list](skills/provider-list/)** - List all registered providers
- **[provider-register](skills/provider-register/)** - Register remote WPS/OGC services
- **[provider-unregister](skills/provider-unregister/)** - Remove provider registrations

### Setup Operations

- **[weaver-install](skills/weaver-install/)** - Install and configure Weaver (Docker or from source)
- **[weaver-ci-validate](skills/weaver-ci-validate/)** - Run code test and lint checks with Makefile targets
- **[weaver-skill-create](skills/weaver-skill-create/)** - Create new Agent Skills
- **[weaver-skills-update](skills/weaver-skills-update/)** - Maintain and update skills documentation

### Vault Operations

- **[vault-upload](skills/vault-upload/)** - Store sensitive data securely

## Using These Skills

### For AI Agents

AI agents can read the SKILL.md files to understand:

1. When to use each capability
2. What parameters are required
3. How to format requests
4. What to expect in responses

### For IDEs (PyCharm, VS Code)

Configure your IDE to recognize these skills for autocomplete and suggestions:

**PyCharm / JetBrains**: Add to `~/.config/github-copilot/intellij/mcp.json`:

```json
{
  "servers": {
    "weaver": {
      "type": "filesystem",
      "path": "/path/to/weaver/.agents/skills"
    }
  }
}
```

**VS Code**: Add to `.vscode/settings.json`:

```json
{
  "github.copilot.advanced": {
    "contextFiles": [
      "${workspaceFolder}/.agents/skills/**/*.md"
    ]
  }
}
```

## Creating New Skills

For detailed guidance on creating new Agent Skills, see [weaver-skill-create](skills/weaver-skill-create/SKILL.md).
This includes naming conventions, metadata requirements, structure, examples, and best practices.

## Skill Metadata

Each SKILL.md file contains YAML frontmatter with metadata. For complete metadata documentation and best practices,
see [weaver-skill-create](skills/weaver-skill-create/SKILL.md).

## Additional Resources

- **Weaver Docs**: [https://pavics-weaver.readthedocs.io/](https://pavics-weaver.readthedocs.io/)
- **Agent Skills Spec**: [https://agentskills.io/specification](https://agentskills.io/specification)

## Support

- **Issues**: [https://github.com/crim-ca/weaver/issues](https://github.com/crim-ca/weaver/issues)
- **Discussions**: [https://github.com/crim-ca/weaver/discussions](https://github.com/crim-ca/weaver/discussions)
- **Documentation**: [https://pavics-weaver.readthedocs.io/](https://pavics-weaver.readthedocs.io/)
