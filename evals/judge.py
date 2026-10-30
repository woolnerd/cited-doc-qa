"""LLM-as-judge prompts for answer faithfulness and correctness.

The judge is a stronger model than the one generating answers, called at
temperature 0. Its scores are a rough signal for comparing runs, not ground
truth: a small dataset and a model grader both add noise.
"""

import json
import re
from typing import Any, Literal, cast

from openai import OpenAI

Verdict = Literal["correct", "partial", "incorrect"]

FAITHFULNESS_PROMPT = """You are checking whether an answer is supported by the context it was generated from.

<context>
{context}
</context>

<answer>
{answer}
</answer>

List every factual claim the answer makes about the documents. Skip citations,
greetings, and statements that the documents do not cover something. For each
claim, decide whether the context directly supports it.

Respond with JSON only:
{{"claims": [{{"claim": "...", "supported": true}}]}}"""

CORRECTNESS_PROMPT = """You are grading an answer against a reference answer.

<question>
{question}
</question>

<reference_answer>
{reference}
</reference_answer>

<answer>
{answer}
</answer>

Grade the answer:
- "correct": states the key facts in the reference, with nothing that contradicts it.
- "partial": some key facts are right but others are missing or wrong.
- "incorrect": misses or contradicts the key facts. If the reference says the
  documents do not cover the question, any answer that invents specifics is incorrect.

Extra detail beyond the reference is fine if it does not contradict it.

Respond with JSON only:
{{"verdict": "correct", "reason": "one sentence"}}"""


def format_context(chunks: list[dict[str, Any]]) -> str:
    """Number the chunks the same way the answer prompt does."""
    return "\n\n".join(
        f"[{i}] (Source: {c['document_name']})\n{c['content']}"
        for i, c in enumerate(chunks, start=1)
    )


def parse_json_object(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response, tolerating code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in judge response: {text[:200]!r}")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Judge response JSON is not an object")
    return parsed


def faithfulness_score(parsed: dict[str, Any]) -> float | None:
    """Share of claims marked supported, or None when the answer made no claims."""
    claims = parsed.get("claims") or []
    if not claims:
        return None
    supported = sum(1 for c in claims if c.get("supported") is True)
    return supported / len(claims)


def parse_verdict(parsed: dict[str, Any]) -> Verdict:
    """Validate the correctness verdict."""
    verdict = parsed.get("verdict")
    if verdict not in ("correct", "partial", "incorrect"):
        raise ValueError(f"Unexpected verdict: {verdict!r}")
    return cast(Verdict, verdict)


class Judge:
    """Thin client for the two judge prompts."""

    def __init__(self, client: OpenAI, model: str):
        self.client = client
        self.model = model

    def _ask(self, prompt: str) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json_object(response.choices[0].message.content or "")

    def faithfulness(
        self, answer: str, context: list[dict[str, Any]]
    ) -> dict[str, Any]:
        parsed = self._ask(
            FAITHFULNESS_PROMPT.format(context=format_context(context), answer=answer)
        )
        return {"score": faithfulness_score(parsed), "claims": parsed.get("claims", [])}

    def correctness(self, question: str, reference: str, answer: str) -> dict[str, Any]:
        parsed = self._ask(
            CORRECTNESS_PROMPT.format(
                question=question, reference=reference, answer=answer
            )
        )
        return {"verdict": parse_verdict(parsed), "reason": parsed.get("reason", "")}
