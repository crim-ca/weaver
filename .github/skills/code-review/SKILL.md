---
name: weaver-code-review
description: |
  Apply repository-specific code review rules for Weaver pull requests.
  Validates CHANGES.rst updates, formatting style, documentation, comments, and review practices.
  Use when performing or requesting code reviews on Weaver contributions.
license: Apache-2.0
metadata:
  category: github
  version: 1.0.0
  author: fmigneault
allowed-tools: file_read grep_search
---

# Weaver Code Review

## Overview

Provides [additional rules](#additional-rules) that must be validated for code review specific to this repository.
Typical code review rules for coding best practices still apply.

## Additional Rules

- [ ] Pull requests must contain `CHANGES.rst` updates that describes concisely applied changes relevant to the code.
  - Indicated changes are limited to new features or bug fixes related to the API, CLI, documentation or code logic.
  - Changes purely related to CI configurations, security or dependency version updates do not need mention in changes.
  - Issues related to feature implementation or bugfix should be liked with RST references using the full GitHub URL.

- [ ] Changes should respect the formatting style used across the code base.
  - Avoid switching code style such as using different quotes or indentations (CI will validate and enforce this).
  - Ensure docstring annotations use the usual representation if provided.
  - Ensure that known terminology or references in docstring are consistent with existing definitions.
  - Typing annotations are consistent and logical compared to other function and class definitions.

- [ ] Important behaviour changes or new features are documented in the relevant sections.
  - Code fragments implementing a specific OGC feature refer to them as necessary for identification.
  - The `docs/source` RST documents or updates the appropriate functionalities with relevant details.
  - If applicable, examples are provided through the OpenAPI definitions.
  - Docstring provide RFC or OGC references as `seealso` details if relevant for implemented functions.

- [ ] Superfluous comments are avoided.
  - Code comments that directly state a behaviour easily interpreted with the code should be avoided.
  - Code comments should be provided when needed to interpret an implementation choice not directly observed in code.
  - Code comments may be provided to describe complex operations if used sparingly.

- [ ] Avoid repeating yourself.
  - Review comments that can be provided globally (issue repeated multiple times) should be provided only once.
  - Review comments should be focused to specific files and code lines/blocks when applicable only to them.
  - Review comments expected to be processed by CI validations should only be in the review summary if needed.
