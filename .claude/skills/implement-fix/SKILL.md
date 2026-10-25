---
name: implement-fix
description: Executes bug fix tasks from a fix plan file ONE AT A TIME. Follows TDD — writes failing reproduction test first, then implements the fix, then verifies. Use when you have an approved fix plan and want to implement it sequentially.
---

# Implementing Bug Fix Plans

A methodical skill for executing tasks from an approved fix plan file.

## Critical Rule: ONE TASK AT A TIME

**NEVER work on multiple tasks simultaneously.** Complete one task fully before moving to the next:

1. Identify the single next incomplete task
2. Implement it completely
3. Update the plan file with completion notes
4. Get user confirmation before proceeding to the next task

## Usage

```
/implement-fix plans/bug-name-fix.md
```

## Workflow

Copy this checklist for each task:

```
Fix Task Progress:
- [ ] Step 1: Identify next task
- [ ] Step 2: Read completion notes from previous tasks
- [ ] Step 3: Understand requirements
- [ ] Step 4: Clarify if needed (one question at a time)
- [ ] Step 5: Implement with tests
- [ ] Step 6: Update plan file
```

## Step 1: Identify Next Task

Parse the fix plan file to find the first incomplete task:

1. Look for `### Task N:` sections
2. Check acceptance criteria checkboxes `- [ ]`
3. First task with unchecked criteria is the target
4. If task has `**Status**: Completed` or all criteria checked, skip to next

**Output:**
```
Found: Task N - [Task Title]
Status: Not started / In progress / Completed
```

## Step 2: Read Completion Notes

Before starting, read `**Completion Notes**` from ALL previous tasks and the root cause analysis section:

```markdown
**Completion Notes**:
- Key decisions made: [...]
- Files created/modified: [...]
- Test results: [...]
- Notes for next task: [...]
```

Also re-read:
- **Root Cause Analysis** — to stay focused on the actual defect
- **Bug Triage Summary** — to remember the reproduction conditions

## Step 3: Understand Requirements

From the current task section, extract:

1. **Files to create/modify** — exact paths
2. **Implementation steps** — numbered list
3. **Tests required** — checkbox list
4. **Acceptance criteria** — what defines "done"

Cross-reference with:
- Root cause analysis section
- Previous task completion notes

## Step 4: Clarify If Needed

### Rules

1. **One question at a time** — Never batch questions
2. **Use AskUserQuestion tool** for structured responses
3. **Every question must include**:
   - Why you're asking (what's unclear)
   - Options with pros/cons when applicable
   - Your recommended approach
4. **Wait for answer** before proceeding

### When to Ask

- Ambiguous fix requirements
- Multiple valid implementation approaches
- Missing information not in plan or completion notes
- Potential conflicts with existing code

### When NOT to Ask

- Standard implementation patterns
- Information available in completion notes
- Questions already answered in the plan

## Step 5: Implement with Tests

### For Reproduction Test Tasks (typically Task 1)

1. **Write the test** that triggers the buggy behavior
2. **Run the test** — it MUST fail on current code
3. If it passes, the test doesn't capture the bug — revisit the plan

```bash
# Run ONLY the reproduction test — MUST fail
dotnet test --filter "FullyQualifiedName~TestClassName.TestMethodName"
```

### For Fix Implementation Tasks (typically Task 2+)

1. **Implement the minimal fix** as described in the plan
2. **Run the reproduction test** — it MUST now pass
3. **Run related tests** — ensure no regressions in the module

```bash
# Run the reproduction test — MUST pass now
dotnet test --filter "FullyQualifiedName~TestClassName.TestMethodName"

# Run module tests
dotnet test <project-path> -c release
```

### For Verification Tasks (typically final task)

1. Run the full test suite for affected project(s)
2. Run formatting check
3. Present results

```bash
# Run full test suite
dotnet test -c release

# Check formatting
dotnet format --verify-no-changes
```

## Step 6: Update Plan File

After completing the task, update the fix plan file:

### 1. Mark Acceptance Criteria

Change `- [ ]` to `- [x]` for completed criteria:

```markdown
**Acceptance criteria**:
- [x] Reproduction test fails on current code
- [x] Test name follows project conventions
```

### 2. Mark Tests Completed

```markdown
**Tests**:
- [x] `ScheduleWithReplaceEnabled_DuplicateKey_ShouldReplaceExisting`
```

### 3. Add Completion Notes

Add at the end of the task section:

```markdown
**Completion Notes**:
- **Files created/modified**: `path/to/file.cs`
- **Key decisions**: [Non-obvious choices]
- **Test results**: [Pass/fail summary]
- **Notes for next task**: [Context needed for next task]
```

### 4. Add Status

```markdown
**Status**: Completed
```

## Task Transition

**STOP after each task.** After completing a task:

1. Confirm completion with user
2. Ask: "Continue to Task N+1?"
3. **Wait for explicit user confirmation**
4. Only then return to Step 1

Do NOT automatically proceed to the next task.

## Error Handling

### Build Failures

1. Fix the issue
2. Re-run tests
3. Continue implementation

### Test Failures

1. Analyze failure
2. Fix code (not test, unless test is wrong)
3. Re-run all affected tests

### Reproduction Test Passes (when it shouldn't)

1. The test doesn't capture the bug
2. Re-read the root cause analysis
3. Adjust the test to trigger the actual defect
4. Ask user for guidance if unclear

### Blocked by External Factor

1. Document the blocker in task notes
2. Ask user how to proceed
3. Options: skip task, wait, or work around

## Anti-patterns to Avoid

- **Working on multiple tasks at once** — Complete ONE task fully before starting another
- **Auto-proceeding to next task** — Always wait for user confirmation
- Writing a reproduction test that passes on broken code
- Implementing without reading the root cause analysis
- Batching multiple questions
- Skipping the reproduction test
- Not updating the plan file after completion
- Implementing beyond task scope ("gold plating")
- Forgetting to mark criteria as complete
- Fixing symptoms instead of root cause

## Example Session

```
User: /implement-fix plans/duplicate-job-entries-fix.md

Claude: Reading fix plan...

Root Cause: BackgroundJobsService.ScheduleJob calls scheduler.ScheduleJob()
without checking existence — throws on duplicate keys during app restart.

Found: Task 1 - Write reproduction test
Status: Not started

Writing test: ScheduleWithReplaceEnabled_DuplicateKey_ShouldSucceed...
Running test... FAILED as expected (method not implemented).

Task 1 completed. Updating plan with completion notes.
Continue to Task 2: Add ScheduleWithReplaceEnabled to interface and implementation?
```
