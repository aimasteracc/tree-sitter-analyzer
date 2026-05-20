# Promotion Checklist (GROW-2, GROW-3)

Things humans need to do that can't be automated from inside the
repo. Tracked here so future contributors have a one-stop pre-launch
list.

## GROW-2 — Inline GIF / video demo

Status: 🔴 open (needs recording).

`docs/assets/agent-workflow-comparison.cast` already exists as an
asciinema recording of the headline workflow. To finish the hero:

1. Pin the cast to the current CLI: re-run the demo against `main`
   and overwrite the cast.
2. Convert to GIF with `agg` (preferred — pure Rust, no dep on
   `ffmpeg`):

   ```bash
   brew install agg          # macOS
   agg docs/assets/agent-workflow-comparison.cast docs/assets/hero.gif \
       --font-size 14 --speed 1.5
   ```

3. Add the GIF to `README.md` directly below the existing hero table:

   ```markdown
   ![Tree-sitter Analyzer in action](docs/assets/hero.gif)
   ```

4. Commit. Done.

Why this matters: top-tier OSS READMEs (ruff, ast-grep, ripgrep) all
lead with one screen of value + one moving picture. The current README
hero table (PERF-5) is already a strong textual hook, but agentic-AI
audiences scan visuals first.

## GROW-3 — MCP discovery surface listings

Status: 🔴 open (requires human submissions to external sites).

Submit the package to each of these surfaces. Each submission is
~30 minutes of work; spread across weeks to avoid review load
contention.

| Surface | Submission link | Why it matters |
|---|---|---|
| **mcp.so** | https://mcp.so/submit | The default discovery surface; "MCP" + "code analysis" hits here first. |
| **PulseMCP** | https://www.pulsemcp.com/submit | Slightly more curated; appears in search results from AI clients. |
| **TensorBlock awesome-mcp-servers** | PR against [`docs/code-analysis--quality.md`](https://github.com/TensorBlock/awesome-mcp-servers/blob/main/docs/code-analysis--quality.md) | The "awesome-list" category readers trust for shortlists. |
| **Anthropic MCP directory** | https://www.anthropic.com/news (watch for the directory open-call) | First-party; when Anthropic's own example recommends an MCP server, it's usually one of theirs. Want to be one of the first community entries. |

What to include in each submission:

- Package name: `tree-sitter-analyzer`
- One-line description: "23 MCP tools for AI code-understanding —
  17 languages, TOON output cuts tokens ~73%, no graph DB required."
- Install: `uvx tree-sitter-analyzer`
- Repository link: this repo's GitHub URL
- The screencast / GIF from GROW-2 once it lands

After each submission, log the date and reviewer response in
`docs/PROMOTION_LOG.md` so we don't double-submit and we can measure
referral traffic against star count over time.

## GROW-1 — README hero (✅ done in this audit)

PERF-5 / GROW-1 closed: `README.md` now leads with the 23 tools, 17
languages, and 73% TOON token reduction. See
[AUDIT_FINDINGS_2026-05-20.md](AUDIT_FINDINGS_2026-05-20.md).

## How this feeds back into the autonomous loop

Each promotion outcome (star delta, downstream stargazer activity,
GitHub Trending appearance) should be logged in
`PROMOTION_LOG.md` and stored in ruflo memory under namespace
`project-context` so future audit passes can correlate "did this
sprint move the needle".
