"""Core simulation for ordered events and stale-worker fencing.

The implementation deliberately uses in-memory state so that the coordination
rules are visible without requiring a database or message broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EventOutcome(str, Enum):
    """Result of delivering a versioned event."""

    APPLIED = "APPLIED"
    BUFFERED = "BUFFERED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


class WorkerOutcome(str, Enum):
    """Result of a fenced worker update."""

    APPLIED = "APPLIED"
    STALE_REJECTED = "STALE_REJECTED"


@dataclass(frozen=True, slots=True)
class OrderEvent:
    """An immutable, versioned order update."""

    order_id: str
    version: int
    status: str

    def __post_init__(self) -> None:
        if not self.order_id:
            raise ValueError("order_id must not be empty")
        if self.version < 1:
            raise ValueError("version must be at least 1")
        if not self.status:
            raise ValueError("status must not be empty")


@dataclass(slots=True)
class OrderState:
    """Materialized state and pending events for one order."""

    version: int = 0
    status: str = "NOT_CREATED"
    pending: dict[int, OrderEvent] = field(default_factory=dict)
    highest_fencing_token: int = 0


class OrderProcessor:
    """Applies events in sequence and rejects stale workers."""

    def __init__(self) -> None:
        self._orders: dict[str, OrderState] = {}
        self._next_fencing_token = 0
        self.log: list[str] = []

    def state_for(self, order_id: str) -> OrderState:
        """Return the order state, creating an empty state if necessary."""

        return self._orders.setdefault(order_id, OrderState())

    def deliver(self, event: OrderEvent) -> EventOutcome:
        """Deliver an event, buffering gaps and draining contiguous versions."""

        state = self.state_for(event.order_id)
        expected_version = state.version + 1

        if event.version <= state.version or event.version in state.pending:
            self._record(
                f"DUPLICATE ignored: order={event.order_id} "
                f"version={event.version} current_version={state.version}"
            )
            return EventOutcome.DUPLICATE_IGNORED

        if event.version > expected_version:
            state.pending[event.version] = event
            missing = list(range(expected_version, event.version))
            self._record(
                f"PENDING: order={event.order_id} received_version={event.version} "
                f"missing_versions={missing} pending_versions={self.pending_versions(event.order_id)}"
            )
            return EventOutcome.BUFFERED

        self._apply(state, event)
        self._drain_pending(event.order_id, state)
        return EventOutcome.APPLIED

    def pending_versions(self, order_id: str) -> list[int]:
        """Return buffered versions in ascending order."""

        return sorted(self.state_for(order_id).pending)

    def issue_fencing_token(self, worker_name: str) -> int:
        """Issue a globally increasing token to a worker."""

        self._next_fencing_token += 1
        token = self._next_fencing_token
        self._record(f"TOKEN issued: worker={worker_name} token={token}")
        return token

    def worker_update(
        self,
        *,
        order_id: str,
        worker_name: str,
        fencing_token: int,
        status: str,
    ) -> WorkerOutcome:
        """Apply a worker update only when its token is not stale."""

        state = self.state_for(order_id)
        if fencing_token < state.highest_fencing_token:
            self._record(
                f"STALE WORKER rejected: order={order_id} worker={worker_name} "
                f"token={fencing_token} highest_token={state.highest_fencing_token}"
            )
            return WorkerOutcome.STALE_REJECTED

        state.highest_fencing_token = fencing_token
        state.status = status
        self._record(
            f"WORKER UPDATE applied: order={order_id} worker={worker_name} "
            f"token={fencing_token} status={status}"
        )
        return WorkerOutcome.APPLIED

    def snapshot(self, order_id: str) -> dict[str, object]:
        """Return a stable dictionary suitable for logs and assertions."""

        state = self.state_for(order_id)
        return {
            "order_id": order_id,
            "version": state.version,
            "status": state.status,
            "pending_versions": self.pending_versions(order_id),
            "highest_fencing_token": state.highest_fencing_token,
        }

    def _apply(self, state: OrderState, event: OrderEvent) -> None:
        state.version = event.version
        state.status = event.status
        self._record(
            f"APPLIED: order={event.order_id} version={event.version} status={event.status}"
        )

    def _drain_pending(self, order_id: str, state: OrderState) -> None:
        next_version = state.version + 1
        while next_version in state.pending:
            event = state.pending.pop(next_version)
            self._record(
                f"RELEASED pending event: order={order_id} version={next_version}"
            )
            self._apply(state, event)
            next_version = state.version + 1

    def _record(self, message: str) -> None:
        self.log.append(message)
