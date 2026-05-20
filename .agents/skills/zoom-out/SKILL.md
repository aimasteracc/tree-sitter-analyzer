---
name: zoom-out
description: Tell the agent to zoom out and give broader context or a higher-level perspective. Use when you're unfamiliar with a section of code or need to understand how it fits into the bigger picture.
disable-model-invocation: true
---

I don't know this area of code well. Go up a layer of abstraction. Give me a map of all the relevant modules and callers, using the project's domain glossary vocabulary.

## Acceptance Criteria

- [ ] The answer starts one layer above the confusing code, not inside local details.
- [ ] Relevant modules, callers, data flow, and ownership are mapped in plain language.
- [ ] Project domain vocabulary is used when available.
- [ ] The final paragraph names the next concrete file, symbol, or question to inspect.
