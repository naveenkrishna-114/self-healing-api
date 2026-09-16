"""
engine.py — RetryEngine

Decides whether a failed request should be retried, and computes the
delay before the next attempt.

The engine:
1. Checks attempt count against max_attempts.
2. Classifies the error using ErrorClassifier.
3. Checks idempotency safety (delegates to IdempotencyGuard in Phase 12;
   for now accepts an optional is_safe_to_retry flag).
4. Computes backoff delay.
5. Applies jitter if configured.
6. Returns a RetryDecision.

The engine never sleeps — the caller (SelfHealingClient) does the waiting.
This keeps the engine fully synchronous and testable without time.sleep().
"""
from __future__ import annotations

import time

from self_healing_api.config.models import RetryConfig
from self_healing_api.errors.categories import RETRYABLE_CATEGORIES
from self_healing_api.errors.classifier import ErrorClassifier
from self_healing_api.retry.backoff import compute_delay
from self_healing_api.retry.jitter import apply_jitter
from self_healing_api.retry.policy import RetryDecision


class RetryEngine:
    """
    Decides whether to retry a failed request and computes the wait delay.

    Parameters
    ----------
    config : RetryConfig     Retry configuration.
    classifier : ErrorClassifier | None
        Error classifier. If None, a default one is created.

    Usage
    -----
    ::

        engine = RetryEngine(config)
        engine.start()   # reset state for a new request

        for attempt in range(config.max_attempts):
            try:
                response = transport.send(request)
                break
            except Exception as exc:
                decision = engine.evaluate(exc, attempt=attempt)
                if not decision.should_retry:
                    raise
                time.sleep(decision.delay)
    """

    def __init__(
        self,
        config: RetryConfig,
        classifier: ErrorClassifier | None = None,
    ) -> None:
        self._config = config
        self._classifier = classifier or ErrorClassifier(
            retryable_status_codes=config.retryable_status_codes
        )
        self._prev_delay: float = config.base_delay

    def start(self) -> None:
        """Reset per-request state. Call before each new request lifecycle."""
        self._prev_delay = self._config.base_delay

    def evaluate(
        self,
        exc: BaseException,
        attempt: int,
        http_status: int | None = None,
        is_idempotent: bool = True,
    ) -> RetryDecision:
        """
        Evaluate whether to retry after a failure.

        Parameters
        ----------
        exc : BaseException
            The exception raised by the transport.
        attempt : int
            Current zero-based attempt index (0 = first attempt).
        http_status : int | None
            HTTP status code if available (provides more accurate classification).
        is_idempotent : bool
            Whether the operation is safe to retry.
            Non-idempotent operations without an idempotency key
            must not be retried.

        Returns
        -------
        RetryDecision
            Decision with should_retry flag, delay, and reason.
        """
        next_attempt = attempt + 1  # 1-based for human-readable logs

        # Classify the failure
        if http_status is not None:
            category = self._classifier.classify_status_code(http_status)
        else:
            category = self._classifier.classify_exception(exc)

        # Attempts exhausted
        if attempt >= self._config.max_attempts - 1:
            return RetryDecision(
                should_retry=False,
                delay=0.0,
                attempt=next_attempt,
                category=category,
                reason=f"max_attempts ({self._config.max_attempts}) reached",
            )

        # Non-retryable error category
        if category not in RETRYABLE_CATEGORIES:
            return RetryDecision(
                should_retry=False,
                delay=0.0,
                attempt=next_attempt,
                category=category,
                reason=f"error category {category.name} is not retryable",
            )

        # Idempotency check — non-idempotent ops must not be retried
        if not is_idempotent:
            return RetryDecision(
                should_retry=False,
                delay=0.0,
                attempt=next_attempt,
                category=category,
                reason="operation is not idempotent and has no idempotency key",
            )

        # Compute delay
        delay = compute_delay(
            strategy=self._config.backoff,
            base=self._config.base_delay,
            attempt=attempt,
            max_delay=self._config.max_delay,
        )

        # Apply jitter
        if self._config.jitter:
            delay = apply_jitter(
                strategy=self._config.jitter_strategy,
                delay=delay,
                base=self._config.base_delay,
                prev_delay=self._prev_delay,
            )
            delay = max(0.0, min(delay, self._config.max_delay))

        self._prev_delay = delay

        return RetryDecision(
            should_retry=True,
            delay=delay,
            attempt=next_attempt,
            category=category,
            reason=f"retryable {category.name}, attempt {next_attempt}/{self._config.max_attempts}",
        )

    def sleep(self, delay: float) -> None:
        """
        Wait for the computed delay.

        Extracted into its own method so tests can monkeypatch it
        without mocking time.sleep globally.
        """
        if delay > 0:
            time.sleep(delay)
