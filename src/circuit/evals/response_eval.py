from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from circuit.tokenizer import count_tokens_from_text, truncate_text_to_max_tokens


FORBIDDEN_PATTERNS = [
    re.compile(r"<SSN>", re.IGNORECASE),
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+prior\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
]


@dataclass
class EvalResult:
    status: str
    output_text: str
    token_count: int


def _extract_response_format(payload: dict[str, Any]) -> str | None:
    response_format = payload.get("response_format")
    if not isinstance(response_format, dict):
        return None
    return response_format.get("type")


def _check_json_if_required(payload: dict[str, Any], text: str) -> str | None:
    response_format_type = _extract_response_format(payload)
    if response_format_type != "json_object":
        return None

    try:
        parsed = json.loads(text)
    except Exception:
        return "failed_json"

    if not isinstance(parsed, dict):
        return "failed_json"

    return None


def _check_regex(text: str) -> str | None:
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return "flagged_regex"
    return None


def evaluate_response(
    *,
    payload: dict[str, Any],
    model: str,
    output_text: str,
) -> EvalResult:
    json_failure = _check_json_if_required(payload, output_text)
    if json_failure:
        return EvalResult(
            status=json_failure,
            output_text=output_text,
            token_count=count_tokens_from_text(model, output_text),
        )

    regex_failure = _check_regex(output_text)
    if regex_failure:
        return EvalResult(
            status=regex_failure,
            output_text=output_text,
            token_count=count_tokens_from_text(model, output_text),
        )

    requested_max_tokens = payload.get("max_tokens")
    if isinstance(requested_max_tokens, int) and requested_max_tokens > 0:
        token_count = count_tokens_from_text(model, output_text)
        if token_count > requested_max_tokens:
            truncated = truncate_text_to_max_tokens(
                model=model,
                text=output_text,
                max_tokens=requested_max_tokens,
            )
            return EvalResult(
                status="truncated_max_tokens",
                output_text=truncated,
                token_count=requested_max_tokens,
            )

    return EvalResult(
        status="pass",
        output_text=output_text,
        token_count=count_tokens_from_text(model, output_text),
    )