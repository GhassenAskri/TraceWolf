---
name: implement-plan
description: Executes implementation tasks from a feature plan file ONE AT A TIME. Tracks progress, maintains completion notes, and ensures tests are implemented alongside code. Use when you have an approved plan and want to implement tasks sequentially.
---

# Implementing Feature Plans

A methodical skill for executing tasks from an approved feature plan file.

## Critical Rule: ONE TASK AT A TIME

**NEVER work on multiple tasks simultaneously.** Complete one task fully before moving to the next:

1. Identify the single next incomplete task
2. Implement it completely with tests
3. Update the plan file with completion notes
4. Get user confirmation before proceeding to the next task

## Usage

```
/implement-plan .claude/features/feature-name/feature-name-plan.md
/implement-plan feature-name        # shorthand: resolves to the path above
```

## Feature Folder

Plans live in `.claude/features/[feature-name]/` (created by `plan-feature`). Everything related to implementing that feature is written to the **same folder**:

```
.claude/features/
└── [feature-name]/
    ├── [feature-name]-plan.md             # the approved plan (checkboxes, status, completion notes)
    └── [feature-name]-implementation.md   # implementation log, created on the first task
```

- If given only a feature name, resolve it to `.claude/features/[feature-name]/[feature-name]-plan.md`.
- If the plan file is not inside `.claude/features/`, ask the user whether to move it there before starting.
- Create `[feature-name]-implementation.md` when the first task starts, if it does not exist.
- Any other implementation file for the feature that is not source code (spike findings, decision records, manual verification steps) also goes in this folder. Source code and tests go in the project as the plan specifies.

## Workflow

Copy this checklist for each task:

```
Task Implementation Progress:
- [ ] Step 1: Identify next task
- [ ] Step 2: Read completion notes from previous tasks
- [ ] Step 3: Understand requirements
- [ ] Step 4: Clarify if needed (one question at a time)
- [ ] Step 5: Implement with tests
- [ ] Step 6: Update plan file and implementation log
```

## Step 1: Identify Next Task

Parse the plan file to find the first incomplete task:

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

Before starting, read `[feature-name]-implementation.md` in the feature folder (if it exists) and `**Completion Notes**` from ALL previous tasks:

```markdown
**Completion Notes**:
- Key decisions made: [...]
- Files created/modified: [...]
- Patterns established: [...]
- Dependencies introduced: [...]
- Test utilities added: [...]
```

These notes contain critical context for maintaining consistency.

## Step 3: Understand Requirements

From the current task section, extract:

1. **Files to create/modify** - exact paths
2. **Implementation steps** - numbered list
3. **Tests required** - checkbox list
4. **Acceptance criteria** - what defines "done"

Cross-reference with:
- Architecture decisions section
- Requirements summary table
- Related previous task completion notes

## Step 4: Clarify If Needed

### Rules

1. **One question at a time** - Never batch questions
2. **Use AskUserQuestion tool** for structured responses
3. **Every question must include**:
   - Why you're asking (what's unclear)
   - Options with pros/cons when applicable
   - Your recommended approach
4. **Wait for answer** before proceeding

### Question Format

```
**Clarification needed for Task N**

**Question**: [Clear, specific question]

**Context**: [Why this matters for implementation]

**Options** (if applicable):
1. **[Option A]** - [Description]
2. **[Option B]** - [Description]

**Recommendation**: [Your suggested approach]
```

### When to Ask

- Ambiguous requirements
- Multiple valid implementation approaches
- Missing information not in plan or completion notes
- Potential conflicts with existing code

### When NOT to Ask

- Standard implementation patterns
- Information available in completion notes
- Questions already answered in the plan

## Step 5: Implement with Tests

### Implementation Order

1. **Write tests first** when practical (TDD approach)
2. Implement the minimum code to pass tests
3. Refactor if needed
4. Run all related tests

### Test Strategy

- **Unit tests**: Implement alongside domain models/services
- **Integration tests**: Implement as early as possible, right after repository/EF configuration
- Follow existing test patterns from codebase

### Progress Tracking

Use TodoWrite to track sub-tasks:

