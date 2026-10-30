"""Model client interface for the move interpretation call.

The sentence-to-structured-move call goes through the small
``MoveModelClient`` interface so tests can use a fake and never touch
the network. ``MetaMoveClient`` is the live client: model
``muse-spark-1.3``, with the API key read from the environment
(``META_API_KEY``) or passed explicitly, never written in code. Only
the standard library is used.
"""

import json
import os
import urllib.error
import urllib.request

MODEL_NAME = "muse-spark-1.3"

API_KEY_ENV_VAR = "META_API_KEY"

API_BASE_ENV_VAR = "META_API_BASE_URL"

API_BASE_DEFAULT = "https://api.meta.ai/v1"

SYSTEM_PROMPT = (
    "Turn one sentence about moving an expected payment into JSON. "
    "Reply with exactly one JSON object and nothing else: either "
    '{"deal": "...", "payment": "...", "target_month": "YYYY-MM"} '
    'for a clear move, or {"question": "..."} with one focused '
    "question when the sentence is ambiguous or names something "
    "unknown. Move operation only."
)


class ModelError(Exception):
    """The model call failed or its answer could not be used."""


class MoveModelClient:
    """Interpret one move sentence as a structured move dict."""

    def interpret_move(self, sentence):
        """Return a dict: a move or ``{"question": ...}``."""
        raise NotImplementedError(
            "interpret_move is implemented by a model client")


def _api_base():
    return os.environ.get(API_BASE_ENV_VAR, API_BASE_DEFAULT)


def _read_content(body):
    """Extract the model text from a chat response body."""
    try:
        payload = json.loads(body.decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError,
            AttributeError):
        raise ModelError("the model answer could not be read")
    if not isinstance(content, str) or not content.strip():
        raise ModelError("the model answer was empty")
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if len(lines) > 1 else []
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        reading = json.loads(text)
    except ValueError:
        raise ModelError("the model answer was not JSON")
    if not isinstance(reading, dict):
        raise ModelError("the model answer was not an object")
    return reading


class MetaMoveClient(MoveModelClient):
    """Live interpretation client for model ``muse-spark-1.3``."""

    def __init__(self, api_key=None, timeout=30):
        key = api_key if api_key is not None else os.environ.get(
            API_KEY_ENV_VAR)
        if not key or not str(key).strip():
            raise ModelError(
                "a model API key is needed: set " + API_KEY_ENV_VAR)
        self.api_key = key
        self.model = MODEL_NAME
        self.timeout = timeout

    def interpret_move(self, sentence):
        """Ask the model to turn one sentence into a move or question."""
        if not isinstance(sentence, str) or not sentence.strip():
            raise ModelError("a move sentence is needed")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": sentence.strip()},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            _api_base() + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request,
                                        timeout=self.timeout) as reply:
                body = reply.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ModelError(
                    "the model key was refused (HTTP %d): check %s"
                    % (exc.code, API_KEY_ENV_VAR))
            raise ModelError(
                "the model call was refused (HTTP %d)" % exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelError("the model call failed: %s" % exc)
        return _read_content(body)
