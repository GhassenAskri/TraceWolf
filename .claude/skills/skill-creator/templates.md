# Skill Templates

## Template 1: Simple instruction skill

For skills that provide guidance without code.

````markdown
---
name: doing-something
description: Does X for Y context. Use when the user mentions Z or asks about W.
---

# Skill Title

## Quick start

[Most common use case with minimal example]

## Workflow

1. First step
2. Second step
3. Final step

## Guidelines

- Key principle 1
- Key principle 2

## Examples

**Example 1:**
Input: [scenario]
Output: [expected result]
````

## Template 2: Code-based skill with scripts

For skills that include executable scripts.

````markdown
---
name: processing-something
description: Processes X files and generates Y. Use when working with X files or when the user mentions X processing.
---

# Processing Something

## Quick start

```bash
python scripts/process.py input.file output.file
```

## Workflow

Copy this checklist:

```
Task Progress:
- [ ] Step 1: Analyze input
- [ ] Step 2: Validate configuration
- [ ] Step 3: Process data
- [ ] Step 4: Verify output
```

### Step 1: Analyze input

Run: `python scripts/analyze.py input.file`

Output shows structure and available options.

### Step 2: Validate configuration

Edit `config.json` with desired settings.

Run: `python scripts/validate.py config.json`

Fix any errors before continuing.

### Step 3: Process data

Run: `python scripts/process.py input.file config.json output.file`

### Step 4: Verify output

Run: `python scripts/verify.py output.file`

If verification fails, return to Step 2.

## Utility scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `analyze.py` | Inspect input | `python scripts/analyze.py <input>` |
| `validate.py` | Check config | `python scripts/validate.py <config>` |
| `process.py` | Main processing | `python scripts/process.py <in> <cfg> <out>` |
| `verify.py` | Verify output | `python scripts/verify.py <output>` |
````

## Template 3: Domain knowledge skill

For skills that provide domain-specific context.

````markdown
---
name: analyzing-domain
description: Analyzes [domain] data using [company/project] conventions. Use when querying [domain] data or when the user asks about [specific metrics].
---

# Domain Analysis

## Available data

| Dataset | Description | Reference |
|---------|-------------|-----------|
| Sales | Revenue, pipeline | [reference/sales.md](reference/sales.md) |
| Finance | ARR, billing | [reference/finance.md](reference/finance.md) |
| Product | Usage, features | [reference/product.md](reference/product.md) |

## Common queries

**Total revenue this quarter:**
```sql
SELECT SUM(amount) FROM sales WHERE quarter = CURRENT_QUARTER
```

**Active users:**
```sql
SELECT COUNT(DISTINCT user_id) FROM events WHERE date > DATE_SUB(NOW(), INTERVAL 30 DAY)
```

## Important rules

- Always filter test accounts: `WHERE account_type != 'test'`
- Use UTC timestamps
- Round currency to 2 decimals

## Quick reference lookup

```bash
grep -i "metric_name" reference/*.md
```
````

## Template 4: Style/convention skill

For skills that enforce style or conventions.

````markdown
---
name: writing-something
description: Generates [content type] following [project/company] style guide. Use when creating [content type] or when the user asks for [content type].
---

# Writing [Content Type]

## Format

Use this structure:

```
[TEMPLATE STRUCTURE]
```

## Style rules

1. [Key rule 1]
2. [Key rule 2]
3. [Key rule 3]

## Examples

**Good example:**
```
[Well-formatted example]
```

**Avoid:**
```
[Counter-example showing what not to do]
```

## Terminology

| Use | Don't use |
|-----|-----------|
| [preferred term] | [avoided term] |
| [preferred term] | [avoided term] |
````