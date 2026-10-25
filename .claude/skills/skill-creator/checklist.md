# Skill Quality Checklist

Before sharing a skill, verify all items.

## Metadata

- [ ] `name` is lowercase with hyphens only
- [ ] `name` is max 64 characters
- [ ] `name` uses gerund form (e.g., `processing-pdfs`)
- [ ] `name` avoids vague terms (`helper`, `utils`, `tools`)
- [ ] `description` is non-empty
- [ ] `description` is max 1024 characters
- [ ] `description` is written in third person
- [ ] `description` includes what the skill does
- [ ] `description` includes when to use it (triggers)
- [ ] `description` contains no XML tags

## Content quality

- [ ] SKILL.md body is under 500 lines
- [ ] Only adds context Claude doesn't already have
- [ ] No unnecessary explanations of common concepts
- [ ] Consistent terminology throughout
- [ ] No time-sensitive information
- [ ] Examples are concrete, not abstract

## Structure

- [ ] Additional details in separate files (if needed)
- [ ] File references are one level deep from SKILL.md
- [ ] Longer reference files have table of contents
- [ ] Forward slashes in all paths (no backslashes)
- [ ] Clear workflows with sequential steps

## For skills with scripts

- [ ] Scripts handle errors explicitly (don't punt to Claude)
- [ ] All constants are documented (no magic numbers)
- [ ] Required packages listed
- [ ] Validation/verification steps included
- [ ] Clear distinction: execute vs. read as reference

## Testing

- [ ] Tested with actual use cases
- [ ] Works with intended model(s)
- [ ] Skill triggers appropriately from description

## Quick validation commands

Check line count:
```bash
wc -l SKILL.md
# Should be under 500
```

Check for Windows paths:
```bash
grep -n '\\' SKILL.md
# Should return nothing
```

Validate YAML frontmatter:
```bash
head -20 SKILL.md | grep -E '^(name|description):'
# Should show both fields
```