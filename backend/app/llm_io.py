"""Log Anthropic Messages API request/response bodies at INFO.

Base64 image payloads in requests are replaced with placeholders so logs stay readable.
Ported from sibling sof-agent.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List, Union

from anthropic import AsyncAnthropic

logger = logging.getLogger("ote.llm")

ContentPart = Union[str, List[Dict[str, Any]], Dict[str, Any]]


def _redact_image_block(block: Dict[str, Any]) -> Dict[str, Any]:
    b = copy.deepcopy(block)
    if b.get("type") != "image":
        return b
    src = b.get("source")
    if isinstance(src, dict) and src.get("type") == "base64" and "data" in src:
        raw = src["data"]
        src["data"] = f"<REDACTED base64 image, {len(raw)} chars>"
    return b


def _redact_user_content(content: ContentPart) -> ContentPart:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: List[Any] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image":
                out.append(_redact_image_block(part))
            elif isinstance(part, dict):
                out.append(copy.deepcopy(part))
            else:
                out.append(part)
        return out
    if isinstance(content, dict):
        return copy.deepcopy(content)
    return content


def _request_payload_for_log(**kwargs: Any) -> Dict[str, Any]:
    payload = copy.deepcopy(dict(kwargs))
    messages = payload.get("messages")
    if isinstance(messages, list):
        redacted = []
        for msg in messages:
            if not isinstance(msg, dict):
                redacted.append(msg)
                continue
            m = copy.deepcopy(msg)
            if "content" in m:
                m["content"] = _redact_user_content(m["content"])
            redacted.append(m)
        payload["messages"] = redacted
    return payload


def _response_payload_for_log(response: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "stop_reason": getattr(response, "stop_reason", None),
    }
    usage = getattr(response, "usage", None)
    if usage is not None:
        out["usage"] = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
    blocks: List[Dict[str, Any]] = []
    for blk in getattr(response, "content", None) or []:
        btype = getattr(blk, "type", None)
        if btype == "text":
            blocks.append({"type": "text", "text": getattr(blk, "text", "")})
        else:
            blocks.append({"type": str(btype)})
    out["content"] = blocks
    return out


async def logged_messages_create(
    client: AsyncAnthropic,
    call_site: str,
    **kwargs: Any,
) -> Any:
    """Call client.messages.create and log full request (images redacted) and response."""
    req = _request_payload_for_log(**kwargs)
    logger.info(
        "LLM REQUEST [%s]\n%s",
        call_site,
        json.dumps(req, indent=2, ensure_ascii=False, default=str),
    )
    response = await client.messages.create(**kwargs)
    resp = _response_payload_for_log(response)
    logger.info(
        "LLM RESPONSE [%s]\n%s",
        call_site,
        json.dumps(resp, indent=2, ensure_ascii=False, default=str),
    )
    return response
