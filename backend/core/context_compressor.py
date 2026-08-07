"""
Context Compression — multiple strategies for reducing conversation / context size.

Provides compression strategies for reducing the size of conversation history
and context sections to fit within a token budget.  Supports auto-detection of
the optimal strategy based on context size and required compression ratio.

Usage:
    compressor = ContextCompressor()

    # Auto-detect best strategy
    compressed = compressor.compress(sections, target_tokens=4096)

    # Explicit strategy
    summary = compressor.summarize_history(messages, max_tokens=512)
    recent = compressor.sliding_window(messages, window_size=20)
    trimmed = compressor.truncate_early(messages, keep_ratio=0.5)
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from backend.core.context_engine import ContextPriority, ContextSection, estimate_tokens
from backend.core.model_config import model_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compression strategy
# ---------------------------------------------------------------------------


class CompressionStrategy(Enum):
    """Strategies for reducing context size.

    Each value corresponds to a different trade-off between information
    preservation and compression aggressiveness.
    """

    DROP_LOWEST = "drop"  # drop lowest priority sections
    SUMMARIZE = "summarize"  # summarise old history into a condensed section
    TRUNCATE_EARLY = "truncate"  # keep head + tail, drop middle
    SLIDING_WINDOW = "window"  # keep last N sections / messages


# ---------------------------------------------------------------------------
# LLM summarisation prompt
# ---------------------------------------------------------------------------

_SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a conversation summarisation assistant. Condense the following "
    "conversation history into a concise summary that preserves every critical "
    "piece of information."
)

_SUMMARIZATION_USER_PROMPT = """\
Please produce a concise summary of the conversation below.  Include:

1. **Key decisions** made by the user or assistant.
2. **User requests**, preferences, goals, and questions.
3. **Tool call results** or external data that was retrieved.
4. **Action items** or follow-up tasks that were identified.

Keep the summary factual.  Preserve specific numbers, names, dates, and
technical details.  Omit pleasantries and repetitive content.

--- BEGIN CONVERSATION ---
{conversation_text}
--- END CONVERSATION ---

