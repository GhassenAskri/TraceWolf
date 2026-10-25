---
name: creating-skills
description: Create well-structured Agent Skills following best practices. Use when asked to create, write, or help with a new skill, SKILL.md file, or custom capability for Claude.
---

# Creating Agent Skills

## Skill structure

Every skill requires a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: your-skill-name
description: What it does and when to use it. Written in third person.
---

# Skill Title

[Instructions here]
```

**Field requirements:**
- `name`: lowercase letters, numbers, hyphens only (max 64 chars)
- `description`: max 1024 chars, third person, includes triggers

## Workflow for creating a skill

Copy this checklist:

```
Skill Creation Progress:
- [ ] Step 1: Identify the reusable pattern
- [ ] Step 2: Write metadata (name + description)
- [ ] Step 3: Draft minimal instructions
- [ ] Step 4: Add examples if needed
- [ ] Step 5: Review for conciseness
- [ ] Step 6: Validate structure
```

### Step 1: Identify the reusable pattern

Ask: What context would be useful for similar future tasks?
- Domain knowledge Claude doesn't have
- Specific workflows or procedures
- Configuration or schemas
- Style preferences or conventions

### Step 2: Write metadata

**Name** (gerund form preferred):
- Good: `processing-pdfs`, `analyzing-data`, `reviewing-code`
- Avoid: `helper`, `utils`, `tools`

**Description** (third person, specific):
```yaml
# Good
description: Analyzes Excel spreadsheets and generates summary reports. Use when working with .xlsx files, pivot tables, or spreadsheet analysis.

# Bad
description: Helps with documents
```

### Step 3: Draft minimal instructions

**Default assumption**: Claude is already very smart. Only add context Claude doesn't already have.

Challenge each piece:
- "Does Claude really need this explanation?"
- "Can I assume Claude knows this?"
- "Does this paragraph justify its token cost?"

Keep SKILL.md under 500 lines. Split into separate files if needed.

### Step 4: Add examples if needed

For output-sensitive skills, provide input/output pairs:

````markdown
**Example:**
Input: [what user provides]
Output: [what Claude should produce]
````

### Step 5: Review for conciseness

Remove:
- Explanations of common concepts
- Redundant instructions
- Verbose descriptions

### Step 6: Validate structure

See [CHECKLIST.md](CHECKLIST.md) for final validation.

## Progressive disclosure pattern

For complex skills, split content:

```
skill-name/
├── SKILL.md (overview, under 500 lines)
├── REFERENCE.md (detailed reference)
├── EXAMPLES.md (if many examples needed)
└── scripts/ (utility scripts)
```

Reference files from SKILL.md:
```markdown
**Advanced features**: See [REFERENCE.md](REFERENCE.md)
```

Keep references one level deep from SKILL.md.

## Templates

See [TEMPLATES.md](TEMPLATES.md) for starter templates:
- Simple instruction skill
- Code-based skill with scripts
- Domain knowledge skill

## Common patterns

**Workflow pattern**: Clear sequential steps with checklist
**Template pattern**: Provide output format templates
**Examples pattern**: Input/output pairs for style guidance
**Conditional pattern**: Guide through decision points

## Anti-patterns to avoid

- Vague descriptions (`"Helps with documents"`)
- Time-sensitive information
- Inconsistent terminology
- Deeply nested references
- Windows-style paths (use forward slashes)
- Too many options without defaults
- Magic numbers without explanation