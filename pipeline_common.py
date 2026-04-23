#!/usr/bin/env python3
"""
Shared runtime helpers for the experimental synthesis pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
from pathlib import Path
from threading import Lock
from typing import Any, Callable, TypeVar

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_OPENAI_MODEL = "glm-5.1"
DEFAULT_OPENAI_API_BASE = "https://open.bigmodel.cn/api/paas/v4/"
DEFAULT_OPENAI_TIMEOUT = 120
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
T = TypeVar("T")


def load_project_dotenv(dotenv_path: Path | None = None) -> None:
    path = dotenv_path or DEFAULT_DOTENV_PATH
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any], lock: Lock) -> None:
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with lock:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


def normalize_model_name(model: str) -> str:
    model = model.strip()
    if "/" in model:
        _, model_name = model.split("/", 1)
        model = model_name
    return model


def add_openai_client_args(parser: argparse.ArgumentParser, *, include_timeout: bool = False) -> None:
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL))
    parser.add_argument("--api-base", default=os.environ.get("OPENAI_API_BASE", DEFAULT_OPENAI_API_BASE))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    if include_timeout:
        parser.add_argument("--timeout", type=int, default=int(os.environ.get("OPENAI_TIMEOUT", str(DEFAULT_OPENAI_TIMEOUT))))


def require_api_key(api_key: str, message: str = "OPENAI_API_KEY or --api-key is required") -> None:
    if not str(api_key).strip():
        raise SystemExit(message)


def build_openai_client(
    *,
    model: str,
    api_key: str,
    api_base: str,
    timeout: int = DEFAULT_OPENAI_TIMEOUT,
    max_retries: int = 2,
) -> "OpenAICompatClient":
    return OpenAICompatClient(
        model=model,
        api_key=api_key,
        api_base=api_base,
        timeout=timeout,
        max_retries=max_retries,
    )


def build_openai_client_from_args(
    args: Any,
    *,
    timeout: int | None = None,
    max_retries: int = 2,
) -> "OpenAICompatClient":
    effective_timeout = int(timeout if timeout is not None else getattr(args, "timeout", DEFAULT_OPENAI_TIMEOUT))
    return build_openai_client(
        model=str(getattr(args, "model")),
        api_key=str(getattr(args, "api_key")),
        api_base=str(getattr(args, "api_base")),
        timeout=effective_timeout,
        max_retries=max_retries,
    )


def is_transient_llm_error(
    exc: Exception,
    *,
    extra_retryable: tuple[type[BaseException], ...] = (),
) -> bool:
    if extra_retryable and isinstance(exc, extra_retryable):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        if (
            "Empty LLM content" in message
            or "Model returned reasoning_content without final answer" in message
            or "Malformed JSON in model output" in message
        ):
            return True
    if isinstance(
        exc,
        (
            TimeoutError,
            APITimeoutError,
            RateLimitError,
            APIConnectionError,
            InternalServerError,
        ),
    ):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in TRANSIENT_HTTP_CODES
    if isinstance(exc, urllib.error.URLError):
        return True
    return False


def call_with_retries(
    operation: Callable[[], T],
    *,
    retries: int,
    is_retryable: Callable[[Exception], bool],
    sleep_base_seconds: float = 1.0,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries or not is_retryable(exc):
                raise
            time.sleep(sleep_base_seconds * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def extract_first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
                    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
                    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
                    return json.loads(repaired)
    raise ValueError("No complete JSON object found in model output")


class OpenAICompatClient:
    def __init__(self, model: str, api_key: str, api_base: str, timeout: int = 120, max_retries: int = 2) -> None:
        self.model = normalize_model_name(model)
        self.api_base = api_base
        self.default_extra_body = {"thinking": {"type": "disabled"}} if self.model.startswith("glm-") else None
        self.client = OpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=float(timeout),
            max_retries=max(0, max_retries - 1),
        )

    def chat_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            extra_body=self.default_extra_body,
        )
        message = resp.choices[0].message
        raw_content = message.content
        if isinstance(raw_content, str):
            content = raw_content.strip()
        elif isinstance(raw_content, list):
            parts = []
            for item in raw_content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            content = "".join(parts).strip()
        else:
            content = ""
        if not content:
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning:
                raise RuntimeError(f"Model returned reasoning_content without final answer: {str(reasoning)[:600]}")
            raise RuntimeError(f"Empty LLM content: {resp}")
        return content

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        text = self.chat_text(
            system_prompt,
            user_prompt,
        )
        try:
            return extract_first_json_object(text)
        except ValueError as exc:
            raise RuntimeError(f"Malformed JSON in model output: {text[:600]}") from exc
