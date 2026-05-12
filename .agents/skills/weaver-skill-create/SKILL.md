---
name: weaver-create-skill
description: |
  Create new Agent Skills for Weaver capabilities. Learn skill structure, naming conventions,
  metadata requirements, and best practices for documenting new capabilities.
license: Apache-2.0
compatibility: Requires understanding of Weaver architecture and Agent Skills specification.
metadata:
  category: setup-operations
  version: "1.0.0"
  keywords:
    - skill-development
    - documentation
    - agent-skills
    - capability-exposure
  author: CRIM
---

# Create New Agent Skills

Learn to create new Agent Skills for Weaver capabilities in the standardized Agent Skills format.

## When to Use

- Adding new Weaver capabilities to the skill library
- Documenting LLM-accessible workflows
- Exposing functionality to AI agents and IDEs
- Creating reusable skill templates
- Contributing to the Weaver skill ecosystem

## Skill Directory Structure

All skills follow this standard structure:

```
.agents/
└── skills/
    └── my-new-skill/
        ├── SKILL.md              (required)
        ├── scripts/              (optional)
        │   ├── example.py
        │   └── example.sh
        └── assets/               (optional)
            └── diagram.png
```

## Skill Naming Conventions

Skill names follow a two-part pattern depending on their purpose:

### Repository/Code Management Skills

Skills that manage the repository, installation, or skill infrastructure use
the **`weaver-<component>-<action>`** pattern:

- **weaver**: Prefix to identify repository/infrastructure management
- **component**: The target domain (e.g., `skill`, `install`)
- **action**: The operation (e.g., `create`, `update`)

✓ Examples:
- `weaver-skill-create` - Create new Agent Skills
- `weaver-skills-update` - Update skill documentation
- `weaver-install` - Install Weaver

In a sense, these are "meta-skills" that manage the skill ecosystem itself.
The `"weaver-<component>"` is iself the *component* and the `<action>` is the specific operation on that component.

### Operational Skills

Skills that perform operations using Weaver or other tools relevant to it simply describe what they do,
**without** the `weaver-` prefix:

- **component**: The domain or object (e.g., `job`, `process`, `cwl`, `api`)
- **action**: The operation (e.g., `deploy`, `monitor`, `validate`)

✓ Examples:
- `job-monitor` - Monitor job execution
- `process-deploy` - Deploy processes
- `cwl-validate-package` - Validate CWL packages
- `api-version` - Get API version information

### Naming Rules

- Use **lowercase with hyphens** (never underscores)
- Be **descriptive but concise**
- Match directory name to skill name exactly
- Use `weaver-` prefix **only** for repository/infrastructure management skills

## SKILL.md Frontmatter

Every SKILL.md must start with YAML frontmatter:

```yaml
---
name: skill-name                    # Unique identifier (matches directory)
description: |                      # Multi-line description with keywords
  Clear description of what it does.
  Include keywords for AI discoverability.
license: Apache-2.0                 # License information
compatibility: Requirements         # Environment/system requirements
metadata:
  category: category-name           # e.g., job-operations, process-management
  version: "1.0.0"                  # Skill version
  keywords:                         # Search keywords
    - keyword1
    - keyword2
  author: CRIM                       # Original author
---
```

### Metadata Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | Yes | Unique skill identifier (lowercase, hyphens) |
| `description` | string | Yes | Clear description with keywords (max 1024 chars) |
| `license` | string | Yes | License type (e.g., Apache-2.0) |
| `compatibility` | string | Yes | System/environment requirements |
| `metadata.category` | string | Yes | Skill category for organization |
| `metadata.version` | string | Yes | Skill version (semantic versioning) |
| `metadata.keywords` | array | Yes | Search keywords for discovery |
| `metadata.author` | string | Yes | Author/maintainer name |

