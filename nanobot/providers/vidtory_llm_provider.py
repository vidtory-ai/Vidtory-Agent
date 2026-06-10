"""Vidtory LLM Provider — wraps bapi.vidtory.net/generative-core/text as an LLMProvider."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Callable

import httpx
from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

_DEFAULT_API_BASE = "https://bapi.vidtory.net"
_DEFAULT_MODEL = "gemini-3-flash-preview"      # Vidtory text model
_DEFAULT_WORKER_ID = "worker-mini-veo3-ultra1" # HARDCODED — always route text via this worker
_POLL_INTERVAL_S = 2.0       # poll every 2 seconds
_JOB_TIMEOUT_S = 120.0       # single job timeout (extended for slow models)
_MAX_JOB_ATTEMPTS = 1        # no retries — one clean attempt only
_DEFAULT_TIMEOUT_S = 180.0   # httpx connect/read timeout per individual request

# ReAct-style tool use prompt template injected into system instruction
_TOOL_USE_SYSTEM_SUFFIX = """
You have access to the following tools. To use a tool, respond EXACTLY in this JSON format (no other text):
{"tool_call": {"name": "<tool_name>", "arguments": {<arguments_json>}}}

After receiving a tool result, continue your reasoning and provide the final answer.
Available tools:
"""

_TOOL_USE_RESULT_PREFIX = "[Tool result for {name}]: "


def _extract_text_from_content(content: Any) -> str:
    """Extract plain text from a message content (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text") or "")
                elif block.get("type") == "tool_result":
                    result_content = block.get("content") or ""
                    if isinstance(result_content, list):
                        result_content = " ".join(
                            b.get("text", "") for b in result_content
                            if isinstance(b, dict)
                        )
                    parts.append(str(result_content))
                elif block.get("type") == "image_url":
                    parts.append("[image]")
                elif block.get("type") == "tool_use":
                    parts.append(
                        f'[tool call: {block.get("name")}({json.dumps(block.get("input", {}))})]'
                    )
        return "\n".join(p for p in parts if p)
    return str(content) if content is not None else ""


def _messages_to_vidtory_format(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Convert OpenAI-style messages to Vidtory API format.

    Returns:
        (system_instruction, user_prompt, conversation_history)
    """
    system_parts: list[str] = []
    history: list[dict[str, Any]] = []
    last_user_prompt = ""

    # Collect system messages
    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            content = _extract_text_from_content(msg.get("content", ""))
            if content:
                system_parts.append(content)

    # Build tool descriptions in system if tools provided
    if tools:
        tool_descs: list[str] = []
        for tool in tools:
            fn = tool.get("function") or tool
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = json.dumps(fn.get("parameters", {}), ensure_ascii=False, indent=2)
            tool_descs.append(f"- {name}: {desc}\n  Parameters: {params}")
        system_parts.append(_TOOL_USE_SYSTEM_SUFFIX + "\n".join(tool_descs))

    system_instruction = "\n\n".join(system_parts)

    # Build conversation history (excluding system) — collect all but the last user message
    non_system = [m for m in messages if m.get("role") != "system"]
    if non_system:
        # Last message should be user — use as prompt; rest as history
        if non_system[-1].get("role") == "user":
            history_msgs = non_system[:-1]
            last_user_prompt = _extract_text_from_content(non_system[-1].get("content", ""))
        else:
            history_msgs = non_system
            last_user_prompt = "(continue)"

        for msg in history_msgs:
            role = msg.get("role", "")
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")

            if role == "assistant":
                if tool_calls:
                    # Encode tool calls as JSON in the assistant turn
                    text_parts = []
                    if content:
                        text_parts.append(_extract_text_from_content(content))
                    for tc in tool_calls:
                        fn = tc.get("function") or {}
                        args_str = fn.get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                        except Exception:
                            args = {}
                        text_parts.append(
                            json.dumps({"tool_call": {"name": fn.get("name", ""), "arguments": args}})
                        )
                    history.append({"role": "assistant", "content": "\n".join(text_parts)})
                else:
                    text = _extract_text_from_content(content)
                    if text:
                        history.append({"role": "assistant", "content": text})

            elif role == "tool":
                # Tool result — append as user message with prefix
                tool_name = msg.get("name") or ""
                result_text = _extract_text_from_content(content)
                history.append({
                    "role": "user",
                    "content": _TOOL_USE_RESULT_PREFIX.format(name=tool_name) + result_text,
                })

            elif role == "user":
                text = _extract_text_from_content(content)
                if text:
                    history.append({"role": "user", "content": text})

    return system_instruction, last_user_prompt, history



# Mapping from Vidtory model action names → nanobot tool names
_ACTION_TO_TOOL: dict[str, str] = {
    "dalle.text2im": "generate_image",
    "dalle.image2image": "generate_image",
    "image.generate": "generate_image",
    "image.text2im": "generate_image",
    "video.generate": "generate_video",
    "video.text2video": "generate_video",
    "audio.generate": "generate_audio",
    "audio.tts": "generate_audio",
    "web.search": "web_search",
    "web.fetch": "web_fetch",
}

# Actions to SKIP — these are internal agent directives, not real tool calls
_SKIP_ACTIONS: frozenset[str] = frozenset({
    "vidtory_onboarding",
    "vidtory-onboarding",
    "onboarding",
    "final_answer",
    "Final Answer",
})


def _extract_all_json_objects(text: str) -> list[dict]:
    """Extract all top-level JSON objects from a string using raw_decode.

    The Vidtory model (gemini-3-flash-preview) sometimes returns multiple
    JSON objects concatenated with whitespace, e.g.:
        {"action": "vidtory_onboarding", ...}
        {"action": "dalle.text2im", ...}

    json.loads() fails on this because it expects a single value.
    raw_decode() parses one object at a time and returns the end index.
    """
    decoder = json.JSONDecoder()
    objects: list[dict] = []
    idx = 0
    while idx < len(text):
        # Skip whitespace and non-JSON characters
        while idx < len(text) and text[idx] != '{':
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                objects.append(obj)
            idx = end_idx
        except (json.JSONDecodeError, ValueError):
            idx += 1
    return objects


def _parse_vidtory_action(text: str) -> ToolCallRequest | None:
    """Parse Vidtory model's native agent JSON format.

    Handles single or multiple JSON objects in the response:
        {"action": "dalle.text2im", "action_input": "{\"prompt\": \"...\"}"}
    or multiple concatenated:
        {"action": "vidtory_onboarding", "action_input": "{}"}
        {"action": "dalle.text2im", "action_input": "{\"prompt\": \"...\"}"}

    Skips non-creative actions (onboarding, final_answer) and returns
    the first actionable tool call mapped via _ACTION_TO_TOOL.
    """
    import uuid
    text = text.strip()
    if '{' not in text:
        return None

    objects = _extract_all_json_objects(text)
    if not objects:
        return None

    # First pass: find an action that maps to a known creative tool
    for payload in objects:
        action = payload.get("action")
        if not action:
            continue
        # Skip internal/non-tool actions
        if action in _SKIP_ACTIONS:
            logger.debug("Vidtory: skipping non-tool action '{}'", action)
            continue
        tool_name = _ACTION_TO_TOOL.get(action)
        if not tool_name:
            # Unknown action — not a known creative tool, skip it
            logger.debug("Vidtory: unknown action '{}', skipping", action)
            continue

        # Parse action_input
        raw_input = payload.get("action_input") or payload.get("input") or {}
        if isinstance(raw_input, str):
            raw_input = raw_input.strip()
            try:
                parsed = json.loads(raw_input)
                arguments = parsed if isinstance(parsed, dict) else {"prompt": raw_input}
            except (json.JSONDecodeError, ValueError):
                arguments = {"prompt": raw_input}
        elif isinstance(raw_input, dict):
            arguments = raw_input
        else:
            arguments = {"prompt": str(raw_input)}

        logger.info(
            "Vidtory agent action detected: {} → tool={} args={}",
            action, tool_name, str(arguments)[:120],
        )
        return ToolCallRequest(
            id=f"vidtory-{uuid.uuid4().hex[:8]}",
            name=tool_name,
            arguments=arguments,
        )

    # No actionable creative tool found in any JSON object
    return None



def _parse_tool_call(text: str) -> ToolCallRequest | None:
    """Try to parse tool calls from LLM response.

    Handles two formats:
    1. ReAct-style: {"tool_call": {"name": "...", "arguments": {...}}}
    2. Vidtory agent: {"action": "dalle.text2im", "action_input": "...", "thought": "..."}
    """
    text = text.strip()
    start = text.find("{")
    if start == -1:
        return None

    # Try Vidtory agent format first (model's native format)
    vidtory_tc = _parse_vidtory_action(text)
    if vidtory_tc:
        return vidtory_tc

    # Try ReAct format
    try:
        payload = json.loads(text[start:])
        tc = payload.get("tool_call")
        if not isinstance(tc, dict):
            return None
        name = tc.get("name")
        arguments = tc.get("arguments") or {}
        if not name:
            return None
        import uuid
        return ToolCallRequest(
            id=f"vidtory-{uuid.uuid4().hex[:8]}",
            name=name,
            arguments=arguments,
        )
    except (json.JSONDecodeError, Exception):
        return None



class VidtoryLLMProvider(LLMProvider):
    """LLM provider that uses Vidtory B2B text generation API.

    Uses async job polling (POST /generative-core/text → poll /jobs/{id}/status).
    Supports conversationHistory and systemInstruction.
    Tool calling via ReAct pattern (JSON in response).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = _DEFAULT_MODEL,
        worker_id: str | None = _DEFAULT_WORKER_ID,  # default = worker-mini-veo3-ultra1 (hardcoded)
        timeout: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        super().__init__(api_key=api_key, api_base=api_base)
        self._default_model = default_model
        self._worker_id = worker_id
        self._timeout = timeout

    def get_default_model(self) -> str:
        return self._default_model

    def _effective_api_key(self) -> str | None:
        """Get the effective API key: prefer user context var, fallback to config key."""
        from nanobot.utils.context_vars import telegram_vidtory_api_key
        user_key = telegram_vidtory_api_key.get()
        return user_key or self.api_key

    def _api_base(self) -> str:
        return (self.api_base or _DEFAULT_API_BASE).rstrip("/")

    async def _submit_job(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict,
        body: dict,
    ) -> str | None:
        """Submit a text generation job. Returns job_id or None on failure."""
        resp = await client.post(
            f"{base}/generative-core/text",
            headers=headers,
            json=body,
        )
        if resp.status_code == 401:
            raise _AuthError("Invalid Vidtory API key. Please re-enter with /apikey.")
        if resp.status_code == 429:
            raise _RateLimitError(resp.text[:200])
        if resp.status_code >= 400:
            raise _ApiError(resp.status_code, resp.text[:500])

        init_data = resp.json()
        if not init_data.get("success"):
            msg = init_data.get("message") or "Unknown error"
            raise _ApiError(0, f"Vidtory text generation failed: {msg}")

        job_id = (init_data.get("data") or {}).get("generationHistoryId")
        return job_id

    async def _poll_job(
        self,
        client: httpx.AsyncClient,
        base: str,
        headers: dict,
        job_id: str,
        job_timeout: float,
        tools: list[dict] | None,
    ) -> LLMResponse | None:
        """Poll job until COMPLETED/FAILED or job_timeout exceeded.

        Returns LLMResponse if done, or None if timed out (caller should retry).
        """
        start = time.monotonic()
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= job_timeout:
                logger.warning(
                    "Vidtory job {} timed out after {:.0f}s — will start a new job",
                    job_id, elapsed,
                )
                return None  # Signal caller to start a new job

            await asyncio.sleep(_POLL_INTERVAL_S)

            try:
                poll = await client.get(
                    f"{base}/generative-core/jobs/{job_id}/status",
                    headers=headers,
                )
            except Exception as exc:
                logger.warning("Vidtory poll request failed: {}", exc)
                continue

            if poll.status_code >= 400:
                logger.warning("Vidtory poll HTTP {}: {}", poll.status_code, poll.text[:200])
                continue

            status_data = poll.json().get("data") or {}
            status = status_data.get("status")

            if status == "COMPLETED":
                result = status_data.get("result") or {}
                text_out = (
                    result.get("text")
                    or result.get("content")
                    or result.get("output")
                    or ""
                )
                # Fallback: result stored at URL
                if not text_out:
                    url = result.get("url")
                    if url and url.startswith("http"):
                        try:
                            text_resp = await client.get(url)
                            text_out = text_resp.text
                        except Exception as e:
                            logger.warning("Failed to fetch text result URL: {}", e)

                text_out = str(text_out).strip()

                # Always try to detect Vidtory agent action format first
                # (model returns {"action": "dalle.text2im", "action_input": "..."})
                if text_out:
                    vidtory_action = _parse_vidtory_action(text_out)
                    if vidtory_action:
                        logger.debug(
                            "Vidtory agent action: {} → tool={} args={}",
                            text_out[:60], vidtory_action.name, str(vidtory_action.arguments)[:80],
                        )
                        return LLMResponse(
                            content=None,
                            tool_calls=[vidtory_action],
                            finish_reason="tool_calls",
                        )

                # ReAct tool call detection (only when tools provided)
                if tools and text_out:
                    tc = _parse_tool_call(text_out)
                    if tc:
                        logger.debug("Vidtory LLM tool call: {} ({})", tc.name, tc.arguments)
                        return LLMResponse(
                            content=None,
                            tool_calls=[tc],
                            finish_reason="tool_calls",
                        )

                return LLMResponse(content=text_out, finish_reason="stop")

            elif status == "FAILED":
                err = status_data.get("error") or "Job failed"
                return LLMResponse(
                    content=f"Error: Vidtory job failed: {err}",
                    finish_reason="error",
                )
            # PENDING / PROCESSING → keep polling

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        api_key = self._effective_api_key()
        if not api_key:
            return LLMResponse(
                content=(
                    "❌ Bạn chưa cấu hình Vidtory API Key.\n\n"
                    "Vui lòng cung cấp key bằng lệnh:\n"
                    "`/apikey YOUR_VIDTORY_API_KEY`\n\n"
                    "👉 Lấy API key tại: https://app.vidtory.net/settings/api"
                ),
                finish_reason="error",
            )

        effective_model = model or self._default_model
        system_instruction, prompt, history = _messages_to_vidtory_format(messages, tools)

        # Send BOTH workerId AND modelId — the worker supports multiple models,
        # so omitting modelId causes the server to default to gemini-2.5-flash.
        # workerId = "worker-mini-veo3-ultra1", modelId = "gemini-3-flash-preview" (hardcoded).
        worker = self._worker_id or _DEFAULT_WORKER_ID
        body: dict[str, Any] = {
            "prompt": prompt,
            "workerId": worker,
            "modelId": effective_model,  # hardcoded = "gemini-3-flash-preview"
        }

        if system_instruction:
            body["systemInstruction"] = system_instruction
        if history:
            body["conversationHistory"] = history

        headers = {"x-api-key": api_key, "Content-Type": "application/json"}
        base = self._api_base()

        # httpx client with short per-request timeout (connect + read)
        http_timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)

        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                for attempt in range(1, _MAX_JOB_ATTEMPTS + 1):
                    target = worker  # always worker-mini-veo3-ultra1
                    logger.debug(
                        "Vidtory LLM attempt {}/{} — worker={}", attempt, _MAX_JOB_ATTEMPTS, target
                    )
                    try:
                        job_id = await self._submit_job(client, base, headers, body)
                    except _AuthError as exc:
                        return LLMResponse(
                            content=f"❌ {exc}",
                            finish_reason="error",
                            error_status_code=401,
                            error_should_retry=False,
                        )
                    except _RateLimitError as exc:
                        return LLMResponse(
                            content=f"⚠️ Vidtory rate limit: {exc}",
                            finish_reason="error",
                            error_status_code=429,
                            error_should_retry=True,
                        )
                    except _ApiError as exc:
                        return LLMResponse(
                            content=f"⚠️ Vidtory API error ({exc.status}): {exc.detail}",
                            finish_reason="error",
                            error_status_code=exc.status,
                            error_should_retry=exc.status >= 500,
                        )

                    if not job_id:
                        return LLMResponse(
                            content="⚠️ Vidtory did not return a job ID.",
                            finish_reason="error",
                        )

                    result = await self._poll_job(
                        client, base, headers, job_id, _JOB_TIMEOUT_S, tools
                    )

                    if result is not None:
                        # Got a response (success, FAILED, or error)
                        return result

                    # result is None → job timed out → loop continues to next attempt
                    if attempt < _MAX_JOB_ATTEMPTS:
                        logger.info(
                            "Vidtory job {} timed out, retrying ({}/{})...",
                            job_id, attempt, _MAX_JOB_ATTEMPTS,
                        )
                    else:
                        logger.warning(
                            "Vidtory job timed out after {} attempts, giving up.", _MAX_JOB_ATTEMPTS
                        )
                        return LLMResponse(
                            content=(
                                "⏱️ Hệ thống Vidtory đang bận, không phản hồi sau "
                                f"{_MAX_JOB_ATTEMPTS} lần thử. Vui lòng thử lại."
                            ),
                            finish_reason="error",
                            error_kind="timeout",
                            error_should_retry=True,
                        )

        except httpx.TimeoutException as exc:
            return LLMResponse(
                content=f"⏱️ Kết nối Vidtory timeout: {exc}",
                finish_reason="error",
                error_kind="timeout",
                error_should_retry=True,
            )
        except httpx.RequestError as exc:
            return LLMResponse(
                content=f"⚠️ Kết nối Vidtory thất bại: {exc}",
                finish_reason="error",
                error_kind="connection",
                error_should_retry=True,
            )

        # Should never reach here
        return LLMResponse(content="⚠️ Unexpected error in VidtoryLLMProvider.", finish_reason="error")

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        """Vidtory uses job polling, not native streaming.
        Deliver the full response in one delta after polling completes.
        """
        response = await self.chat(
            messages=messages, tools=tools, model=model,
            max_tokens=max_tokens, temperature=temperature,
            reasoning_effort=reasoning_effort, tool_choice=tool_choice,
        )
        if on_content_delta and response.content:
            await on_content_delta(response.content)
        return response


# ---------------------------------------------------------------------------
# Internal exception helpers (not exported)
# ---------------------------------------------------------------------------

class _AuthError(Exception):
    pass


class _RateLimitError(Exception):
    pass


class _ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail

