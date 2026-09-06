from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from crawler.phase1_ingestion_worker import (
    Phase1IngestionResult,
)
from crawler.run_phase1_ingestion import main


SAFE_OUTPUT_FIELDS = {
    "event",
    "tracking_request_id",
    "status",
    "product_id",
    "listing_id",
    "watch_id",
    "error_code",
}


class RunPhase1IngestionTest(unittest.TestCase):
    def _run_with_results(
        self,
        results: list[Phase1IngestionResult],
    ) -> tuple[int, dict]:
        output = StringIO()

        with (
            patch(
                "crawler.run_phase1_ingestion."
                "process_phase1_ingestion_requests",
                return_value=results,
            ) as process,
            redirect_stdout(output),
        ):
            exit_code = main()

        process.assert_called_once_with(limit=1)

        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)

        return exit_code, json.loads(lines[0])

    def _result(
        self,
        status: str,
        *,
        error_code: str | None = None,
    ) -> Phase1IngestionResult:
        return Phase1IngestionResult(
            tracking_request_id="tracking-request-id",
            status=status,
            product_id="product-id",
            listing_id="listing-id",
            watch_id="watch-id",
            error_code=error_code,
        )

    def test_no_work_calls_worker_once_and_exits_zero(self):
        exit_code, payload = self._run_with_results([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload,
            {
                "event": "phase1_ingestion_runner",
                "tracking_request_id": None,
                "status": "no_work",
                "product_id": None,
                "listing_id": None,
                "watch_id": None,
                "error_code": None,
            },
        )

    def test_completed_exits_zero_with_safe_result_fields(self):
        exit_code, payload = self._run_with_results(
            [self._result("completed")]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            set(payload),
            SAFE_OUTPUT_FIELDS,
        )
        self.assertEqual(
            payload,
            {
                "event": "phase1_ingestion_runner",
                "tracking_request_id": (
                    "tracking-request-id"
                ),
                "status": "completed",
                "product_id": "product-id",
                "listing_id": "listing-id",
                "watch_id": "watch-id",
                "error_code": None,
            },
        )

    def test_failed_exits_zero(self):
        exit_code, payload = self._run_with_results(
            [
                self._result(
                    "failed",
                    error_code="duplicate_watch",
                )
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(
            payload["error_code"],
            "duplicate_watch",
        )

    def test_cancelled_exits_zero(self):
        exit_code, payload = self._run_with_results(
            [self._result("cancelled")]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "cancelled")

    def test_ownership_lost_exits_zero(self):
        exit_code, payload = self._run_with_results(
            [self._result("ownership_lost")]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload["status"],
            "ownership_lost",
        )

    def test_processing_exits_two(self):
        exit_code, payload = self._run_with_results(
            [
                self._result(
                    "processing",
                    error_code=(
                        "catalog_bootstrap_outcome_unknown"
                    ),
                )
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "processing")
        self.assertEqual(
            payload["error_code"],
            "catalog_bootstrap_outcome_unknown",
        )

    def test_unknown_status_exits_one(self):
        exit_code, payload = self._run_with_results(
            [self._result("unexpected")]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            payload["status"],
            "runner_failed",
        )
        self.assertEqual(
            payload["error_code"],
            "unknown_result_status",
        )

    def test_more_than_one_result_exits_one(self):
        exit_code, payload = self._run_with_results(
            [
                self._result("completed"),
                self._result("completed"),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(
            payload["status"],
            "runner_failed",
        )
        self.assertEqual(
            payload["error_code"],
            "unexpected_result_cardinality",
        )

    def test_unexpected_exception_exits_one_without_private_detail(self):
        output = StringIO()
        private_detail = (
            "PRIVATE PostgREST constraint detail"
        )

        with (
            patch(
                "crawler.run_phase1_ingestion."
                "process_phase1_ingestion_requests",
                side_effect=RuntimeError(
                    private_detail
                ),
            ) as process,
            self.assertLogs(
                "crawler.run_phase1_ingestion",
                level="ERROR",
            ),
            redirect_stdout(output),
        ):
            exit_code = main()

        process.assert_called_once_with(limit=1)
        self.assertEqual(exit_code, 1)

        payload = json.loads(
            output.getvalue()
        )
        self.assertEqual(
            payload["status"],
            "runner_failed",
        )
        self.assertEqual(
            payload["error_code"],
            "unexpected_exception",
        )
        self.assertNotIn(
            private_detail,
            output.getvalue(),
        )
        self.assertEqual(
            set(payload),
            SAFE_OUTPUT_FIELDS,
        )

    def test_system_exit_is_not_caught(self):
        with patch(
            "crawler.run_phase1_ingestion."
            "process_phase1_ingestion_requests",
            side_effect=SystemExit(7),
        ) as process:
            with self.assertRaises(SystemExit) as raised:
                main()

        process.assert_called_once_with(limit=1)
        self.assertEqual(raised.exception.code, 7)


if __name__ == "__main__":
    unittest.main()
