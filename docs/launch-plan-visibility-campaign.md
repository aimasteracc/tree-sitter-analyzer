# Coordinated Visibility Campaign: Launch Plan

**Scope:** tree-sitter-analyzer v1.29.0 visibility push — MCP Registry listing,
article publications, and community seeding.

**Calendar dates:** TBD. Exact timing depends on Phase 0/1/2 completion and
human operator availability. **This is a task for the human operator to schedule
after Phase 2 prep is confirmed ready.** Do not launch until:
- `server.json` is submitted and live on registry.modelcontextprotocol.io (Step 14).
- At least one article is published externally (Step 21 or 22).
- The human has confirmed the 24-48 hour posting window.

---

## (a) Pre-Announcement to Existing PyPI Users

**Audience:** ~5,341 monthly PyPI downloads (as of campaign planning, 2026-07-10).

**Channel:** GitHub Releases page + README announcement block (not an email blast;
we have download counts but not email addresses).

**Timing:** 48-72 hours before the main posting window opens. This gives existing
users time to update, test, and become word-of-mouth amplifiers during the launch
window.

**Message draft:**

---

**Subject / Release title:** tree-sitter-analyzer v1.29.0 — now on MCP Registry

Hi everyone,

tree-sitter-analyzer v1.29.0 is now listed on the official MCP Registry
(`registry.modelcontextprotocol.io`). If you are using TSA with Claude Code or
another MCP-compatible agent, you can now discover and install it directly from
the registry.

**What's new in this campaign:**
- Official MCP Registry listing with namespace `io.github.aimasteracc/tree-sitter-analyzer`.
- Published articles on the cross-language mis-wire problem and the security
  boundary design — links below.
- No changes to the tool surface or behavior in v1.29.0.

**Install:**
```bash
uvx --from tree-sitter-analyzer tsa-mcp
```

**Run the mis-wire audit on your own repo:**
```bash
uvx --from tree-sitter-analyzer miswire-audit . --card
```

Share the card output if you find unexpected mis-wires — it helps us improve
language compatibility detection.

Thanks for using TSA.
— @aimasteracc

---

## (b) 24-48 Hour Coordinated Posting Plan

**Style reference:** AFFiNE's viral open-source launch — coordinated, same-window
postings across multiple channels to maximize cross-amplification. The goal is to
hit the front pages of multiple communities within the same 24-48 hour window,
creating the appearance of simultaneous organic discovery.

**Target window:** One weekday (Tuesday-Thursday preferred; avoid Monday and
Friday). Start at 09:00-11:00 UTC to catch both European morning and US East
Coast pre-lunch. Calendar date: **[human decides]**.

### Channel order and timing

| Hour | Channel | Post type | Content |
|---|---|---|---|
| H+0 | Hacker News | Show HN | Short demo, link to polyglot-miswire-article |
| H+1 | Reddit r/MachineLearning | Link + comment | Cross-language mis-wire problem framing |
| H+2 | Reddit r/programming | Link | AST oracle shootout article |
| H+3 | dev.to | Full article | polyglot-miswire-article (publish) |
| H+6 | X / Twitter | Thread | Key stats + --card demo GIF/screenshot |
| H+12 | MCP Discord (if available) | Announcement | Registry listing + article links |
| H+24 | Reddit r/LocalLLaMA | Comment in relevant thread OR new post | Security posture article |

### Hacker News Show HN draft

**Title:** Show HN: Tree-sitter Analyzer — a cross-language-safe MCP code graph (0 mis-wires on 4 polyglot repos)

**Body:**

```
I built tree-sitter-analyzer to solve a problem I kept hitting with AI-assisted
refactoring in polyglot repos: the call graph would confidently wire Python callers
to Swift methods because they shared a name like "sorted()".

TSA gates every call-graph edge through a language-compatibility check
(Python cannot call Swift, Go has no relationship to Kotlin, etc.) before binding.
Calls that can't be resolved cross-language are reported as "unknown" rather than
mis-wired.

On four real polyglot open-source repos (tokenizers, ruff, polars, gin), TSA
produces 0 cross-language mis-wires vs hundreds from name-only indexes.

- GitHub: https://github.com/aimasteracc/tree-sitter-analyzer
- MCP Registry: io.github.aimasteracc/tree-sitter-analyzer
- Article with repro: [link to polyglot-miswire-article]
- Install: uvx --from tree-sitter-analyzer tsa-mcp

Happy to discuss the language-compatibility predicate design or the gauntlet
benchmark methodology.
```

