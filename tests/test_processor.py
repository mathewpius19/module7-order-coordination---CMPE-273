import unittest

from order_coordination import (
    EventOutcome,
    OrderEvent,
    OrderProcessor,
    WorkerOutcome,
)


class VersionedOrderingTests(unittest.TestCase):
    def test_out_of_order_events_are_buffered_then_applied_in_order(self):
        processor = OrderProcessor()

        self.assertEqual(
            processor.deliver(OrderEvent("o-1", 2, "PAID")),
            EventOutcome.BUFFERED,
        )
        self.assertEqual(processor.snapshot("o-1")["version"], 0)
        self.assertEqual(processor.pending_versions("o-1"), [2])

        self.assertEqual(
            processor.deliver(OrderEvent("o-1", 1, "CREATED")),
            EventOutcome.APPLIED,
        )
        self.assertEqual(processor.snapshot("o-1")["version"], 2)
        self.assertEqual(processor.snapshot("o-1")["status"], "PAID")
        self.assertEqual(processor.pending_versions("o-1"), [])

    def test_duplicate_event_is_ignored(self):
        processor = OrderProcessor()
        processor.deliver(OrderEvent("o-2", 1, "CREATED"))
        processor.deliver(OrderEvent("o-2", 2, "PAID"))

        outcome = processor.deliver(OrderEvent("o-2", 2, "PAID"))

        self.assertEqual(outcome, EventOutcome.DUPLICATE_IGNORED)
        self.assertEqual(processor.snapshot("o-2")["version"], 2)

    def test_duplicate_pending_event_is_ignored(self):
        processor = OrderProcessor()
        processor.deliver(OrderEvent("o-3", 3, "SHIPPED"))

        outcome = processor.deliver(OrderEvent("o-3", 3, "SHIPPED"))

        self.assertEqual(outcome, EventOutcome.DUPLICATE_IGNORED)
        self.assertEqual(processor.pending_versions("o-3"), [3])

    def test_missing_versions_prevent_state_jump(self):
        processor = OrderProcessor()

        outcome = processor.deliver(OrderEvent("o-4", 3, "SHIPPED"))

        self.assertEqual(outcome, EventOutcome.BUFFERED)
        self.assertEqual(processor.snapshot("o-4")["version"], 0)
        self.assertEqual(processor.snapshot("o-4")["status"], "NOT_CREATED")
        self.assertEqual(processor.pending_versions("o-4"), [3])
        self.assertIn("missing_versions=[1, 2]", processor.log[-1])


class FencingTokenTests(unittest.TestCase):
    def test_newer_worker_wins_and_stale_worker_is_rejected(self):
        processor = OrderProcessor()
        old_token = processor.issue_fencing_token("worker-A")
        new_token = processor.issue_fencing_token("worker-B")

        newer_result = processor.worker_update(
            order_id="o-5",
            worker_name="worker-B",
            fencing_token=new_token,
            status="SHIPPED",
        )
        stale_result = processor.worker_update(
            order_id="o-5",
            worker_name="worker-A",
            fencing_token=old_token,
            status="CANCELLED",
        )

        self.assertEqual(newer_result, WorkerOutcome.APPLIED)
        self.assertEqual(stale_result, WorkerOutcome.STALE_REJECTED)
        self.assertEqual(processor.snapshot("o-5")["status"], "SHIPPED")
        self.assertEqual(processor.snapshot("o-5")["highest_fencing_token"], 2)


if __name__ == "__main__":
    unittest.main()
