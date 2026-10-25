---
name: challenge-plan
description: Challenges implementation plans as a devil's advocate, identifying technical and functional gaps, wrong assumptions, and risks. Use when you have a plan and want to validate it before implementation.
---

# Challenging Implementation Plans

A methodical skill for stress-testing plans by identifying gaps, assumptions, and risks one at a time.

## Workflow

Copy this checklist:

```
Plan Challenge Progress:
- [ ] Phase 1: Analysis - Understand the plan thoroughly
- [ ] Phase 2: Challenge - Identify issues one at a time
- [ ] Phase 3: Resolution - Address each challenge with user
- [ ] Phase 4: Update - Revise plan with agreed changes
```

## Phase 1: Analysis

**Goal**: Deeply understand the plan before challenging it.

1. Read the entire plan carefully
2. Identify key components:
   - Requirements and scope
   - Architecture decisions
   - Implementation tasks
   - Test coverage
   - Dependencies and integrations

3. Note areas to investigate:
   - Technical assumptions
   - Functional completeness
   - Edge cases
   - Security implications
   - Performance considerations
   - Error handling
   - Migration/rollback strategy

**Do NOT proceed until analysis is complete.**

## Phase 2: Challenge

**Goal**: Identify potential issues systematically.

### Challenge Categories

1. **Technical Challenges**
   - Architecture flaws
   - Technology mismatches
   - Performance bottlenecks
   - Scalability concerns
   - Security vulnerabilities
   - Missing error handling

2. **Functional Challenges**
   - Missing requirements
   - Incomplete edge cases
   - Inconsistent behavior
   - User experience gaps
   - Integration issues

3. **Assumption Challenges**
   - Unvalidated assumptions
   - Implicit dependencies
   - Missing preconditions
   - Unclear success criteria

### Rules

1. **One challenge at a time** - Never batch multiple challenges
2. **Use AskUserQuestion tool** for structured responses
3. **Always include "Keep as-is" option** - The plan may be correct
4. **Wait for resolution** before presenting next challenge
5. **Track all challenges** - Maintain a running list of addressed items

## Phase 3: Resolution

**Goal**: Work through each challenge with the user.

### Challenge Format

Present each challenge using this structure:

```
**Challenge #N**: [Category - Technical/Functional/Assumption]

**Issue**: [Clear description of the potential problem]

**Why this matters**: [Impact if not addressed]

**Current plan states**: [Quote relevant section]

**Options**:

1. **[Fix Option A]** (Recommended if applicable)
   - Change: [What to modify]
   - Impact: [How it affects the plan]

2. **[Fix Option B]**
   - Change: [What to modify]
   - Impact: [How it affects the plan]

3. **Keep as-is**
   - Rationale: [Why current approach might be acceptable]
   - Risk accepted: [What risk remains]
```

### Using AskUserQuestion

```
Question: "How should we address [issue]?"
Header: "Challenge #N"
Options:
- Label: "[Option A name]", Description: "[Brief description]"
- Label: "[Option B name]", Description: "[Brief description]"
- Label: "Keep as-is", Description: "Accept current approach with noted risk"
```

### Resolution Tracking

Maintain a summary after each resolved challenge:

```
## Challenges Addressed

| # | Category | Issue | Resolution |
|---|----------|-------|------------|
| 1 | Technical | [Issue] | [Chosen option] |
| 2 | Functional | [Issue] | [Chosen option] |
```

## Phase 4: Update

**Goal**: Revise the plan with all agreed changes.

1. **Compile all resolutions** that require plan changes
2. **Update each affected section**:
   - Mark changes clearly
   - Preserve original context
   - Add rationale for changes

3. **Present updated plan** with change summary:

```
## Changes Made

1. [Section]: [What changed] - Based on Challenge #N
2. [Section]: [What changed] - Based on Challenge #N

## Risks Accepted

1. [Risk from "Keep as-is" decisions]
```

4. **Ask for final approval** before saving

## Common Challenges to Check

### Technical

- [ ] Database schema handles all relationships correctly?
- [ ] API contracts are complete and consistent?
- [ ] Error states are properly handled?
- [ ] Concurrency/race conditions addressed?
- [ ] Caching strategy appropriate?
- [ ] Logging/observability sufficient?

### Functional

- [ ] All user stories covered?
- [ ] Edge cases identified?
- [ ] Validation rules complete?
- [ ] Authorization checked at all levels?
- [ ] Backward compatibility maintained?

### Assumptions

- [ ] External service availability assumed?
- [ ] Data format assumptions validated?
- [ ] Performance expectations realistic?
- [ ] Dependencies available and compatible?

## Anti-patterns to Avoid

- Challenging everything (focus on real risks)
- Batching multiple challenges together
- Not providing "Keep as-is" option
- Challenging without understanding context
- Nitpicking minor style preferences
- Proceeding without explicit resolution