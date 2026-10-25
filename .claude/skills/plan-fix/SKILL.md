---
name: plan-fix
description: Plans bug fixes through structured triage, codebase exploration, root cause diagnosis, and actionable fix plan generation. Outputs a fix plan file for use with /implement-fix. Use when asked to plan a bug fix, diagnose a failure, investigate an error, or analyze an issue.
---

# Planning Bug Fixes

A methodical skill for diagnosing bugs and producing an actionable fix plan — no assumptions.

## Workflow

Copy this checklist:

```
Fix Planning Progress:
- [ ] Phase 1: Triage - Gather symptoms and reproduction steps
- [ ] Phase 2: Exploration - Understand affected code paths
- [ ] Phase 3: Diagnosis - Identify root cause
- [ ] Phase 4: Planning - Design fix tasks with tests
- [ ] Phase 5: Finalizing - Get approval and save fix plan
```

## Phase 1: Triage

**Goal**: Collect all observable symptoms before touching code.

### Required Information

Gather the following using **AskUserQuestion** (one question at a time):

1. **Stack trace / error output** — Ask for the full error message or stack trace
2. **Reproduction steps** — Exact steps to trigger the bug
3. **Expected vs actual behavior** — What should happen vs what does happen
4. **Environment** — Which environment, configuration, or conditions trigger it

### Rules

1. **One question at a time** — Never batch multiple questions
2. **Use AskUserQuestion tool** for structured responses
3. **Do NOT skip questions** — If the user already provided info (e.g., in the issue), acknowledge it and ask only for what's missing
4. **Extract from issues** — If linked to a GitHub issue, read it first with `gh issue view` and pre-fill known information

### Triage Question Flow

Start by checking what's already known:

```
1. Read linked issue / PR / user context
2. Identify which of the 4 required items are already provided
3. Ask ONLY for missing items, one at a time
```

### Triage Summary

After collecting all info, output a structured summary for confirmation:

```
## Bug Triage Summary

**Error**: [Error message or description]
**Stack trace**: [Key frames or "not applicable"]
**Reproduction steps**:
1. [Step 1]
2. [Step 2]

**Expected**: [What should happen]
**Actual**: [What does happen]
**Environment**: [Relevant context]
```

Ask user to confirm the summary is accurate before proceeding.

**Do NOT proceed until triage is confirmed.**

## Phase 2: Exploration

**Goal**: Understand the code paths involved in the bug.

1. Use the Task tool with `subagent_type=Explore` to investigate:
   - The code path described in the stack trace / reproduction steps
   - Related error handling and validation logic
   - Test coverage of the affected area
   - Recent changes to affected files (`git log --oneline -10 -- <file>`)

2. Document findings:
   - Entry point(s) where the bug manifests
   - Root file(s) and line(s) likely causing the issue
   - Existing tests that should have caught this (if any)
   - Test patterns used in the affected module

**Do NOT proceed until exploration is complete.**

## Phase 3: Diagnosis

**Goal**: Identify the root cause with confidence.

### Analysis Steps

1. **Trace the execution path** — Follow the code from trigger to failure
2. **Identify the defect** — Pinpoint the exact line(s) or logic error
3. **Understand why** — Why does this code fail under these conditions?
4. **Check for siblings** — Are there similar patterns elsewhere that have the same bug?

### Diagnosis Output

Present the root cause analysis to the user:

```
## Root Cause Analysis

**Defect location**: `path/to/file.cs:line` — [method/function name]

**What's wrong**: [1-2 sentence description of the defect]

**Why it fails**: [Explanation of the conditions that trigger the bug]

**Similar occurrences**: [List any sibling patterns with the same issue, or "None found"]
```

Ask user to confirm the diagnosis before proceeding to planning.

**Do NOT proceed without user agreement on root cause.**

## Phase 4: Planning

**Goal**: Design actionable fix tasks with integrated tests.

### Rules

1. **Present implementation options one at a time** with pros/cons/recommendation
2. **Task 1 is always the reproduction test** — A failing test that proves the bug
3. **Task 2+ are the fix** — Minimal changes to make the test green
4. **Final task is always verification** — Run full test suite
5. **Atomic tasks** — Each task is self-contained

### Task Structure

Each task should follow this format:

```markdown
### Task N: [Title]

**Files to modify/create**:
- `path/to/file.cs` — [what changes]

**Implementation**:
1. [Step 1]
2. [Step 2]

**Tests** (implement alongside):
- [ ] [Test description]

**Acceptance criteria**:
- [ ] [Criterion 1]
- [ ] [Criterion 2]
```

### Fix Plan Template

```markdown
# Fix Plan: [Bug Title]

## Issue Reference
[Link to GitHub issue or description]

## Bug Triage Summary
**Error**: [Error message]
**Reproduction steps**: [Steps]
**Expected**: [Expected behavior]
**Actual**: [Actual behavior]

## Root Cause Analysis
**Defect location**: `path/to/file.cs:line`
**What's wrong**: [Description]
**Why it fails**: [Explanation]
**Similar occurrences**: [List or "None"]

## Fix Tasks

### Task 1: Write reproduction test
[Test that fails on current code, proving the bug exists]

### Task 2: Implement fix
[Minimal code change to fix the root cause]

### Task 3: Fix sibling occurrences (if any)
[Apply same fix pattern to similar code]

### Task 4: Verify no regressions
[Run full test suite]

## Risks and Mitigations
[Breaking changes, edge cases, etc.]

## Out of Scope
[Explicitly excluded items]
```

## Phase 5: Finalizing

**Goal**: Get approval and save the fix plan.

1. **Present the complete plan** to the user
2. **Ask for feedback or approval**:
   - Use AskUserQuestion with options: "Approve", "Request changes", "Need more details"
3. **If feedback provided**:
   - Address specific concerns
   - Update the plan
   - Present again
   - Repeat until approved
4. **Once approved**:
   - Save plan to `plans/[bug-name]-fix.md`
   - Confirm save location with user

### Saving the Fix Plan

File naming convention:
- Lowercase
- Hyphens for spaces
- Suffix with `-fix.md`
- Example: `plans/duplicate-job-entries-fix.md`

## Anti-patterns to Avoid

- Making assumptions about reproduction steps
- Batching triage questions
- Skipping root cause diagnosis
- Planning a fix without user confirmation on diagnosis
- Proceeding without explicit approval
- Skipping the reproduction test task
- Mixing fix tasks with refactoring tasks