"""
ai/reliability.py — Reliability Layer (Priority 3)
Timeout, retry, cancellation, structured logging, and metrics
for every tool call and AI request.
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  [%(component)s]  %(message)s"
_DATE_FORMAT = "%H:%M:%S"

logging.basicConfig(format=_LOG_FORMAT, datefmt=_DATE_FORMAT, level=logging.INFO)


def get_logger(component: str) -> logging.LoggerAdapter:
    """Return a structured logger tagged with a component name."""
    logger = logging.getLogger("ai_ide")
    return logging.LoggerAdapter(logger, {"component": component})


# ---------------------------------------------------------------------------
# Metrics collector
# ---------------------------------------------------------------------------

@dataclass
class CallMetric:
    name: str
    started_at: float
    duration_ms: float = 0
    ok: bool = True
    retries: int = 0
    error: Optional[str] = None


class MetricsCollector:
    """In-memory metrics store for tool calls and AI requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: List[CallMetric] = []

    def record(self, metric: CallMetric) -> None:
        with self._lock:
            self._metrics.append(metric)

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            if not self._metrics:
                return {"total": 0}
            total = len(self._metrics)
            failed = sum(1 for m in self._metrics if not m.ok)
            total_ms = sum(m.duration_ms for m in self._metrics)
            avg_ms = total_ms / total if total else 0
            retried = sum(1 for m in self._metrics if m.retries > 0)
            return {
                "total_calls":    total,
                "failed_calls":   failed,
                "success_rate":   f"{(total - failed) / total * 100:.1f}%",
                "avg_latency_ms": round(avg_ms, 1),
                "retried_calls":  retried,
            }

    def recent(self, n: int = 20) -> List[CallMetric]:
        with self._lock:
            return list(self._metrics[-n:])

    def clear(self) -> None:
        with self._lock:
            self._metrics.clear()


# Singleton instance
metrics = MetricsCollector()


# ---------------------------------------------------------------------------
# Reliable call wrapper
# ---------------------------------------------------------------------------

@dataclass
class ReliabilityConfig:
    max_retries: int = 3
    timeout_seconds: float = 30.0
    retry_delay: float = 0.5
    exponential_backoff: bool = True
    log_component: str = "tool"


def reliable_call(
    fn: Callable,
    args: tuple = (),
    kwargs: Optional[Dict] = None,
    config: Optional[ReliabilityConfig] = None,
    stop_event: Optional[threading.Event] = None,
    name: str = "",
) -> Any:
    """
    Call any function with:
    - Timeout (via thread + event)
    - Retry with exponential backoff
    - Cancellation via stop_event
    - Structured logging
    - Metrics recording

    Returns the function's result or raises on final failure.
    """
    kwargs = kwargs or {}
    cfg = config or ReliabilityConfig()
    log = get_logger(cfg.log_component)
    call_name = name or getattr(fn, "__name__", str(fn))

    metric = CallMetric(name=call_name, started_at=time.time())
    last_exc: Optional[Exception] = None

    for attempt in range(1, cfg.max_retries + 1):
        if stop_event and stop_event.is_set():
            metric.ok = False
            metric.error = "Cancelled"
            break

        result_holder: List[Any] = []
        exc_holder: List[Exception] = []
        done_event = threading.Event()

        def _run():
            try:
                result_holder.append(fn(*args, **kwargs))
            except Exception as e:
                exc_holder.append(e)
            finally:
                done_event.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        finished = done_event.wait(timeout=cfg.timeout_seconds)

        if not finished:
            last_exc = TimeoutError(f"{call_name} timed out after {cfg.timeout_seconds}s")
            log.warning(f"Attempt {attempt}/{cfg.max_retries} TIMEOUT: {call_name}")
            metric.retries = attempt - 1
        elif exc_holder:
            last_exc = exc_holder[0]
            log.warning(f"Attempt {attempt}/{cfg.max_retries} FAILED: {call_name} — {last_exc}")
            metric.retries = attempt - 1
        else:
            # Success
            metric.duration_ms = (time.time() - metric.started_at) * 1000
            metric.ok = True
            log.info(f"OK [{metric.duration_ms:.0f}ms] {call_name}")
            metrics.record(metric)
            return result_holder[0]

        # Wait before retry
        if attempt < cfg.max_retries:
            delay = cfg.retry_delay * (2 ** (attempt - 1)) if cfg.exponential_backoff else cfg.retry_delay
            if stop_event:
                stop_event.wait(timeout=delay)
            else:
                time.sleep(delay)

    # All retries exhausted
    metric.duration_ms = (time.time() - metric.started_at) * 1000
    metric.ok = False
    metric.error = str(last_exc)
    metrics.record(metric)
    log.error(f"FAILED after {cfg.max_retries} attempts: {call_name} — {last_exc}")
    raise last_exc or RuntimeError(f"{call_name} failed")


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def with_reliability(
    max_retries: int = 3,
    timeout: float = 30.0,
    component: str = "tool",
) -> Callable[[F], F]:
    """
    Decorator to add timeout + retry + logging + metrics to any function.

    Usage:
        @with_reliability(max_retries=3, timeout=10.0, component="git")
        def my_tool(args):
            ...
    """
    cfg = ReliabilityConfig(
        max_retries=max_retries,
        timeout_seconds=timeout,
        log_component=component,
    )

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return reliable_call(fn, args=args, kwargs=kwargs, config=cfg, name=fn.__name__)
        return wrapper  # type: ignore
    return decorator


# ---------------------------------------------------------------------------
# Pipeline stage timer (used by pipeline.py for structured logs)
# ---------------------------------------------------------------------------

class StageTimer:
    """
    Context manager that logs + records timing for a named pipeline stage.

    Usage:
        with StageTimer("Analyze", logger) as t:
            do_work()
        print(t.duration_ms)
    """

    def __init__(self, stage_name: str, logger: Optional[logging.LoggerAdapter] = None):
        self.stage_name = stage_name
        self._log = logger or get_logger("pipeline")
        self.duration_ms: float = 0
        self._start: float = 0

    def __enter__(self) -> "StageTimer":
        self._start = time.time()
        self._log.info(f"START  {self.stage_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.duration_ms = (time.time() - self._start) * 1000
        if exc_type:
            self._log.error(f"FAIL   {self.stage_name}  [{self.duration_ms:.0f}ms]  {exc_val}")
        else:
            self._log.info(f"DONE   {self.stage_name}  [{self.duration_ms:.0f}ms]")
        return False  # don't suppress exceptions