The metadata fields must respect the [Agent Skills Specification](https://agentskills.io/specification).

## Description Guidelines

Effective skill descriptions should:

- **Start with the action**: "Deploy processes", "Monitor jobs", "Validate packages"
- **Include use cases**: When and why to use this skill
- **Add keywords**: For AI agent discovery
- **Keep concise**: Under 1024 characters
- **Avoid redundancy**: Don't repeat operations that can be performed by other skills
- **Avoid ambiguity**: Be specific about what the skill does

Examples:

✓ Good: "Deploy CWL application packages to Weaver. Use for registering new processes."

✗ Poor: "This skill is used to deploy CWL packages to Weaver using deployment."

## Content Structure

After frontmatter, structure SKILL.md as follows.
Sections that are not applicable can be omitted, but should be provided if available to offer alternatives.

````markdown
# Skill Title

One-line summary of the capability.

## When to Use

- Use case 1
- Use case 2
- Use case 3

## Parameters

- **param_name** (type): Description
- **param_name** (type): Optional description

## CLI Usage

```bash
# Example command
command --flag value
```

## Python Usage

```python
from weaver.client import WeaverClient

client = WeaverClient(url="...")
result = client.method()
```

## API Request

```bash
curl -X GET \
  "${WEAVER_URL}/endpoint"
```

## Returns

JSON structure or response format.

## Limitations

- Issue 1: Solution
- Issue 2: Cause and workaround

## Related Skills

- [related-skill](../related-skill/): Brief description of how it relates
- [other-skill](../other-skill/): Brief description of how it relates

## References

- [Documentation](https://link-to-docs)
````

## Best Practices

1. **Keep it focused**: One skill = one primary capability
2. **Include examples**: Provide CLI, Python, and API examples
3. **Document parameters**: Every input should be documented with type and purpose
4. **Add use cases**: Help LLMs understand when to invoke this skill
5. **Link related skills**: Create navigable skill graphs
6. **Use clear language**: Avoid jargon; be explicit about requirements
7. **Test examples**: Ensure code examples actually work
8. **Update metadata keywords**: These enable AI agent discovery
9. **Provide skils**: Link to related skills, but only if actually relevant and specific to the skill being documented
10. **Provide references**: Link to documentation and specifications if needd for better understanding or context

## Step-by-Step Creation

### 1. Create Directory

```bash
mkdir -p .agents/skills/my-new-skill
cd .agents/skills/my-new-skill
```

### 2. Create SKILL.md

```bash
cat > SKILL.md << 'EOF'
---
name: my-new-skill
description: |
  What this skill does in one clear sentence.
license: Apache-2.0
compatibility: Requirements here.
metadata:
  category: operation-type
  version: "1.0.0"
  keywords:
    - keyword1
    - keyword2
  author: CRIM
---

# Skill Title

Content here...
EOF
```

### 3. Add Usage Examples

Include at least three usage methods:
- CLI examples with commands and flags
- Python code with imports and method calls
- Raw API requests with curl or HTTP

### 4. Document Parameters

List all inputs with:
- Parameter name and type
- Description
- Default value (if applicable)
- Example values

### 5. Document Returns

Show what the skill returns:
- Success response format
- Error response format
- Example output

### 6. Test Documentation

Verify:
- [ ] All examples are syntactically correct
- [ ] Parameters are clearly documented
- [ ] Return values match actual API responses
- [ ] Links to related skills work
- [ ] Metadata keywords enable discovery

### 7. Update Catalogs

After creating a skill, update the following files to include cross-references.
Note that file references are from the root of the repository.

- **[AGENTS.md](/AGENTS.md)** - Add skill to appropriate category
- **[.agents/README.md](../)** - Add skill to appropriate category with description

## Validation Checklist

Before considering a skill complete:

- [ ] Directory name matches skill name (lowercase, hyphens)
- [ ] SKILL.md has complete frontmatter
- [ ] All required metadata fields present
- [ ] Description includes keywords for AI discovery
- [ ] At least 3 usage examples (CLI, Python, API)
- [ ] Parameters clearly documented with types
- [ ] Return values documented
- [ ] Links to related skills included
- [ ] Line length ≤ 120 characters
- [ ] No escaped underscores (`\_` → `_`)
- [ ] YAML frontmatter is syntactically valid
- [ ] All code examples tested

## Related Skills

- [weaver-skills-update](../weaver-skills-update/) - Maintain and update skills documentation after creation

## References

- **Agent Skills Specification**: <https://agentskills.io/specification>
- **Weaver Documentation**: <https://pavics-weaver.readthedocs.io/>
- **Weaver GitHub**: <https://github.com/crim-ca/weaver>