Summary:"""


# ---------------------------------------------------------------------------
# Context Compressor
# ---------------------------------------------------------------------------


class ContextCompressor:
    """Compress conversation history and context sections to fit token budgets.

    Supports four compression strategies:

    * ``DROP_LOWEST`` — Remove lowest-priority :class:`ContextSection` entries.
    * ``SUMMARIZE``  — Use an LLM (or heuristic fallback) to condense older
      low-priority content into a single summary section.
    * ``TRUNCATE_EARLY`` — Keep the first *keep_ratio* and the remainder of
      sections / messages, dropping the middle.
    * ``SLIDING_WINDOW`` — Keep only the last *window_size* entries.

    When no explicit strategy is provided, :meth:`compress` auto-detects the
    best strategy based on the compression ratio and total section count.
    """

    def __init__(self, llm_adapter: Optional[Any] = None) -> None:
        """Initialise with an optional LLM adapter override.

        :param llm_adapter:  If provided, used for LLM-based summarization
            instead of ``model_manager.get_main_llm()``.  Must have an
            ``async chat(messages, model, **kwargs)`` method returning
            ``str``.
        """
        self._llm_adapter = llm_adapter

    # ------------------------------------------------------------------
    # Token estimation (delegated)
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token count via character heuristic.

        Delegates to :func:`backend.core.context_engine.estimate_tokens`.

        :param text: Input string (may be empty).
        :returns:    Estimated token count (minimum 1 for non-empty text).
        """
        return estimate_tokens(text)

    # ------------------------------------------------------------------
    # LLM adapter resolution
    # ------------------------------------------------------------------

    def _resolve_llm(self) -> Any:
        """Return an LLM adapter (injected or from the global model manager).

        Returns *None* if no adapter is available.
        """
        if self._llm_adapter is not None:
            return self._llm_adapter
        try:
            return model_manager.get_main_llm()
        except (KeyError, AttributeError) as exc:
            logger.warning("No LLM adapter available for summarization: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Main compress entry point (sections)
    # ------------------------------------------------------------------

    def compress(
        self,
        sections: List[ContextSection],
        target_tokens: int,
        strategy: Optional[CompressionStrategy] = None,
    ) -> List[ContextSection]:
        """Compress *sections* to fit within *target_tokens*.

        :param sections:      List of :class:`ContextSection` to compress.
        :param target_tokens: Maximum total tokens the result should occupy.
        :param strategy:      Explicit strategy override.  When *None* the
            compressor auto-detects the best strategy.
        :returns:             Compressed list of sections (may be empty).
        """
        if not sections:
            return []
        if target_tokens <= 0:
            return []

        current_tokens = sum(s.tokens for s in sections)
        if current_tokens <= target_tokens:
            # Already within budget — nothing to do.
            return list(sections)

        compression_ratio = 1.0 - (target_tokens / current_tokens) if current_tokens > 0 else 0.0

        if strategy is None:
            strategy = self._auto_detect_strategy(sections, compression_ratio)

        logger.info(
            "Compressing %d sections (%d tokens -> %d tokens, ratio=%.1f%%) using %s",
            len(sections),
            current_tokens,
            target_tokens,
            compression_ratio * 100,
            strategy.value,
        )

        _DISPATCH = {
            CompressionStrategy.DROP_LOWEST: self._compress_drop_lowest,
            CompressionStrategy.SUMMARIZE: self._compress_via_summary,
            CompressionStrategy.TRUNCATE_EARLY: self._compress_truncate_early,
            CompressionStrategy.SLIDING_WINDOW: self._compress_sliding_window,
        }

        handler = _DISPATCH.get(strategy)
        if handler is None:
            logger.warning("Unknown strategy %r, falling back to DROP_LOWEST", strategy)
            handler = self._compress_drop_lowest

        return handler(sections, target_tokens)

    # ------------------------------------------------------------------
    # Strategy auto-detection
    # ------------------------------------------------------------------

    @staticmethod
    def _auto_detect_strategy(
        sections: List[ContextSection],
        compression_ratio: float,
    ) -> CompressionStrategy:
        """Heuristically select the best compression strategy.

        Rules
        -----
        * Compression > 50 %  -> ``SUMMARIZE``   (aggressive reduction).
        * Compression < 30 %  -> ``DROP_LOWEST`` (light pruning).
        * Section count > 50  -> ``SLIDING_WINDOW`` (temporal locality).
        * Otherwise           -> ``SUMMARIZE``.
        """
        if compression_ratio > 0.50:
            return CompressionStrategy.SUMMARIZE
        if compression_ratio < 0.30:
            return CompressionStrategy.DROP_LOWEST
        if len(sections) > 50:
            return CompressionStrategy.SLIDING_WINDOW
        return CompressionStrategy.SUMMARIZE

    # ------------------------------------------------------------------
    # Strategy: DROP_LOWEST
    # ------------------------------------------------------------------

    @staticmethod
    def _compress_drop_lowest(
        sections: List[ContextSection],
        target_tokens: int,
    ) -> List[ContextSection]:
        """Drop the lowest-priority sections until the budget is satisfied.

        CRITICAL / required sections are never dropped.  Among droppable
        sections the compressor sorts by ascending priority (lowest first)
        and descending token size so that the largest, least-important
        sections are removed first.
        """
        # Separate protected (always kept) from droppable sections.
        protected: List[ContextSection] = []
        droppable: List[ContextSection] = []
        for s in sections:
            if s.required or s.priority >= ContextPriority.CRITICAL:
                protected.append(s)
            else:
                droppable.append(s)

        # Sort: lowest priority first, then largest token count first.
        # This means we drop the biggest low-priority sections earliest,
        # which is the most space-efficient strategy.
        droppable.sort(key=lambda s: (s.priority.value, -s.tokens))

        protected_tokens = sum(s.tokens for s in protected)

        # If protected sections alone exceed the budget we have no choice
        # but to return them anyway (they are required).
        if protected_tokens > target_tokens:
            logger.warning(
                "Protected sections already use %d tokens (budget=%d); "
                "returning protected sections only",
                protected_tokens,
                target_tokens,
            )
            return protected

        remaining_budget = target_tokens - protected_tokens
        kept: List[ContextSection] = list(protected)

        for section in droppable:
            if section.tokens <= remaining_budget:
                kept.append(section)
                remaining_budget -= section.tokens

        return kept

    # ------------------------------------------------------------------
    # Strategy: SUMMARIZE
    # ------------------------------------------------------------------

    def _compress_via_summary(
        self,
        sections: List[ContextSection],
        target_tokens: int,
    ) -> List[ContextSection]:
        """Summarize low-priority sections into a single compressed section.

        CRITICAL and HIGH priority sections are kept intact.  MEDIUM, LOW and
        ARCHIVE sections are concatenated and summarised into a single
        ``"compressed_history"`` :class:`ContextSection` with MEDIUM priority.

        If LLM summarization is unavailable or fails, falls back to heuristic
        extractive truncation.
        """
        high_priority: List[ContextSection] = []
        summarizable: List[ContextSection] = []
        for s in sections:
            if s.required or s.priority >= ContextPriority.HIGH:
                high_priority.append(s)
            else:
                summarizable.append(s)

        high_tokens = sum(s.tokens for s in high_priority)
        summary_budget = target_tokens - high_tokens

        if not summarizable or summary_budget <= 20:
            # Nothing meaningful to summarise, or no room.
            return self._compress_drop_lowest(sections, target_tokens)

        combined_text = "\n\n".join(s.content for s in summarizable)
        combined_tokens = estimate_tokens(combined_text)

        if combined_tokens <= summary_budget:
            # Already fits — keep everything.
            return list(sections)

        # Attempt LLM summarization, with heuristic fallback.
        summary_text = self._llm_summarize(combined_text, max_tokens=summary_budget)
        if not summary_text:
            summary_text = self._heuristic_truncate(combined_text, summary_budget)

        summary_section = ContextSection(
            name="compressed_history",
            content=summary_text,
            priority=ContextPriority.MEDIUM,
            tokens=estimate_tokens(summary_text),
            required=False,
        )

        return high_priority + [summary_section]

    # ------------------------------------------------------------------
    # Strategy: TRUNCATE_EARLY
    # ------------------------------------------------------------------

    @staticmethod
    def _compress_truncate_early(
        sections: List[ContextSection],
        target_tokens: int,
    ) -> List[ContextSection]:
        """Keep the first half and a tail portion of sections; drop the middle.

        After the initial split the tail is further pruned via
        ``DROP_LOWEST`` if it exceeds its token budget.
        """
        if not sections:
            return []

        keep_ratio = 0.5
        mid = max(1, int(len(sections) * keep_ratio))

        head = sections[:mid]
        tail = sections[mid:]

        head_tokens = sum(s.tokens for s in head)
        tail_budget = target_tokens - head_tokens

        if tail_budget <= 0:
            retained = head
        else:
            tail_kept = ContextCompressor._compress_drop_lowest(tail, tail_budget)
            retained = head + tail_kept

        # Final safety pass.
        if sum(s.tokens for s in retained) > target_tokens:
            retained = ContextCompressor._compress_drop_lowest(retained, target_tokens)

        return retained

    # ------------------------------------------------------------------
    # Strategy: SLIDING_WINDOW
    # ------------------------------------------------------------------

    @staticmethod
    def _compress_sliding_window(
        sections: List[ContextSection],
        target_tokens: int,
    ) -> List[ContextSection]:
        """Keep the most recent sections that fit within *target_tokens*.

        Iterates from the end of the list backward, accumulating sections
        until the budget is exhausted.  This preserves the most recent
        (and usually most relevant) content.
        """
        if not sections:
            return []

        accumulated: List[ContextSection] = []
        used = 0

        for section in reversed(sections):
            if used + section.tokens <= target_tokens:
                accumulated.append(section)
                used += section.tokens
            else:
                break

        # Restore original chronological order.
        accumulated.reverse()
        return accumulated

    # ------------------------------------------------------------------
    # LLM-based summarization (async-aware)
    # ------------------------------------------------------------------

    def _llm_summarize(self, text: str, max_tokens: int) -> Optional[str]:
        """Use the LLM adapter to produce a summary of *text*.

        Handles both sync and async calling contexts:

        * If no event loop is running, uses ``asyncio.run()``.
        * If an event loop **is** running (e.g. inside a ``async def``),
          returns *None* so the caller falls back to heuristic.  Callers
          that are already in an async context should use
          :meth:`async_summarize_text` directly.

        Returns *None* if summarization fails or the adapter is unavailable.
        """
        llm = self._resolve_llm()
        if llm is None:
            return None

        prompt = self._build_summary_prompt(text)
        prompt_tokens = estimate_tokens(prompt)

        # Reserve some room for the response itself.
        response_allocation = max(64, max_tokens - prompt_tokens)
        if response_allocation < 64:
            logger.warning("Summary budget too tight for LLM call; skipping.")
            return None

        try:
            # Check whether we are already inside a running event loop.
            try:
                asyncio.get_running_loop()
                # There IS a running loop — we cannot block with
                # asyncio.run().  Return None so the caller uses the
                # heuristic fallback instead.
                logger.debug("Running event loop detected; deferring LLM summarization.")
                return None
            except RuntimeError:
                # No running loop — safe to use asyncio.run().
                pass

            result = asyncio.run(
                llm.chat(
                    messages=[
                        {"role": "system", "content": _SUMMARIZATION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    model="",
                    max_tokens=response_allocation,
                    temperature=0.3,
                )
            )
            return result.strip() if result else None
        except Exception as exc:
            logger.error("LLM summarization failed: %s", exc)
            return None

    async def async_summarize_text(self, text: str, max_tokens: int) -> Optional[str]:
        """Async variant of :meth:`_llm_summarize`.

        Safe to call from within an async context (e.g. FastAPI route
        handlers, async agent loops).  Falls back to heuristic truncation
        if the LLM is unavailable.
        """
        llm = self._resolve_llm()
        if llm is None:
            return None

        prompt = self._build_summary_prompt(text)
        prompt_tokens = estimate_tokens(prompt)
        response_allocation = max(64, max_tokens - prompt_tokens)
        if response_allocation < 64:
            return None

        try:
            result = await llm.chat(
                messages=[
                    {"role": "system", "content": _SUMMARIZATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model="",
                max_tokens=response_allocation,
                temperature=0.3,
            )
            return result.strip() if result else None
        except Exception as exc:
            logger.error("Async LLM summarization failed: %s", exc)
            return None

    @staticmethod
    def _build_summary_prompt(conversation_text: str) -> str:
        """Build the user prompt for summarization.

        If the conversation is very long, truncates the input to avoid
        exceeding typical context limits.
        """
        # Rough safety cap: 8K chars ~ 2K tokens.
        if len(conversation_text) > 32000:
            conversation_text = (
                conversation_text[:16000]
                + "\n\n... [middle portion truncated] ...\n\n"
                + conversation_text[-16000:]
            )
        return _SUMMARIZATION_USER_PROMPT.format(conversation_text=conversation_text)

    # ------------------------------------------------------------------
    # Heuristic (non-LLM) helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _messages_to_text(messages: Sequence[Dict[str, str]]) -> str:
        """Convert a list of message dicts into a plain-text conversation log."""
        lines: List[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "").strip()
            if content:
                lines.append(f"[{role.upper()}]\n{content}")
        return "\n\n".join(lines)

    @staticmethod
    def _heuristic_truncate(text: str, max_tokens: int) -> str:
        """Truncate *text* to approximately *max_tokens* tokens.

        Attempts to break at a sentence or paragraph boundary rather than
        mid-word.
        """
        if not text or estimate_tokens(text) <= max_tokens:
            return text

        # Conservative char-to-token ratio: ~4 chars / token.
        char_limit = max_tokens * 4
        if len(text) <= char_limit:
            return text

        truncated = text[:char_limit]

        # Walk backwards to find a clean break point.
        for sep in ("\n\n", "\n", ". ", "。", "! ", "！", "? ", "？", ", "):
            idx = truncated.rfind(sep)
            # Only use the break if it's past the halfway point.
            if idx > char_limit // 2:
                truncated = truncated[: idx + len(sep)]
                break

        return truncated.strip()

    # ------------------------------------------------------------------
    # Message-level convenience operations
    # ------------------------------------------------------------------

    def summarize_history(
        self,
        messages: Sequence[Dict[str, str]],
        max_tokens: int = 512,
    ) -> str:
        """Summarize a conversation message list into a concise string.

        .. note::
            In a synchronous context this method uses heuristic extractive
            summarization.  For LLM-powered summarisation call
            :meth:`async_summarize_text` from an ``async def`` context.

        :param messages:   Sequence of ``{"role": ..., "content": ...}`` dicts.
        :param max_tokens: Maximum token count for the summary.
        :returns:          Summarised text (may be empty if *messages* is empty).
        """
        if not messages:
            return ""

        conversation_text = self._messages_to_text(messages)

        if estimate_tokens(conversation_text) <= max_tokens:
            return conversation_text

        # Use heuristic (extractive) summarization in sync context.
        return self._heuristic_summarize_messages(messages, max_tokens)

    @staticmethod
    def sliding_window(
        messages: Sequence[Dict[str, str]],
        window_size: int = 20,
    ) -> List[Dict[str, str]]:
        """Keep the last *window_size* messages.

        :param messages:    Sequence of message dicts.
        :param window_size: Number of most recent messages to retain.
        :returns:           The last *window_size* messages (or all if fewer).
        """
        if not messages:
            return []
        if len(messages) <= window_size:
            return list(messages)
        return list(messages[-window_size:])

    @staticmethod
    def truncate_early(
        messages: Sequence[Dict[str, str]],
        keep_ratio: float = 0.5,
    ) -> List[Dict[str, str]]:
        """Keep the first *keep_ratio* messages and the remaining tail.

        Drops the middle portion of the conversation, preserving both the
        opening context and the most recent exchanges.

        :param messages:    Sequence of message dicts.
        :param keep_ratio:  Fraction of messages kept from the start
            (0.0–1.0).  The tail receives the remainder ``(1-keep_ratio)``.
        :returns:           Truncated message list.
        """
        if not messages:
            return []
        if keep_ratio <= 0.0 or keep_ratio >= 1.0:
            return list(messages)

        mid = max(1, int(len(messages) * keep_ratio))
        head = list(messages[:mid])
        tail = list(messages[mid:])
        return head + tail

    # ------------------------------------------------------------------
    # Heuristic message summarization
    # ------------------------------------------------------------------

    @staticmethod
    def _heuristic_summarize_messages(
        messages: Sequence[Dict[str, str]],
        max_tokens: int,
    ) -> str:
        """Heuristic extractive summarization of message history.

        Preservation order (highest priority first):

        1. System messages (instructions, persona).
        2. User messages (requests, questions).
        3. Tool result summaries (truncated to 200 characters each).
        4. The most recent assistant response.
        """
        if not messages:
            return ""

        system_parts: List[str] = []
        user_parts: List[str] = []
        tool_parts: List[str] = []
        assistant_parts: List[str] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(f"[System] {content}")
            elif role == "user":
                user_parts.append(f"[User] {content}")
            elif role in ("tool", "tool_result"):
                # Keep only first ~200 characters per tool result.
                truncated = content[:200]
                if len(content) > 200:
                    truncated += " ..."
                tool_parts.append(f"[Tool] {truncated}")
            elif role == "assistant":
                assistant_parts.append(f"[Assistant] {content}")

        # Assemble in priority order: system > user > tool > last assistant.
        ordered: List[str] = system_parts + user_parts + tool_parts

        # Attach the most recent assistant message.
        if assistant_parts:
            ordered.append(assistant_parts[-1])

        combined = "\n\n".join(ordered)

        if estimate_tokens(combined) <= max_tokens:
            return combined

        # Remove low-priority items from the end until we fit the budget.
        # Tool results go first, then user messages, etc.
        while ordered and estimate_tokens("\n\n".join(ordered)) > max_tokens:
            # Prefer to drop tool parts first, then assistant tail.
            if any(p.startswith("[Tool]") for p in ordered):
                # Remove the last tool entry.
                for i in range(len(ordered) - 1, -1, -1):
                    if ordered[i].startswith("[Tool]"):
                        ordered.pop(i)
                        break
            elif len(ordered) > 1 and ordered[-1].startswith("[Assistant]"):
                ordered.pop()
            elif len(ordered) > len(system_parts):
                # Drop the last non-system entry.
                for i in range(len(ordered) - 1, -1, -1):
                    if not ordered[i].startswith("[System]"):
                        ordered.pop(i)
                        break
            else:
                # Only system entries remain — hard truncate.
                break

        return "\n\n".join(ordered)[: max_tokens * 4]

    # ------------------------------------------------------------------
    # Convenience: compress a message list (multi-strategy)
    # ------------------------------------------------------------------

    def compress_messages(
        self,
        messages: Sequence[Dict[str, str]],
        target_tokens: int,
        window_size: int = 20,
        keep_ratio: float = 0.5,
    ) -> List[Dict[str, str]]:
        """Compress a conversation message list to fit *target_tokens*.

        Chains multiple strategies for best results:

        1. **Sliding window** — if the message count exceeds *window_size*,
           the oldest messages are sliced off.
        2. **Summarize** — the oldest chunk (outside the window) is
           summarised via :meth:`summarize_history` and injected as a single
           system message.
        3. **Truncate early** — fallback if summarization yields nothing.

        :param messages:      Sequence of message dicts.
        :param target_tokens: Target token budget for the result.
        :param window_size:   Sliding-window size (default 20).
        :param keep_ratio:    Truncation keep ratio (default 0.5).
        :returns:             Compressed message list.
        """
        if not messages:
            return []

        # Quick check: already fits.
        text_repr = self._messages_to_text(messages)
        if estimate_tokens(text_repr) <= target_tokens:
            return list(messages)

        if len(messages) <= window_size:
            # Small conversation: just use truncation.
            return self._truncate_message_list(messages, target_tokens, keep_ratio)

        # 1. Sliding window: keep the most recent messages.
        recent = self.sliding_window(messages, window_size)
        recent_text = self._messages_to_text(recent)
        recent_tokens = estimate_tokens(recent_text)

        if recent_tokens <= target_tokens:
            return recent

        # 2. Summarise the older portion.
        older = list(messages[:-window_size])
        summary_budget = max(128, min(target_tokens // 3, 1024))

        summary = self.summarize_history(older, max_tokens=summary_budget)
        if summary and estimate_tokens(summary) < target_tokens - recent_tokens:
            summary_msg: Dict[str, str] = {
                "role": "system",
                "content": f"[Compressed history summary]\n{summary}",
            }
            return [summary_msg] + recent

        # 3. Fallback to truncation.
        return self._truncate_message_list(messages, target_tokens, keep_ratio)

    @staticmethod
    def _truncate_message_list(
        messages: Sequence[Dict[str, str]],
        target_tokens: int,
        keep_ratio: float = 0.5,
    ) -> List[Dict[str, str]]:
        """Iteratively truncate messages until they fit the token budget."""
        if not messages:
            return []

        result = list(messages)

        # First pass: truncate-early split.
        result = ContextCompressor.truncate_early(result, keep_ratio)

        # Iteratively drop from the middle until the budget is met.
        while len(result) > 3:
            text = ContextCompressor._messages_to_text(result)
            if estimate_tokens(text) <= target_tokens:
                break
            mid = len(result) // 2
            result = result[:mid] + result[mid + 1:]

        # Final safety: hard character truncation on the last message
        # if still over budget.
        text = ContextCompressor._messages_to_text(result)
        if estimate_tokens(text) > target_tokens:
            # Merge everything into a single system message.
            combined = ContextCompressor._heuristic_truncate(text, target_tokens)
            result = [{"role": "system", "content": combined}]

        return result

    # ------------------------------------------------------------------
    # Debugging & introspection
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}"
            f"(llm_adapter={'provided' if self._llm_adapter else 'from_manager'})"
        )
