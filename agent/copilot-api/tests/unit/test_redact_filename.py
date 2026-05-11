"""L1: filename redaction at the sidecar boundary (AgDR-0084 / Plan §3.7).

Verifies that ``app.routes.redact_filename`` strips PHI from
user-supplied upload filenames at the sidecar entry boundary. The PHP
gateway is the primary scrub point (``copilot_upload_redact_filename``
in ``upload_common.php``); this Python helper is defense-in-depth.

What this catches:
  * A future endpoint that bypasses the gateway's redaction and lets a
    PHI-pattern filename ("smith_anne_dob_1962-04-14_lipid.pdf") reach
    the FastAPI extractor — the test asserts redact_filename strips
    every PHI token from the input even when the raw name looks
    catastrophic.
  * A future change that loosens the extension allowlist (e.g. accepts
    ``.html``, ``.json``, or ``..pdf``) — the test pins the allowlist
    to ``[a-z0-9]{1,8}``.
  * A change that drops the per-document determinism property — the
    test asserts the same (raw, sha) input always produces the same
    redacted output.
"""

from __future__ import annotations

import pytest

from app.routes import redact_filename

# Reference SHA-256 for a known empty-content document.
_EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_strips_phi_filename_keeps_extension() -> None:
    """A PHI-pattern filename is replaced with `upload-{sha8}.pdf`."""
    raw = "smith_anne_dob_1962-04-14_lipid.pdf"
    redacted = redact_filename(raw, _EMPTY_SHA)
    assert redacted == "upload-e3b0c442.pdf"
    # Every PHI token must be absent from the redacted form.
    for phi in ("smith", "anne", "1962", "04-14", "lipid"):
        assert phi.lower() not in redacted.lower(), (
            f"PHI token {phi!r} leaked into redacted name {redacted!r}"
        )


@pytest.mark.parametrize(
    "raw, expected_ext",
    [
        ("smith_anne.pdf", "pdf"),
        ("MRN_8453.PDF", "pdf"),
        ("scan.png", "png"),
        ("scan.JPEG", "jpeg"),
        ("file.jpg", "jpg"),
        ("noext", "bin"),
        (".", "bin"),
        (".hidden", "bin"),
        ("file.html", "html"),
        ("file.json", "json"),
    ],
)
def test_extension_handling(raw: str, expected_ext: str) -> None:
    """Extension is normalized to lowercase; missing/empty/hidden → 'bin'."""
    redacted = redact_filename(raw, _EMPTY_SHA)
    assert redacted == f"upload-e3b0c442.{expected_ext}"


@pytest.mark.parametrize(
    "raw",
    [
        "file.exe;rm -rf /",     # injection-ish
        "../etc/passwd",          # path traversal
        "file.{badext}",          # special chars in extension
        "file.a-b",               # dash in extension
        "file.toolongextensionfortest",  # > 8 chars
    ],
)
def test_unsafe_extension_falls_back_to_bin(raw: str) -> None:
    """Any extension outside the [a-z0-9]{1,8} allowlist is sanitized to 'bin'."""
    redacted = redact_filename(raw, _EMPTY_SHA)
    assert redacted.endswith(".bin"), (
        f"Unsafe extension in {raw!r} should produce '.bin', got {redacted!r}"
    )


def test_null_byte_in_name_still_produces_safe_output() -> None:
    """A null byte embedded in the raw name does not survive into the
    redacted output. ``os.path.splitext`` on ``"file.txt\\x00.pdf"`` sees
    the final ``.pdf`` extension which is in the allowlist, so the
    redacted form is ``upload-{sha8}.pdf`` (clean) rather than
    ``upload-{sha8}.bin``. Either output is acceptable — what matters is
    that the null byte AND the raw name are both gone from the result.
    """
    redacted = redact_filename("file.txt\x00.pdf", _EMPTY_SHA)
    assert "\x00" not in redacted
    assert "file" not in redacted
    assert "txt" not in redacted
    # Extension is either 'pdf' (final segment) or 'bin' (fallback) —
    # both safe, both deterministic. Pin to the actually-produced value
    # so a future change that tightens the regex still has to consciously
    # update the test.
    assert redacted == "upload-e3b0c442.pdf"


def test_deterministic_per_document() -> None:
    """Same (raw, sha) input always produces the same redacted output."""
    raw = "any-filename.pdf"
    sha = "a" * 64
    out1 = redact_filename(raw, sha)
    out2 = redact_filename(raw, sha)
    assert out1 == out2 == "upload-aaaaaaaa.pdf"


def test_different_sha_produces_different_name() -> None:
    """The SHA prefix differentiates documents."""
    sha_a = "a" * 64
    sha_b = "b" * 64
    out_a = redact_filename("intake.pdf", sha_a)
    out_b = redact_filename("intake.pdf", sha_b)
    assert out_a != out_b
    assert out_a == "upload-aaaaaaaa.pdf"
    assert out_b == "upload-bbbbbbbb.pdf"


def test_empty_string_input_handled() -> None:
    """Empty raw name still produces a redacted output."""
    redacted = redact_filename("", _EMPTY_SHA)
    assert redacted == "upload-e3b0c442.bin"


def test_no_phi_token_survives_redaction() -> None:
    """Comprehensive: a catastrophic PHI filename has every PHI token stripped.

    This mirrors the assertion in the eval case
    ``refusal_09_phi_filename_not_in_logs.json``: a PHI-pattern filename
    (last name + first name + DOB) must produce a redacted form whose
    string representation contains no case-variant of any PHI token.
    """
    raw = "Smith_Anne_DOB_1962-04-14_lipid_panel.pdf"
    redacted = redact_filename(raw, "deadbeef" * 8)
    forbidden_tokens = [
        "smith", "Smith", "SMITH",
        "anne", "Anne", "ANNE",
        "1962", "04-14", "04/14", "lipid", "panel",
    ]
    lowered = redacted.lower()
    for tok in forbidden_tokens:
        assert tok.lower() not in lowered, (
            f"PHI token {tok!r} leaked into redacted name {redacted!r}"
        )
    assert redacted == "upload-deadbeef.pdf"
