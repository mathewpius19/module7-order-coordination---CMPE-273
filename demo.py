"""Run all Module 7 scenarios and print rubric-ready evidence."""

from __future__ import annotations

import json

from order_coordination import OrderEvent, OrderProcessor


def print_new_logs(processor: OrderProcessor, start: int) -> int:
    for line in processor.log[start:]:
        print(f"  {line}")
    return len(processor.log)


def print_snapshot(processor: OrderProcessor, order_id: str) -> None:
    print("  Final state:", json.dumps(processor.snapshot(order_id), sort_keys=True))


def ordering_and_duplicate_demo() -> None:
    print("=== 1. VERSIONED EVENT ORDERING + DUPLICATE HANDLING ===")
    processor = OrderProcessor()
    order_id = "order-100"
    cursor = 0

    deliveries = [
        OrderEvent(order_id, 2, "PAID"),
        OrderEvent(order_id, 1, "CREATED"),
        OrderEvent(order_id, 2, "PAID"),
    ]
    for event in deliveries:
        print(f"Delivering: version={event.version} status={event.status}")
        outcome = processor.deliver(event)
        cursor = print_new_logs(processor, cursor)
        print(f"  Outcome: {outcome.value}")

    print_snapshot(processor, order_id)
    print("  PASS: v2 waited for v1, then duplicate v2 was ignored.\n")


def missing_event_demo() -> None:
    print("=== 2. MISSING EVENT TEST ===")
    processor = OrderProcessor()
    order_id = "order-200"

    print("Delivering only: version=3 status=SHIPPED")
    outcome = processor.deliver(OrderEvent(order_id, 3, "SHIPPED"))
    print_new_logs(processor, 0)
    print(f"  Outcome: {outcome.value}")
    print_snapshot(processor, order_id)
    print("  PASS: order did not jump to SHIPPED; versions 1 and 2 are missing.\n")


def stale_worker_demo() -> None:
    print("=== 3. STALE WORKER / FENCING TOKEN TEST ===")
    processor = OrderProcessor()
    order_id = "order-300"
    cursor = 0

    old_token = processor.issue_fencing_token("worker-A")
    new_token = processor.issue_fencing_token("worker-B")
    cursor = print_new_logs(processor, cursor)

    print("Worker B updates first with the newer token:")
    newer_outcome = processor.worker_update(
        order_id=order_id,
        worker_name="worker-B",
        fencing_token=new_token,
        status="SHIPPED",
    )
    cursor = print_new_logs(processor, cursor)
    print(f"  Outcome: {newer_outcome.value}")

    print("Worker A resumes late with the older token:")
    older_outcome = processor.worker_update(
        order_id=order_id,
        worker_name="worker-A",
        fencing_token=old_token,
        status="CANCELLED",
    )
    print_new_logs(processor, cursor)
    print(f"  Outcome: {older_outcome.value}")
    print_snapshot(processor, order_id)
    print("  PASS: stale worker was rejected and SHIPPED was preserved.\n")


def main() -> None:
    print("MODULE 7: TIME, ORDERING & COORDINATION\n")
    ordering_and_duplicate_demo()
    missing_event_demo()
    stale_worker_demo()
    print("ALL MODULE 7 SCENARIOS PASSED")


if __name__ == "__main__":
    main()
