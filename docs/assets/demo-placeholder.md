# Demo GIF Placeholder

This is a placeholder for the demo.gif file.

## GIF Specification

- **Duration**: 15-30 seconds
- **Resolution**: 800x600 or higher
- **Content**: AI integration scenario with SMART workflow

## Recommended Recording Steps

1. Set project path with AI assistant
2. Analyze file structure
3. Extract code snippets

## Alternative: CLI Demo

- Use `asciinema` or `terminalizer` to record terminal
- Show analysis of a large file with structure table output
- For a repeatable before/after story, run:
  ```bash
  uv run python examples/agent_workflow_comparison_demo.py
  uv run python examples/agent_workflow_comparison_demo.py --format json
  uv run python examples/agent_workflow_comparison_demo.py --format cast > docs/assets/agent-workflow-comparison.cast
  ```
  This compares reading all of `examples/BigService.java` with the SMART workflow
  path that retrieves only the target method context. The `cast` format emits
  asciinema v2 JSONL, so the demo evidence can be regenerated without an
  interactive recording step. A checked-in sample lives at
  [agent-workflow-comparison.cast](agent-workflow-comparison.cast).

## How to Create

1. Install recording tool:
   ```bash
   # Option 1: asciinema
   brew install asciinema  # macOS
   
   # Option 2: terminalizer
   npm install -g terminalizer
   ```

2. Record terminal session:
   ```bash
   # With asciinema
   asciinema rec demo.cast

   # Recommended command to record
   uv run python examples/agent_workflow_comparison_demo.py

   # Non-interactive asciinema v2 payload
   uv run python examples/agent_workflow_comparison_demo.py --format cast > demo.cast
   
   # With terminalizer
   terminalizer record demo
   ```

3. Convert to GIF:
   ```bash
   # From asciinema
   docker run --rm -v $PWD:/data asciinema/asciicast2gif demo.cast demo.gif
   
   # From terminalizer
   terminalizer render demo
   ```

4. Place the resulting `demo.gif` in this directory.

---

*This placeholder file can be deleted once the actual demo.gif is created.*
