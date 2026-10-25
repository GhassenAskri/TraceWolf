# Skill Examples

Real examples demonstrating best practices.

## Example 1: Git commit message skill

A simple skill that provides style guidance.

````markdown
---
name: writing-commits
description: Generates descriptive commit messages by analyzing git diffs. Use when the user asks for help writing commit messages or reviewing staged changes.
---

# Writing Commit Messages

## Format

```
type(scope): brief description

Detailed explanation if needed
```

**Types:** feat, fix, docs, style, refactor, test, chore

## Examples

**Example 1:**
Input: Added user authentication with JWT tokens
Output:
```
feat(auth): implement JWT-based authentication

Add login endpoint and token validation middleware
```

**Example 2:**
Input: Fixed bug where dates displayed incorrectly
Output:
```
fix(reports): correct date formatting in timezone conversion

Use UTC timestamps consistently across report generation
```

## Guidelines

- First line under 72 characters
- Use imperative mood ("add" not "added")
- Focus on why, not just what
````

## Example 2: API analysis skill with domain knowledge

A skill with progressive disclosure for domain data.

````markdown
---
name: analyzing-sales-data
description: Analyzes sales database using company conventions and schemas. Use when querying sales data, revenue metrics, or pipeline analysis.
---

# Sales Data Analysis

## Quick reference

| Metric | Table | Key field |
|--------|-------|-----------|
| Revenue | `orders` | `total_amount` |
| Pipeline | `opportunities` | `expected_value` |
| Win rate | `opportunities` | `status` |

## Important rules

- Always exclude test accounts: `WHERE account_type != 'test'`
- Use UTC for all timestamps
- Revenue = closed-won opportunities only

## Common queries

**Quarterly revenue:**
```sql
SELECT SUM(total_amount)
FROM orders
WHERE status = 'completed'
  AND account_type != 'test'
  AND QUARTER(created_at) = @quarter
```

## Detailed schemas

See [schemas/sales.md](schemas/sales.md) for complete field definitions.
````

## Example 3: Document processing skill with scripts

A code-based skill with validation workflow.

````markdown
---
name: processing-invoices
description: Extracts and validates data from invoice PDFs. Use when processing invoices, extracting invoice data, or validating invoice formats.
---

# Invoice Processing

## Quick start

```bash
python scripts/extract.py invoice.pdf > data.json
```

## Workflow

```
Progress:
- [ ] Extract data from PDF
- [ ] Validate extracted fields
- [ ] Review and correct errors
- [ ] Export final data
```

### Step 1: Extract data

```bash
python scripts/extract.py invoice.pdf > data.json
```

### Step 2: Validate

```bash
python scripts/validate.py data.json
```

Fix any errors reported before continuing.

### Step 3: Export

```bash
python scripts/export.py data.json --format csv
```

## Required fields

| Field | Type | Validation |
|-------|------|------------|
| invoice_number | string | Required, unique |
| date | date | Required, ISO format |
| total | decimal | Required, positive |
| line_items | array | At least one item |
````

## Example 4: Concise vs verbose comparison

**Good (concise):**
````markdown
---
name: extracting-pdf-text
description: Extracts text from PDF files using pdfplumber. Use when working with PDFs or extracting document text.
---

# PDF Text Extraction

```python
import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

For scanned PDFs, use OCR: See [OCR.md](OCR.md)
````

**Bad (verbose):**
````markdown
---
name: extracting-pdf-text
description: Extracts text from PDF files.
---

# PDF Text Extraction

PDF (Portable Document Format) is a file format developed by Adobe in 1992.
PDFs can contain text, images, and other elements. To extract text from a PDF
file, you need to use a specialized library because PDFs store text in a
complex internal format that isn't directly readable.

There are many libraries available for PDF processing in Python:
- pdfplumber - good for text extraction
- PyPDF2 - basic PDF operations
- PyMuPDF - fast processing
- pdf2image - converts to images

We recommend pdfplumber because it handles most cases well and is easy to use.
First, you need to install it...

[continues unnecessarily]
````

The concise version assumes Claude knows what PDFs are and jumps straight to the useful code.