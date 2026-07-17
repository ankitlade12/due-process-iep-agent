"""Privacy-minimizing redaction before a cloud model call.

IEPs and service logs may be student education records under FERPA (20 U.S.C.
1232g; 34 C.F.R. Part 99). Sending them to a third-party cloud model unredacted
is the reason a school, nonprofit, or legal-aid clinic would refuse to adopt the
tool. The agent workflow uses this module to replace known direct identifiers
with placeholders before a text call, and can restore them afterward for an
authorized local copy. It cannot detect every indirect or previously unknown
identifier and is therefore defense in depth, not a compliance guarantee.

The reliable signal is that the tool already *knows* the student's identifiers
(the parent entered them), so it can redact those exact strings — far more robust
than guessing names with NER. Generic patterns (email, phone, SSN, labeled DOB)
are caught too. Session dates are deliberately preserved: they are the evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Generic PII patterns. Note: bare dates are NOT redacted — service dates are
# evidence; only a date explicitly labeled as a birth date is masked.
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOB = re.compile(
    r"\b(?:DOB|D\.O\.B\.|date of birth)\b\s*[:#-]?\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


@dataclass
class Redactor:
    """Masks a specific student's identifiers (plus generic PII patterns)."""

    # Maps an exact identifier string -> its placeholder, longest first so
    # full names mask before their individual tokens.
    identifiers: Dict[str, str] = field(default_factory=dict)
    mask_generic: bool = True

    @classmethod
    def for_case(
        cls,
        *,
        student_name: str = "",
        parent_name: str = "",
        student_id: str = "",
        extra: Optional[Dict[str, str]] = None,
    ) -> "Redactor":
        """Build a redactor from the identifiers the tool already knows."""
        ids: Dict[str, str] = {}

        def add(value: str, label: str) -> None:
            value = (value or "").strip()
            if len(value) < 2:
                return
            ids[value] = label
            # Also mask individual name tokens (first/last) so "Maria" alone goes.
            if " " in value and label in ("[STUDENT]", "[PARENT]"):
                for token in value.split():
                    if len(token) >= 2:
                        ids.setdefault(token, label)

        add(student_name, "[STUDENT]")
        add(parent_name, "[PARENT]")
        add(student_id, "[STUDENT_ID]")
        for value, label in (extra or {}).items():
            add(value, label)
        return cls(identifiers=ids)

    def redact(self, text: str) -> Tuple[str, Dict[str, str]]:
        """Return (redacted_text, restore_map). ``restore_map`` maps each
        placeholder used back to the original value so output can be re-hydrated
        locally."""
        if not text:
            return text, {}
        restore: Dict[str, str] = {}
        out = text
        # Longest identifiers first to avoid partial masking.
        for value in sorted(self.identifiers, key=len, reverse=True):
            label = self.identifiers[value]
            if value in out:
                out = re.sub(re.escape(value), label, out, flags=re.IGNORECASE)
                restore[label] = value
        if self.mask_generic:
            out = _DOB.sub("DOB: [DOB]", out)
            out = _EMAIL.sub("[EMAIL]", out)
            out = _SSN.sub("[SSN]", out)
            out = _PHONE.sub("[PHONE]", out)
        return out, restore

    def restore(self, text: str, restore_map: Dict[str, str]) -> str:
        """Re-insert the original identifiers (for the parent's local copy)."""
        out = text
        for placeholder, original in restore_map.items():
            out = out.replace(placeholder, original)
        return out

    def leaks(self, text: str) -> List[str]:
        """Any known identifiers still present in ``text`` (should be none after
        redaction). Used to assert nothing identifiable leaves for the cloud."""
        found = []
        low = (text or "").lower()
        for value in self.identifiers:
            if value.lower() in low:
                found.append(value)
        return found

    def assert_clean(self, text: str) -> None:
        leaked = self.leaks(text)
        if leaked:
            raise PrivacyLeakError(
                f"Refusing to send: identifiers still present after redaction: "
                f"{leaked}"
            )


class PrivacyLeakError(RuntimeError):
    """Raised when redaction did not remove a known identifier."""


def redact_for_cloud(text: str, redactor: Optional[Redactor]) -> str:
    """Redact and verify text before a cloud call; a no-op if no redactor.

    Verifies that known identifiers are absent, so a known-value redaction miss
    fails loudly. It cannot prove that the text is fully de-identified.
    """
    if redactor is None:
        return text
    redacted, _ = redactor.redact(text)
    redactor.assert_clean(redacted)
    return redacted