### Reddit r/programming post draft

**Title:** We measured how many Python callers a code-intelligence tool wires to a Swift method. The answer was 299.

**Body:**

```
Code-intelligence tools for AI agents often use name-only call graph resolution:
find a definition with the same name as the call site, wire them together,
done. In a single-language codebase, this works fine. In a polyglot repo (Rust +
Python, Go + TypeScript, etc.), it creates mis-wires.

I documented a concrete example: Python's builtin sorted() is called hundreds of
times across a codebase that also happens to have one Swift file defining a
sorted() method. A name-only index wires all 299 Python callers to the Swift
node. The AST doesn't support any of those edges. Python can't call Swift.

Full writeup with one-command repros for both tools:
[link to polyglot-miswire-article]

The tool I built to fix this: https://github.com/aimasteracc/tree-sitter-analyzer
```

### X / Twitter thread draft

```
Tweet 1/5:
I measured how many Python callers one code-intelligence tool wires to a Swift
method just because they share a name. The answer: 299.

Here is what happens when name-only call graph resolution meets a polyglot repo.
(thread)

Tweet 2/5:
Python's builtin sorted() is called ~300x in a codebase that also has a
.swift file defining a sorted() method.

A name-only index finds one "sorted" node. Wires all Python callers to it.
The AST doesn't support any of those edges. Python can't call Swift.

Tweet 3/5:
The effect at scale:
- huggingface/tokenizers: 1,259 potential mis-wires (7.71% of call edges)
- astral-sh/ruff: 7,557 potential mis-wires (4.03% of call edges)
- pola-rs/polars: 9,016 potential mis-wires (3.38% of call edges)

These are genuine cross-language collisions no "smart" name-only index avoids.

Tweet 4/5:
tree-sitter-analyzer gates every edge through a languages_compatible() check.
Python -> Swift: rejected (unknown, not mis-wired).

Result: 0 cross-language mis-wires on all four polyglot repos above.

Run it on your repo:
uvx --from tree-sitter-analyzer miswire-audit . --card

Tweet 5/5:
Full writeup with one-command repros:
[link to polyglot-miswire-article]

MCP Registry: io.github.aimasteracc/tree-sitter-analyzer
GitHub: https://github.com/aimasteracc/tree-sitter-analyzer
```

### dev.to article metadata

**Tags:** `mcp`, `ai`, `llm`, `tooling`
**Series:** (none for first post; consider "Code intelligence for AI agents" series)
**Canonical URL:** (set to GitHub Pages or the article URL if published elsewhere first)
**Cover image:** A side-by-side diff showing "299 Python callers -> Swift" vs "392 unknown"

---

## Reference: AFFiNE Viral Case Study Parallels

AFFiNE (open-source Notion alternative) achieved viral launch by:
1. Simultaneous postings across HN, Reddit, and Product Hunt within a 24-hour window.
2. A single memorable, concrete claim in the headline ("Notion alternative built
   with AI-first architecture").
3. Pre-warming an existing community (their GitHub Discussions) before the
   public launch.
4. Having reproducible demos ready — visitors could try it immediately.

The parallels for this campaign:
1. Same coordinated-window approach (see channel order above).
2. Concrete, reproducible claim: "299 Python callers wired to a Swift method."
3. Pre-warming: the GitHub Releases announcement to existing PyPI users (section a above).
4. Reproducible demo: `uvx --from tree-sitter-analyzer miswire-audit . --card` — runs in seconds on any polyglot repo.

---

## Human Operator Checklist

Before opening the posting window, confirm:

- [ ] `server.json` submitted and live at `registry.modelcontextprotocol.io`
- [ ] `polyglot-miswire-article.md` published externally (dev.to or equivalent)
- [ ] GitHub Releases pre-announcement posted (48-72h before window)
- [ ] HN Show HN draft final-reviewed for accuracy (no unattributable statistics)
- [ ] Calendar slot confirmed (Tuesday-Thursday, 09:00-11:00 UTC)
- [ ] `miswire-audit . --card` demo output screenshot/GIF prepared for X post
- [ ] Exact calendar date entered here: **[TBD — human decides]**

---

*This document is a [HUMAN] deliverable. The AI has prepared the campaign plan
and all draft copy. Execution — posting, submitting, publishing — is the human
operator's responsibility.*
