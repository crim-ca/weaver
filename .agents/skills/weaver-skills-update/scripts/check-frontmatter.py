#!/usr/bin/env python3
"""
Check YAML frontmatter format in Agent Skills.
Verifies that descriptions use multiline format with 'description: |'.
"""
import os
import sys
import yaml

skills_dir = ".agents/skills"
errors = []
warnings = []

for skill_name in sorted(os.listdir(skills_dir)):
    skill_path = os.path.join(skills_dir, skill_name, "SKILL.md")
    if not os.path.isfile(skill_path):
        continue

    with open(skill_path, 'r') as f:
        content = f.read()

    parts = content.split('---')
    if len(parts) < 3:
        errors.append(f"{skill_name}: Invalid frontmatter structure")
        continue

    frontmatter = parts[1]

    try:
        data = yaml.safe_load(frontmatter)

        # Check description format
        if 'description' in data and isinstance(data['description'], str):
            if 'description: |' not in frontmatter:
                errors.append(f"{skill_name}: needs 'description: |' format")
            elif len(data['description']) > 1024:
                warnings.append(f"{skill_name}: description exceeds 1024 characters")
            else:
                print(f"✓ {skill_name}: correct format")
        else:
            errors.append(f"{skill_name}: missing or invalid description")

    except yaml.YAMLError as e:
        errors.append(f"{skill_name}: YAML error - {e}")

print()
if warnings:
    print("Warnings:")
    for warning in warnings:
        print(f"  ⚠️  {warning}")
    print()

if errors:
    print("Errors:")
    for error in errors:
        print(f"  ❌ {error}")
    print()
    print(f"Total errors: {len(errors)}")
    sys.exit(1)
else:
    print("✅ All skills have properly formatted YAML frontmatter")
    sys.exit(0)
