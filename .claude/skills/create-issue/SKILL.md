t---
name: create-issue
description: Fetch the issue description from github and create it's equivalent in docs/issues directory
---

Read a GitHub issue by number and create a markdown file in `docs/issues/`.

## Input

The issue number is passed as an argument: `$ARGUMENTS`

## Steps

1. Run `gh issue view $ARGUMENTS --repo instadeepai/backend-packages` to fetch the issue title, body, labels, and comments
2. Create the directory `docs/issues/` if it doesn't exist
3. Create a markdown file at `docs/issues/<issue-number>-<issue-title-kebab-case>.md` where the filename is the issue number followed by the issue title converted to kebab-case (lowercase, spaces and special characters replaced with hyphens, consecutive hyphens collapsed, leading/trailing hyphens removed). For example, issue #637 titled "Implement DLQ in Azure Service Bus" becomes `637-implement-dlq-in-azure-service-bus.md`. The structure is:

```markdown
# <issue title>

**Issue:** #<number>
**Labels:** <comma-separated labels>
**Created:** <created date>
**Author:** <author>

---

<issue body as-is>

---

## Comments

<each comment with author and date, in chronological order>
```

4. If the issue has no comments, omit the Comments section
5. Do not modify or summarize the issue content — mirror it exactly as it appears on GitHub