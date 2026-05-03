"""Default model guard.

The sidecar's `.env.example` says Haiku 4.5 is the locked default. A retired
default in `app/llm.py` would 404 every deployed call when COPILOT_MODEL is
unset. This test pins the literal default value in the source so a future
agent can't silently downgrade it.

We grep the source rather than reload the module under a clean env, because
`load_dotenv` runs at module import and the test runner's env may already
have COPILOT_MODEL set from `.env`. Pinning the source string keeps the
guard intact even with `.env` present.
"""

from __future__ import annotations

import pathlib
import re


def test_llm_default_model_source_pin():
    src = (
        pathlib.Path(__file__).resolve().parent.parent
        / "app"
        / "llm.py"
    ).read_text(encoding="utf-8")
    match = re.search(
        r'_MODEL\s*=\s*os\.getenv\(\s*["\']COPILOT_MODEL["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
        src,
    )
    assert match, "expected `_MODEL = os.getenv('COPILOT_MODEL', '...')` line in app/llm.py"
    default = match.group(1)
    assert default == "claude-haiku-4-5-20251001", (
        f"app/llm.py default model is {default!r}; expected the locked Haiku 4.5 id "
        "'claude-haiku-4-5-20251001'. A retired default 404s every deployed call when "
        "COPILOT_MODEL is unset — see AgDR-0006."
    )
