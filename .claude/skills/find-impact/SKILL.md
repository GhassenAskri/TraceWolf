---
name: find-impact
description: Analyzes the blast radius of a change in a .NET project using LSP. Use when the user wants to understand the impact of modifying a symbol, method, class, or interface in C# code.
---

# .NET Impact Analysis Workflow

Analyze the full blast radius of a code change by leveraging the C# LSP plugin tools.

## Input

The user provides one of:
- A symbol name (class, method, interface, property)
- A file path and line number
- A description of the planned change

## Workflow

### Step 1: Identify the target symbol

If the user gave a file and line, use `lsp_hover` to identify the symbol. If they gave a name, use `lsp_workspace_symbols` to locate it.

### Step 2: Find all references

Use `lsp_find_references` on the target symbol to identify every call site, usage, and dependency across the solution.

### Step 3: Analyze the symbol type and .NET-specific patterns

Based on what the symbol is, perform targeted analysis:

- **Interface method:** Use `lsp_find_references` on the interface definition, then `lsp_goto_definition` on each implementation to find all concrete implementations that would need updating.
- **Class/Service:** Search `Program.cs` or DI registration files (look for `AddScoped`, `AddTransient`, `AddSingleton`) to understand how this class is wired up and what depends on it via injection.
- **Data Model / DTO:** Check for DTOs, EF Core `DbSet<T>` declarations, AutoMapper profiles, and SQL column references that would break if the model shape changes.
- **Base class / Virtual method:** Use `lsp_find_references` to find all derived classes and overrides.

### Step 4: Check diagnostics

For each impacted file found in Steps 2-3, use `lsp_diagnostics` to detect any existing compiler errors or warnings that may interact with the change.

### Step 5: Classify and report

For every reference found, classify it into one of three categories:

- **Breaking** - Would cause compiler errors (e.g., method signature changes, removed members, changed return types, interface contract violations)
- **Behavioral** - Would compile but change runtime behavior (e.g., altered return values, changed validation logic, reordered operations, different default values)
- **Safe** - References that are unaffected by the change (e.g., read-only usages when only adding a new optional parameter)

## Output Format

Present the report as follows:

```
## Impact Analysis: [Symbol Name]

### Summary
- Total references found: N
- Files affected: N
- Breaking: N | Behavioral: N | Safe: N

### Breaking Changes
| File | Line | Reference | Reason |
|------|------|-----------|--------|
| path/to/File.cs | 42 | MethodCall() | Signature mismatch |

### Behavioral Changes
| File | Line | Reference | Reason |
|------|------|-----------|--------|
| path/to/Other.cs | 15 | ProcessData() | Return value semantics changed |

### Safe References
| File | Line | Reference |
|------|------|-----------|
| path/to/Safe.cs | 10 | ReadOnlyUsage |

### DI Registration
- Registered as: `AddScoped<IService, Service>()` in Program.cs:23

### Recommendations
- [Actionable suggestions based on findings]
```

## Guidelines

- Always start from LSP data, not assumptions
- If `lsp_find_references` returns no results, verify the symbol exists with `lsp_workspace_symbols`
- For large result sets, group by project/namespace in the output
- Flag any circular dependencies discovered during the analysis
- If the LSP server is not running or returns errors, **do not fall back to text search**. Instead, prompt the user that the LSP server is not running and attempt to output the root cause (e.g., missing `csharp-ls` installation, no `.sln` file found, SDK version mismatch, or server crash logs)
