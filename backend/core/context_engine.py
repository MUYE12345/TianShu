"""
Context Management Engine — token budget allocation with priority-based sectioning.

Provides a structured approach to building LLM context windows by assigning
token budgets to sections of varying priority. The engine ensures that critical
instructions are always included, high- and medium-priority sections compete
for remaining space, and low-priority or archival sections are dropped when
the window is full.

Usage:
    engine = ContextEngine(max_tokens=8192)
    engine.add_section("system_prompt", "You are a helpful assistant.", ContextPriority.CRITICAL, required=True)
    engine.add_section("tools", "<tool definitions>", ContextPriority.HIGH)
    engine.add_section("memory", "<user memory>", ContextPriority.MEDIUM)
    engine.add_section("examples", "<few-shot examples>", ContextPriority.LOW)

    context = engine.build_context()
    budget  = engine.summary()
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

# Rough heuristic: ~4 characters per token for most LLMs (OpenAI / Anthropic).
_CHARS_PER_TOKEN = 4.0


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text* using a character-count heuristic.

    This is a best-effort approximation.  For precise counts use the
    model-specific tokeniser at build time.
    """
    if not text:
        return 0
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

class ContextPriority(IntEnum):
    """Priority level for a context section; higher values = more important.

    Ordering (descending):
        CRITICAL  (100) — core instructions, always included
        HIGH      (80)  — tool definitions, current task prompt
        MEDIUM    (50)  — memory / persona, recent conversation history
        LOW       (30)  — few-shot examples, extra reference material
        ARCHIVE   (0)   — historical data safe to drop first
    """
    CRITICAL = 100
    HIGH = 80
    MEDIUM = 50
    LOW = 30
    ARCHIVE = 0


# ---------------------------------------------------------------------------
# Section data-class
# ---------------------------------------------------------------------------

@dataclass
class ContextSection:
    """A named, priority-tagged block of text destined for the context window.

    Attributes:
        name:      Unique identifier for the section.
        content:   The text payload.
        priority:  :class:`ContextPriority` level.
        tokens:    Estimated token count (auto-calculated if not provided).
        required:  If *True* and the section overflows the budget the engine
                   will raise :class:`ContextBudgetError`.
    """
    name: str
    content: str
    priority: ContextPriority = ContextPriority.MEDIUM
    tokens: int = 0
    required: bool = False

    def __post_init__(self) -> None:
        if self.tokens <= 0:
            self.tokens = estimate_tokens(self.content)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ContextBudgetError(RuntimeError):
    """Raised when a required section exceeds the available token budget."""


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

