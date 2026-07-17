# Supervisor Guide — Orchestrating Tickets with Subagents

For whoever (or whichever compacted session of "me") is supervising this project next. This
records the orchestration method in use, what worked, what didn't, and why — so it doesn't need
to be rediscovered.

## The two phases, and who does them

**Phase 1 — Planning** (`/grill-me` → `/to-prd` → `/to-issues`, per ticket). Produces
`tickets/NN-name/{decisions.md,PRD.md,issues/README.md}` plus published GitHub issues. This phase
is pure documentation — no application code, no `src/` changes.

**Phase 2 — Implementation**. Writes the actual code for a ticket's published issues.

**Current method for Phase 2 (this is the change this doc records): one subagent per *ticket*,
not one subagent per *issue*.** The agent reads that ticket's `decisions.md`/`PRD.md` once and
then implements every issue for that ticket sequentially, in dependency order, inside one
continuous run. Earlier in this project one subagent was spawned per *issue* instead — it worked,
but every agent re-read the same ticket context from scratch, which wasted tokens on repeated
project/codebase orientation for issues that were really just facets of one coherent unit of work.
Grouping by ticket amortizes that cost across all of a ticket's issues.

## Why phase 1 and phase 2 must be separate agent invocations

Do not try to redirect a Phase 1 (planning) agent mid-task into also writing code, even by sending
it a follow-up message that says "now implement the issues you just created." **This will be
refused, and correctly so** — it's blocked by the framework's own permission system, not just the
agent's judgment. A message from the orchestrating session (or anything else in-thread) is not
treated as equivalent to the user's own consent for a scope change that big, and there is no way
to override that from inside the conversation. Multiple agents hit this independently and declined
to proceed, which is the framework working as intended, not a bug to route around.

**The fix:** always launch a *new* agent whose original brief already says "implement this," rather
than trying to expand an existing agent's brief after the fact. The new agent loses no context that
matters — everything it needs (`decisions.md`, `PRD.md`, the issue bodies, the current state of
`main`) is sitting in the repo, not trapped in the old agent's head.

## Per-ticket implementation agent: what to give it

- **One git worktree per ticket** (not per issue): `Memory-AI-issue<NN>` naming has been used for
  single-issue agents; for ticket-grouped agents, name it after the ticket, e.g.
  `Memory-AI-ticket04`, on a branch like `feat/04-hierarchy` (or per-issue branches within that
  worktree if you want each issue's PR to be separately reviewable — either works; the point is one
  *agent*, not one *worktree per issue*).
- Point it at `tickets/NN-name/PRD.md`, `decisions.md`, and `issues/README.md` and tell it to work
  through the issues **in the dependency order the issues/README.md already lays out**.
- Tell it explicitly: for each issue, implement → run full quality gates → **self-review pass** →
  **test-quality pass** → commit → push → PR (`Closes #<n>`) → wait for CI green → merge → move to
  the next issue in the same worktree/branch lineage (or a fresh branch off the just-merged main,
  agent's choice). The two passes in bold are mandatory gates *before* committing each issue, not
  optional extras — see below for exactly what to ask for.

### The two mandatory gates before committing each issue

Bake both of these into the per-ticket agent's brief, to run after the code for an issue is
written but before it's committed:

1. **Self-review pass.** Literally instruct the agent: *"Do a full thorough check on the code
   changes made for this issue, and if there are any bugs, errors, or edge cases, sort these out."*
   This is a deliberate second look at its own diff — not just "did it run once" — looking for
   logic errors, unhandled edge cases, off-by-one mistakes, and anything that would embarrass the
   agent if a human read the diff carefully.
2. **Test-quality pass, not just a green pytest run.** Instruct the agent: *"Make sure the new code
   for this issue is thoroughly covered by the project's tests (pytest), every case and edge case
   is fully tested, and that the tests are correct and not stateless — a passing test suite is not
   sufficient proof; the tests themselves must be verified as actually exercising real behavior."*
   Concretely this means the agent should sanity-check its own tests, e.g.: temporarily break the
   implementation (flip a condition, off-by-one a boundary) and confirm the relevant test fails —
   a test that passes both before and after a real behavior change is not testing anything. Also
   check for tests that assert on mocks/trivial return values without touching the actual code
   path, and for missing edge cases the acceptance criteria call for (empty input, boundary values,
   failure/malformed-input paths) — "it passed" is not the bar; "it would catch a real regression"
   is.

Only after both passes should the agent commit, push, and open the PR for that issue.
- Tell it to check `main` for the current state of any *cross-ticket* dependency before starting
  (e.g. ticket 09 needs ticket 08's `scheduling.py` — if it's not there yet, the agent should say so
  and stop rather than build throwaway stand-ins). This has happened multiple times and agents have
  handled it well by asking rather than guessing.

## Hard-won operational details

- **Branch protection is `strict: true`** (status checks must run against the *current* main
  before merge is allowed). With several agents merging in parallel, branches go stale constantly.
  Every agent needs the retry loop baked into its brief: if `gh pr merge` fails or CI looks stale,
  `git fetch origin && git merge origin/main` (conflicts are rare since ticket-scoped work touches
  disjoint files), push, re-wait for CI, retry the merge. Repeat as needed.
- **The shared pre-commit hook.** `.git/hooks/pre-commit` is one file shared by *every* worktree —
  it is not per-worktree. It bakes in an absolute path to whichever worktree's `.venv` last ran
  `pre-commit install`. If that worktree is later deleted (e.g. after its work merges and you clean
  up), the hook breaks for every other worktree still running. **Rule: never run
  `pre-commit install` from inside a per-ticket/per-issue worktree.** Only the main worktree
  (`/Users/dionfernandes/Projects/Memory-AI-project/Memory-AI`) should ever install the hook,
  because it's the one worktree guaranteed not to be torn down. If an agent reports `pre-commit`
  is broken, the fix is to run `uv run pre-commit install` from the main worktree — that repoints
  the shared hook at a stable venv.
- **Worktree cleanup.** Once a ticket/issue's branch is merged, its worktree can be removed
  (`git worktree remove <path>`) — but only after confirming nothing else's pre-commit hook still
  points at its venv (see above), and only when its `git status` is clean.
- **Dependency order across tickets still matters for Phase 2, even though Phase 1 doesn't care
  about it.** Planning agents can run fully in parallel regardless of ticket dependency order,
  because they only write docs. Implementation agents cannot — a ticket-04 agent building routes
  that depend on ticket-03's `current_user` will produce broken/unreviewable code if ticket 03's
  code hasn't actually landed on `main` yet. Check `src/memory_ai/` on current `main` before
  dispatching an implementation agent, not just the issue tracker.

## Quick status check commands

```
gh issue list --repo dionferns/Memory-AI --state open --limit 50
gh pr list --repo dionferns/Memory-AI --state open
gh pr list --repo dionferns/Memory-AI --state merged --limit 30 --json number,title,mergedAt
git ls-tree -r origin/main --name-only | grep '^src/memory_ai'
```

## Summary of the change this doc records

Old: one subagent per GitHub issue → correct, but re-derives ticket context every time.
New: one subagent per ticket, working through that ticket's issues sequentially → same
correctness, less redundant context-loading, still one PR-per-issue for reviewability.
