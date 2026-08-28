# Working Agreement

This repository is maintained through a Manager/Worker workflow.

## Roles and normal workflow

- A Worker implements a scoped task, runs proportionate verification, creates a local commit, and reports the exact commit SHA.
- The Manager reviews the exact diff and the reported verification before directing further work.
- The user controls push, pull-request creation, and merge operations unless a later instruction explicitly grants that authority.

Every Worker engineering task must begin with `Recommended reasoning: Terra 高`, `Recommended reasoning: Terra 中`, or `Recommended reasoning: Terra 低`, plus a short reason for that level.

Every completion report must include the task identifier, starting SHA, resulting commit SHA, branch, `git status`, whether anything was pushed, verification results, and risks or open decisions.

## Safety and product boundaries

- Never store or print API tokens in code, documentation, logs, commits, or reports.
- Do not read Dota process memory, inject into the game, automate player input, or control gameplay.
- Keep providers, scoring semantics, and request budgets within the explicitly authorized task scope.

## Command convention

User-facing PowerShell, Git, or Python command blocks begin from the repository directory:

```powershell
cd 'C:\Users\22908\Documents\ChatGPT\野生dota+\dota-support-draft'
```
