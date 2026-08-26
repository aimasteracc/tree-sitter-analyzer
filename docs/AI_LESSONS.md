# AI Lessons

## 2026-08 — Remove the legacy compact wire format

### Context

A pull request proposed switching the MCP default from the legacy compact wire
format to JSON. The first review rejected that change because repository
instructions still described the compact format as a user-locked default. A
later user decision explicitly changed the direction: remove that format
completely and use JSON everywhere.

### Lessons learned

1. **Closing a pull request is not completing a migration.** The rejected PR
   was only a partial implementation. README files, CLI schemas, MCP defaults,
   compatibility tests, examples, workflow lists, and codemaps still formed a
   second contract. Completion requires a repository-wide search and a runtime
   verification pass.
2. **Repository instructions are part of the product contract.** A locked
   design note in `CLAUDE.md` contradicted the new user decision. When the
   decision changes, update the instruction, implementation, tests, and docs
   together; leaving the old rule makes future agents undo the migration.
3. **Do not hide an absent implementation behind compatibility shims.** A
   pass-through function that still has the old format's name or schema keeps
   stale API surface alive. Removing the encoder also requires removing its
   flags, enum values, response fields, fixtures, and tests.
4. **CI failures must be separated from feature changes.** The dependency and
   Actions PRs exposed pre-existing flaky benchmark and Python-version contract
   failures. Those were fixed in a separate `fix/ci-runtime-contracts` change
   before re-evaluating the dependency work, rather than masking failures in
   Dependabot branches.
5. **Verify the layer users actually call.** Contract tests that only exercise
   inner tools missed envelope duplication and default drift. MCP boundary
   behavior and CLI behavior need direct JSON assertions.

### Required guardrail

For future format migrations, the definition of done is: no active source,
configuration, schema, test, example, codemap, or README references the removed
format; all MCP and CLI defaults agree; focused tests pass; and a final
case-insensitive repository search is reviewed. Historical changelog and
postmortem entries may remain only when clearly marked as historical.
