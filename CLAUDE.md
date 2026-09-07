## AEGIS Team Ownership Rules

### Cross-owner changes
- Vikash is System Architect + Integration Lead.
- Sahil owns Network Simulation + Digital Twin.
- Yyash owns AI Diagnosis + Recovery Planner.
- Hrishi owns Safety Engine + Frontend.

If you discover a bug, architectural conflict, contract mismatch, or improvement opportunity inside another teammate's core implementation:
- DO NOT modify that teammate's core implementation yourself.
- Report the issue to Vikash.
- Explain exactly what should be communicated to the owning teammate.
- Let the owning teammate decide and implement the change.
- Vikash may inspect/review code, integrate branches, resolve integration conflicts, modify agreed shared contracts, write adapters/glue, and make integration-layer changes.
- Do not silently rewrite, replace, or take ownership of another teammate's core implementation.

### Git / GitHub restrictions
- All Git and GitHub operations are manual and owned by Vikash.
- NEVER commit.
- NEVER push or pull.
- NEVER fetch.
- NEVER merge or rebase.
- NEVER reset.
- NEVER create, delete, or switch branches.
- NEVER create pull requests.
- NEVER modify remotes, Git config, GitHub settings, repository history, or attribution.
- NEVER add AI attribution to commits or repository files.
- Read-only Git inspection is allowed:
  - git status
  - git log
  - git branch
  - git diff
  - git show
  - git rev-parse
  - git ls-tree
  - git merge-base

When a logical implementation phase is complete:
1. Stop modifying code.
2. Report what was changed.
3. Report tests run and their result.
4. Tell Vikash the work is ready for manual review/commit.
5. Do not commit or push.