```
- [ ] Create domain model
- [ ] Write unit tests for model
- [ ] Create repository interface
- [ ] Create EF configuration
- [ ] Write integration tests
- [ ] Implement repository
```

Mark each complete immediately after finishing.

### Verification

Before marking task complete:

```bash
# Run specific tests
dotnet test --filter "ClassName~TaskRelatedTests"

# Run full test suite
dotnet test -c release

# Verify formatting
dotnet format --verify-no-changes
```

## Step 6: Update Plan File

After completing the task, update the plan file:

### 1. Mark Acceptance Criteria

Change `- [ ]` to `- [x]` for completed criteria:

```markdown
**Acceptance criteria**:
- [x] UnitCost entity created with all required properties
- [x] AcceleratorsCost supports multiple GPU types
```

### 2. Mark Tests Completed

```markdown
**Tests**:
- [x] Unit test: `UnitCost_Create_WithValidParameters_ShouldSucceed`
- [x] Integration test: `UnitCostRepository_Add_ShouldPersist`
```

### 3. Add Completion Notes

Add at the end of the task section:

```markdown
**Completion Notes**:
- **Files created**: `src/.../UnitCost.cs`, `test/.../UnitCostTests.cs`
- **Key decisions**: Used record type for immutability, added private setter for EF
- **Patterns established**: Dictionary<string, decimal> for AcceleratorsCost JSON
- **Test utilities added**: `UnitCostBuilder` in test helpers
- **Integration points**: Registered in DI via `CostModule.cs`
- **Notes for next task**: Repository needs to handle soft delete filter
```

### 4. Add Status

```markdown
**Status**: Completed
```

### 5. Append to the Implementation Log

Append an entry to `.claude/features/[feature-name]/[feature-name]-implementation.md`:

```markdown
## Task N: [Title] — Completed YYYY-MM-DD

- **Files created/modified**: [...]
- **Commands to verify**: [exact test/run commands used]
- **Test results**: [e.g. 12 passed, 0 failed]
- **Deviations from plan**: [what changed and why, or "None"]
- **Open issues / follow-ups**: [...]
```

Start the file with a header the first time:

```markdown
# Implementation Log: [Feature Name]

Plan: [feature-name]-plan.md
```

The plan file keeps the *what* (checkboxes, status, completion notes for the next task). The implementation log keeps the *history* (what was run, results, deviations).

### Completion Notes Guidelines

Include everything needed to continue efficiently:

| Category | What to Include |
|----------|-----------------|
| Files | All files created or significantly modified |
| Decisions | Non-obvious choices made during implementation |
| Patterns | New patterns introduced for consistency |
| Test utilities | Builders, fixtures, helpers created |
| Integration | How this connects to other components |
| Next task hints | Anything relevant for subsequent tasks |

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

### Blocked by External Factor

1. Document the blocker in task notes
2. Ask user how to proceed
3. Options: skip task, wait, or work around

## Anti-patterns to Avoid

- **Working on multiple tasks at once** - Complete ONE task fully before starting another
- **Auto-proceeding to next task** - Always wait for user confirmation
- Implementing without reading previous completion notes
- Batching multiple questions
- Skipping tests or leaving them for later
- Not updating the plan file and implementation log after completion
- Writing feature notes outside `.claude/features/[feature-name]/`
- Making assumptions about unclear requirements
- Implementing beyond task scope ("gold plating")
- Forgetting to mark criteria as complete

## Example Session

```
User: /implement-plan .claude/features/cost-management/cost-management-plan.md

Claude: Reading plan file...

Found: Task 3 - Create UnitCost EF Configuration and Migration
Status: Not started

Previous completion notes reviewed:
- Task 1: Created UnitCost entity with Dictionary<string, decimal> for AcceleratorsCost
- Task 2: Repository interfaces created, GetEffectiveUnitCost uses EffectiveDate filtering

Starting implementation...

[Creates EF configuration]
[Writes integration tests]
[Generates migration]
[Runs tests]

All tests passing. Updating plan file with completion notes and appending to
.claude/features/cost-management/cost-management-implementation.md.

Task 3 completed. Continue to Task 4: Extend Organization with Currency Field?
```