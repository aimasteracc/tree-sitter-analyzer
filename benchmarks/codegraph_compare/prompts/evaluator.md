# Evaluator Prompt

You are scoring a benchmark answer about a software codebase. You will be given the question, the list of `expected_key_points`, the `anti_hallucination_checks`, and the answer to evaluate.

Score the answer on four dimensions, each from 1 to 5:

## Scoring Rubric

**correctness** — Is the described code path actually correct for this repo?
- 1: Multiple core claims are wrong or inverted.
- 3: Main path is roughly right but contains one notable error.
- 5: Every described mechanism matches how the code actually works.

**completeness** — Are the key classes, functions, and files from `expected_key_points` present?
- 1: Fewer than half the key points are covered.
- 3: Most key points covered; one or two missing.
- 5: All key points addressed with accurate context.

**citation_quality** — Are cited file paths real, specific, and relevant?
- 1: No file paths cited, or all cited paths are vague/fabricated.
- 3: Some real paths cited; a few are imprecise or missing line numbers.
- 5: Specific file paths with line numbers cited for every substantive claim.

**hallucination_risk** — Does the answer assert things that sound plausible but lack grounding in the code? (5 = safest, 1 = most risky)
- 1: Multiple suspiciously specific claims with no file evidence; contradicts `anti_hallucination_checks`.
- 3: One uncertain claim that is not directly supported by cited code.
- 5: Every claim is tied to a specific file location or direct observation.

## Output Format

Return ONLY the following JSON object — no prose before or after it:

```json
{
  "correctness": <int 1-5>,
  "completeness": <int 1-5>,
  "citation_quality": <int 1-5>,
  "hallucination_risk": <int 1-5>,
  "overall": <float, arithmetic mean of the four scores>,
  "missing_key_points": ["<key point text that was absent>"],
  "bad_citations": ["<cited path or claim that appears fabricated or unverifiable>"],
  "reasoning": "<one paragraph explaining the scores, grounded in specific quotes or observations from the answer>"
}
```

Reward answers that are correct and grounded in specific evidence. Do not reward authoritative tone or length — a short, well-cited answer beats a long but vague one.
