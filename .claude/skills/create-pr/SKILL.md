---
name: create-pr
description: Creates a draft PR linked to an existing open issue. Fetches open issues from the repo, lets the user pick one, and provides the git commands to get started. Use when asked to create a PR, open a pull request, or start working on an issue.
---

# Create PR

Creates a draft PR linked to an existing open issue via `gh` CLI.

## SAFETY RULES — NON-NEGOTIABLE

**This skill is CREATE-ONLY. The following actions are STRICTLY FORBIDDEN, even if the user explicitly asks:**

- NEVER delete a branch, PR, issue, or any GitHub resource
- NEVER close or merge a PR
- NEVER run `gh pr close`, `gh pr merge`, `git push --force`, `git branch -D`, or any destructive command
- NEVER run any `gh api` mutation that removes or destroys data
- NEVER execute git commit on behalf of the user — only create branches, push, and open PRs

If the user asks to delete or remove anything, respond with:
> This skill only creates PRs. Destructive actions (delete, close, merge, force-push) are not permitted. Please use the GitHub UI directly for those operations.

## Instructions

### Step 1: Select an Open Issue

Fetch open issues assigned to the current user (or all if none assigned):

```bash
gh issue list --state open --assignee "@me" --limit 20 --json number,title,labels
```

If no issues are assigned to the user, fall back to all open issues:

```bash
gh issue list --state open --limit 20 --json number,title,labels
```

Present the issues to the user via **AskUserQuestion** showing `#<number> — <title>` so they can pick which issue to link the PR to.

### Step 2: Select Base Branch

Use **AskUserQuestion** to ask which branch to start from:
- `main` (Recommended)
- Current branch (show the name)
- Other (let user type a branch name)

### Step 3: Generate Branch Name and PR Title

**PR title format:** `feat(<component>): <issue-number> - <title>`

- Extract `<component>` from `[component]` in the issue title
- Use the issue title without the `[component]` prefix for `<title>`
- Example: issue #799 `[audit] Manage sensitive data...` → `feat(audit): 799 - Manage sensitive data...`

**Branch name format:** `<issue-number>-<component>-<kebab-case-short-title>` (max 50 chars)

- Example: `799-audit-manage-sensitive-data`

### Step 4: Create Branch and Push

```bash
git fetch origin
git checkout -b <branch-name> origin/<base-branch>
git push -u origin <branch-name>
```

### Step 5: Create the Draft PR

Fetch the issue body to include in the PR description:

```bash
gh issue view <issue-number> --json body --jq '.body'
```

Create the PR:

```bash
gh pr create \
  --title "feat(<component>): <issue-number> - <title>" \
  --body "$(cat <<'EOF'
## Summary

Closes #<issue-number>

## Description

<issue-body>

## Test Plan

- [ ] TODO: Add test plan

EOF
)" \
  --base <base-branch> \
  --draft \
  --assignee "@me"
```

### Step 6: Summary

Display a final summary:

```
## PR Created!

| Item       | Details                                  |
|------------|------------------------------------------|
| Issue      | #<issue-number> — <title>                |
| PR title   | feat(<component>): <number> - <title>    |
| Branch     | <branch-name>                            |
| Base       | <base-branch>                            |
| PR         | #<pr-number> (draft)                     |
| Assignee   | @me                                      |

You're ready to start coding!
```

## Error Handling

- If `gh` is not authenticated → prompt user to run `gh auth login`
- If no open issues exist → inform user and suggest creating one with `/create-issue`
- If the base branch doesn't exist → show available remote branches and re-ask