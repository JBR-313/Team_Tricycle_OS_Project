"""Upstage Solar Pro 3 client for the Visual Scheduler LLM Advisor (Role B).

This module is the single place that talks to the LLM over the network.
`tools/llm_advisor.py` should import `SolarClient` from here, build the
scheduling prompt, and turn the response into `recommendation.json`.

Design rules honored from CLAUDE.md / architecture_diagram.md:
  - API key lives in `.env` only, never committed (see `.env.example`).
  - The LLM only advises; it never controls the scheduler. This file just
    returns text / parsed JSON and makes no scheduling decisions itself.

Zero third-party dependencies (stdlib only) so every teammate can run it
without `pip install`.

The Upstage API is OpenAI-compatible:
    POST https://api.upstage.ai/v1/chat/completions
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

__all__ = ["SolarClient", "SolarError", "load_env"]

DEFAULT_BASE_URL = "https://api.upstage.ai/v1"
DEFAULT_MODEL = "solar-pro3"  # Solar Pro 3
DEFAULT_TIMEOUT = 60.0


class SolarError(RuntimeError):
    """Raised when the Solar API call fails or returns an unusable response."""


def load_env(env_path: Optional[str | Path] = None) -> None:
    """Load KEY=VALUE pairs from a `.env` file into os.environ.

    Minimal parser so we don't depend on python-dotenv. Existing environment
    variables are NOT overwritten. If no path is given, look for `.env` next
    to this file and in the project root.
    """
    candidates = []
    if env_path is not None:
        candidates.append(Path(env_path))
    else:
        here = Path(__file__).resolve().parent
        candidates += [here / ".env", here.parent / ".env"]

    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return  # first existing file wins


class SolarClient:
    """Thin client around the Upstage Solar Pro 3 chat-completions endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> None:
        load_env()
        self.api_key = api_key or os.environ.get("UPSTAGE_API_KEY")
        if not self.api_key:
            raise SolarError(
                "UPSTAGE_API_KEY is not set. Copy .env.example to .env at the "
                "project root and put your Upstage Solar Pro 3 API key there. "
                "If you intend to run without a real key, pass an explicit "
                "offline-fixture flag at the call site instead of leaving the "
                "key blank."
            )
        self.model = model or os.environ.get("SOLAR_MODEL", DEFAULT_MODEL)
        self.base_url = (
            base_url or os.environ.get("SOLAR_BASE_URL", DEFAULT_BASE_URL)
        ).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    # ---- low-level ------------------------------------------------------

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            req = urllib.request.Request(
                url, data=data, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                # Retry transient server / rate-limit errors only.
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    last_err = SolarError(f"HTTP {exc.code}: {body}")
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise SolarError(f"HTTP {exc.code} from Solar API: {body}") from exc
            except urllib.error.URLError as exc:
                last_err = SolarError(f"Network error: {exc.reason}")
                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))
                    continue
                raise last_err from exc

        raise last_err or SolarError("Solar API call failed for an unknown reason")

    # ---- high-level helpers --------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Send a chat-completions request and return the assistant text.

        messages: standard OpenAI-style [{"role": "system"/"user"/"assistant",
                  "content": "..."}].
        json_mode: ask the model to return strictly valid JSON (useful for
                   producing recommendation.json).
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = self._post("/chat/completions", payload)
        try:
            return resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SolarError(
                f"Unexpected Solar API response shape: {json.dumps(resp)[:500]}"
            ) from exc

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Convenience wrapper for a single user prompt (+ optional system)."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def complete_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> Any:
        """Like `complete`, but parse and return the response as JSON.

        Intended for Role B's `recommendation.json` generation. Falls back to
        extracting the first {...} block if the model wraps JSON in prose.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        text = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            raise SolarError(f"Model did not return valid JSON:\n{text[:500]}")


def _smoke_test() -> None:
    """Manual check: `python3 tools/solar_client.py`."""
    client = SolarClient()
    print(f"model      = {client.model}")
    print(f"base_url   = {client.base_url}")
    reply = client.complete(
        "In one sentence, when is FCFS scheduling a poor choice?",
        system="You are a concise operating-systems teaching assistant.",
        max_tokens=120,
    )
    print("reply      =", reply.strip())


if __name__ == "__main__":
    _smoke_test()
