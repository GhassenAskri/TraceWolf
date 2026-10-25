---
name: plan-feature
description: Plans feature implementations through deep codebase exploration, structured clarifying questions, and iterative approval. Use when asked to plan a feature, design an implementation, or create a development plan.
---

# Planning Feature Implementations

A methodical skill for planning feature implementations with no assumptions.

## Workflow

Copy this checklist:

```
Feature Planning Progress:
- [ ] Phase 1: Exploration - Understand codebase patterns
- [ ] Phase 2: Understanding - Clarify requirements (no assumptions)
- [ ] Phase 3: Planning - Design implementation with tests
- [ ] Phase 4: Finalizing - Get approval and save plan
```

## Phase 1: Exploration

**Goal**: Deeply understand codebase patterns related to the feature.

1. Use the Task tool with `subagent_type=Explore` to investigate:
   - Similar existing features and their implementation patterns
   - Architectural decisions and conventions
   - Related domain modules and their structure
   - Test patterns used in similar features

2. Document findings:
   - Key files and directories involved
   - Patterns to follow (CQRS, repositories, etc.)
   - Integration points
   - Test coverage expectations

**Do NOT proceed until exploration is complete.**

## Phase 2: Understanding

**Goal**: Full clarity on requirements with zero assumptions.

### Rules

1. **One question at a time** - Never batch multiple questions
2. **Use AskUserQuestion tool** when possible for structured responses
3. **Every question must include**:
   - Clear options (when applicable)
   - Pros and cons for each option
   - Recommended option with reasoning
4. **Wait for answer** before asking next question
5. **No assumptions** - If unclear, ask

### Question Format

When presenting options, use this structure:

```
**Question**: [Clear question]

**Options**:

1. **[Option A]** (Recommended)
   - Pros: [benefits]
   - Cons: [drawbacks]

2. **[Option B]**
   - Pros: [benefits]
   - Cons: [drawbacks]

3. **[Option C]**
   - Pros: [benefits]
   - Cons: [drawbacks]

**Recommendation**: [Option X] because [reasoning]
```

### Common Clarifications

- Scope boundaries (what's in/out)
- Edge cases and error handling
- Performance requirements
- Security considerations
- Breaking changes tolerance
- Migration needs

## Phase 3: Planning

**Goal**: Create detailed, actionable implementation plan.

### Rules

1. **Present implementation options one at a time** with pros/cons/recommendation
2. **Tests are integrated** - Every implementation task includes its tests
3. **Atomic tasks** - Each task is self-contained and testable

### Task Structure

Each task should follow this format:

```markdown
### Task N: [Title]

**Files to modify/create**:
- `path/to/file.cs` - [what changes]

**Implementation**:
1. [Step 1]
2. [Step 2]

**Tests** (implement alongside):
- [ ] Unit test: [description]
- [ ] Integration test: [description] (if applicable)

**Acceptance criteria**:
- [ ] [Criterion 1]
- [ ] [Criterion 2]
```

### Plan Template

Use this template for the final plan:

```markdown
# Feature Plan: [Feature Name]

## Overview
[Brief description of the feature]

## Requirements Summary
[Key requirements gathered during understanding phase]

## Architecture Decisions
[Key decisions made with rationale]

## Implementation Tasks

### Task 1: [Title]
[Task details with integrated tests]

### Task 2: [Title]
[Task details with integrated tests]

...

## Risks and Mitigations
[Identified risks and how to handle them]

## Out of Scope
[Explicitly excluded items]
```

## Phase 4: Finalizing

**Goal**: Get approval and save the plan.

1. **Present the complete plan** to the user
2. **Ask for feedback or approval**:
   - Use AskUserQuestion with options: "Approve", "Request changes", "Need more details"
3. **If feedback provided**:
   - Address specific concerns
   - Update the plan
   - Present again
   - Repeat until approved
4. **Once approved** (never before):
   - Create the feature folder `.claude/features/[feature-name]/`
   - Save plan to `.claude/features/[feature-name]/[feature-name]-plan.md`
   - Confirm save location with user

### Saving the Plan

Each feature gets its own folder under `.claude/features/`. The folder holds the plan and, later, every implementation file related to that feature (see `implement-plan`).

```
.claude/features/
└── [feature-name]/
    ├── [feature-name]-plan.md             # written here, on approval
    └── [feature-name]-implementation.md   # created later by implement-plan
```

Naming convention (folder and files):
- Lowercase
- Hyphens for spaces
- Plan file suffixed with `-plan.md`
- Example: `.claude/features/user-authentication/user-authentication-plan.md`

If a folder for the feature already exists (for example, re-planning), update the plan file in place rather than creating a second folder.

## Anti-patterns to Avoid

- Making assumptions without asking
- Batching multiple questions together
- Presenting options without pros/cons
- Leaving tests as a final standalone phase
- Proceeding without explicit approval
- Skipping exploration phase