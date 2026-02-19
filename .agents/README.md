# Weaver Agent Skills

This directory contains [Agent Skills](https://agentskills.io/) - a standardized format for describing capabilities that can be discovered and used by AI agents, IDEs, and automated systems.

## What are Agent Skills?

Agent Skills provide a structured way to document and expose Weaver's capabilities in a format that LLMs and AI agents can easily understand and utilize. Each skill is self-contained with:

- **Frontmatter metadata** (YAML) describing the skill
- **Markdown documentation** explaining usage
- **Optional supporting files** (scripts, references, assets)

## Directory Structure

```
.agents/
└── skills/
    ├── deploy-process/
    │   └── SKILL.md
    ├── execute-process/
    │   └── SKILL.md
    ├── monitor-job/
    │   └── SKILL.md
    └── ...
```

## Available Skills

All 33 skills are now organized by category for easy discovery:

### API Information (3 skills)
- **[api-conformance](skills/api-conformance/)** - Check OGC standards conformance
- **[api-info](skills/api-info/)** - Get API metadata and endpoints
- **[api-version](skills/api-version/)** - Get Weaver version information

### CWL Comprehension (8 skills)
- **[cwl-create-commandlinetool](skills/cwl-create-commandlinetool/)** - Create CWL CommandLineTool packages from scratch
- **[cwl-debug-package](skills/cwl-debug-package/)** - Debug CWL package deployment and execution issues
- **[cwl-optimize-performance](skills/cwl-optimize-performance/)** - Optimize CWL performance and resource usage
- **[cwl-understand-builtin](skills/cwl-understand-builtin/)** - Use Weaver's built-in utility processes
- **[cwl-understand-docker](skills/cwl-understand-docker/)** - Master Docker requirements in CWL packages
- **[cwl-understand-workflow](skills/cwl-understand-workflow/)** - Create multi-step CWL workflows
- **[cwl-use-expressions](skills/cwl-use-expressions/)** - Use JavaScript expressions for dynamic behavior
- **[cwl-validate-package](skills/cwl-validate-package/)** - Validate CWL syntax before deployment

### Job Operations (11 skills)
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

### Process Management (5 skills)
- **[process-deploy](skills/process-deploy/)** - Deploy CWL application packages
- **[process-describe](skills/process-describe/)** - Get process details and capabilities
- **[process-get-package](skills/process-get-package/)** - Retrieve CWL package definitions
- **[process-list](skills/process-list/)** - Discover available processes
- **[process-undeploy](skills/process-undeploy/)** - Remove deployed processes

### Provider Management (3 skills)
- **[provider-list](skills/provider-list/)** - List all registered providers
- **[provider-register](skills/provider-register/)** - Register remote WPS/OGC services
- **[provider-unregister](skills/provider-unregister/)** - Remove provider registrations

### Setup Operations (2 skills)
- **[weaver-install](skills/weaver-install/)** - Install and configure Weaver (Docker or from source)
- **[weaver-skills-update](skills/weaver-skills-update/)** - Maintain and update skills documentation

### Vault Operations (1 skill)
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

**PyCharm / JetBrains**:
Add to `~/.config/github-copilot/intellij/mcp.json`:
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

**VS Code**:
Add to `.vscode/settings.json`:
```json
{
  "github.copilot.advanced": {
    "contextFiles": [
      "${workspaceFolder}/.agents/skills/**/*.md"
    ]
  }
}
```

### For Developers

1. **Browse skills**: Each skill directory contains complete documentation
2. **Follow examples**: Code examples show CLI, Python, and API usage
3. **Check compatibility**: Frontmatter lists requirements and dependencies

## Skill Metadata

Each SKILL.md file contains YAML frontmatter with:

```yaml
---
name: skill-name                # Unique identifier
description: What it does       # Clear description with keywords
license: Apache-2.0             # License information
compatibility: Requirements     # Environment/system requirements
metadata:                        # Additional metadata
  category: process-management
  version: "1.0.0"
  api_endpoint: GET /endpoint
  cli_command: weaver command
  author: CRIM
allowed-tools: tools it can use # Pre-approved tool access
---
```

## Creating New Skills

When adding new Weaver capabilities:

1. Create a new directory: `.agents/skills/my-new-skill/`
2. Add `SKILL.md` with proper frontmatter
3. Include usage examples (CLI, Python, API)
4. Document parameters and return values
5. Link to related skills
6. Reference official documentation

### Skill Naming

- Use lowercase with hyphens: `my-skill-name`
- Be descriptive but concise
- Match directory name to skill name

### Description Guidelines

- Start with what the skill does
- Include when to use it
- Add specific keywords for discoverability
- Keep under 1024 characters

## Spec Compliance

These skills follow the [Agent Skills Specification](https://agentskills.io/specification):

- ✅ Proper directory structure
- ✅ YAML frontmatter with required fields
- ✅ Markdown body content
- ✅ Progressive disclosure (simple to detailed)
- ✅ Machine-readable and human-friendly

## Additional Resources

- **Main Documentation**: [SKILLS.md](../../SKILLS.md) - Legacy format, comprehensive reference
- **IDE Integration**: [IDE_INTEGRATION.md](../../IDE_INTEGRATION.md) - Setup instructions
- **Weaver Docs**: https://pavics-weaver.readthedocs.io/
- **Agent Skills Spec**: https://agentskills.io/specification

## Validation

Validate skills against the spec:

```bash
# If agent skills validator is available
agentskills validate .agents/skills/
```

## Support

- **Issues**: https://github.com/crim-ca/weaver/issues
- **Discussions**: https://github.com/crim-ca/weaver/discussions
- **Documentation**: https://pavics-weaver.readthedocs.io/

## License

Apache License 2.0 - See LICENSE.txt for details

Copyright © 2020-2026, CRIM