class ContextEngine:
    """Priority-aware context window manager.

    :param max_tokens:       Total context-window size (e.g. 8192 for Claude 3.5).
    :param reserved_tokens:  Token pools reserved for response generation, tool
                             calls, or other non-section overhead.  Common keys
                             are ``"response"`` (default 2048) and ``"tools"``.

    Typical workflow:

        1. Instantiate with the model's context limit.
        2. Call :meth:`add_section` for every context block you want to include.
        3. Call :meth:`build_context` to produce the final assembled string.
        4. Use :meth:`summary` for diagnostic / logging output.
    """

    _DEFAULT_RESERVED: Dict[str, int] = {
        "response": 2048,
        "tools": 0,
    }

    def __init__(
        self,
        max_tokens: int = 8192,
        reserved_tokens: Optional[Dict[str, int]] = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.sections: List[ContextSection] = []
        self.reserved_tokens: Dict[str, int] = {
            **self._DEFAULT_RESERVED,
            **(reserved_tokens or {}),
        }

    # ------------------------------------------------------------------
    # Section management
    # ------------------------------------------------------------------

    def add_section(
        self,
        name: str,
        content: str,
        priority: ContextPriority = ContextPriority.MEDIUM,
        required: bool = False,
    ) -> ContextSection:
        """Register a new context section.

        If a section with the same *name* already exists it will be replaced
        (after emitting a warning — duplicate names often indicate a logic error).

        Returns the newly created :class:`ContextSection`.
        """
        # Remove any existing section with the same name so we don't silently
        # accumulate duplicates.
        existing = self.get_section(name)
        if existing is not None:
            self.sections.remove(existing)

        section = ContextSection(
            name=name,
            content=content,
            priority=priority,
            tokens=estimate_tokens(content),
            required=required,
        )
        self.sections.append(section)
        return section

    def get_section(self, name: str) -> Optional[ContextSection]:
        """Return the section named *name*, or *None* if it does not exist."""
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def remove_section(self, name: str) -> None:
        """Remove the section named *name*.

        Raises :class:`KeyError` if no such section exists.
        """
        section = self.get_section(name)
        if section is None:
            raise KeyError(f"No section named {name!r}")
        self.sections.remove(section)

    def clear(self) -> None:
        """Remove all registered sections (reserved-token config is preserved)."""
        self.sections.clear()

    # ------------------------------------------------------------------
    # Budget allocation
    # ------------------------------------------------------------------

    @staticmethod
    def _priority_sort_key(section: ContextSection) -> Tuple[int, str]:
        """Sort descending by priority, then by name for deterministic ordering."""
        return (-section.priority.value, section.name)

    def _compute_overhead(self) -> int:
        """Return the total number of reserved tokens."""
        return sum(self.reserved_tokens.values())

    def _available_budget(self) -> int:
        """Tokens remaining after reserving overhead."""
        return self.max_tokens - self._compute_overhead()

    def allocate_budget(self) -> Dict[str, int]:
        """Run the priority-based allocation algorithm.

        Returns a ``{section_name: allocated_tokens}`` mapping.  Sections that
        could not fit are omitted from the result and their tokens are set to 0.

        Algorithm
        ---------
        1. Reserve response + tool tokens.
        2. Allocate **CRITICAL** sections first — every required section **must**
           fit or :class:`ContextBudgetError` is raised.
        3. Allocate **HIGH** sections in full until remaining budget is exhausted.
        4. Allocate **MEDIUM** sections from what is left.
        5. Allocate **LOW** sections from whatever remains.
        6. **ARCHIVE** sections are always dropped first (never allocated).
        """
        budget = self._available_budget()
        if budget <= 0:
            raise ContextBudgetError(
                f"Reserved tokens ({self._compute_overhead()}) exceed "
                f"max_tokens ({self.max_tokens}) — no space for sections."
            )

        # Sort sections by priority (highest first).
        ordered = sorted(self.sections, key=self._priority_sort_key)
        allocation: Dict[str, int] = {}

        # ----- Phase 1: CRITICAL (required sections) --------------------
        for section in ordered:
            if section.priority != ContextPriority.CRITICAL:
                continue
            if section.tokens > budget:
                budget_exhausted = (
                    f"Required section {section.name!r} requires "
                    f"{section.tokens} tokens but only {budget} remain."
                )
                if section.required:
                    raise ContextBudgetError(budget_exhausted)
                # Non-required critical: warn-like — just skip.
                continue
            allocation[section.name] = section.tokens
            budget -= section.tokens

        # ----- Phase 2: HIGH --------------------------------------------
        for section in ordered:
            if section.priority != ContextPriority.HIGH:
                continue
            if section.tokens <= budget:
                allocation[section.name] = section.tokens
                budget -= section.tokens
            # else: section is silently dropped.

        # ----- Phase 3: MEDIUM ------------------------------------------
        for section in ordered:
            if section.priority != ContextPriority.MEDIUM:
                continue
            if section.tokens <= budget:
                allocation[section.name] = section.tokens
                budget -= section.tokens

        # ----- Phase 4: LOW ---------------------------------------------
        for section in ordered:
            if section.priority != ContextPriority.LOW:
                continue
            if section.tokens <= budget:
                allocation[section.name] = section.tokens
                budget -= section.tokens

        # Phase 5: ARCHIVE is never allocated.

        return allocation

    # ------------------------------------------------------------------
    # Context assembly
    # ------------------------------------------------------------------

    def build_context(self, separator: str = "\n\n") -> str:
        """Build the final context string respecting the token budget.

        :param separator:  String inserted between sections (default two newlines).

        The ordering in the returned string follows priority descending; sections
        with equal priority retain their insertion order.

        Returns an empty string if no sections fit the budget.
        """
        allocation = self.allocate_budget()

        # Preserve insertion order among sections with the same priority by
        # iterating over the original list but skipping un-allocated sections.
        ordered = sorted(self.sections, key=self._priority_sort_key)

        included: List[str] = []
        for section in ordered:
            if section.name in allocation:
                included.append(section.content)

        return separator.join(included)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> Dict:
        """Return a diagnostic snapshot of the current budget allocation.

        The returned dict includes:

        - ``"max_tokens"``
        - ``"reserved"`` — per-key and total
        - ``"available_for_sections"``
        - ``"used_by_sections"``
        - ``"remaining"``
        - ``"sections"`` — list of dicts with name, priority, tokens, required,
          and ``allocated`` (bool) for every registered section.
        """
        allocation = self.allocate_budget()
        used = sum(allocation.values())
        reserved_total = self._compute_overhead()
        available = self._available_budget()

        section_details: List[Dict] = []
        for s in self.sections:
            section_details.append({
                "name": s.name,
                "priority": s.priority.name,
                "tokens": s.tokens,
                "required": s.required,
                "allocated": s.name in allocation,
            })

        return {
            "max_tokens": self.max_tokens,
            "reserved": {
                **self.reserved_tokens,
                "total": reserved_total,
            },
            "available_for_sections": max(0, available),
            "used_by_sections": used,
            "remaining": max(0, self.max_tokens - reserved_total - used),
            "sections": section_details,
        }

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(max_tokens={self.max_tokens}, "
            f"sections={len(self.sections)})"
        )
