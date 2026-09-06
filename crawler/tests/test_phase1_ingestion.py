from dataclasses import replace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import requests
from postgrest.exceptions import APIError

from crawler.models import ProductData, ProductVariant
from crawler.phase1_ingestion_adapters import (
    NIKE_INGESTION_ADAPTER,
    Phase1IngestionAdapter,
    get_phase1_ingestion_adapter,
)
from crawler.phase1_ingestion_contract import (
    CatalogBootstrapRequest,
    CatalogBootstrapResult,
    CatalogBootstrapVariantResult,
    WatchMaterializationRequest,
)
from crawler.phase1_ingestion_database import (
    TrackingRequestOwnershipLostError,
    claim_phase1_tracking_requests,
    get_phase1_tracking_request_state,
    mark_phase1_tracking_request_failed,
    persist_phase1_catalog_bootstrap,
    persist_phase1_watch_materialization,
    renew_phase1_tracking_request_lease,
)
from crawler.phase1_ingestion_policy import (
    DEFAULT_PHASE1_INGESTION_LEASE_SECONDS,
    MAX_PHASE1_INGESTION_LEASE_SECONDS,
    MIN_PHASE1_INGESTION_LEASE_SECONDS,
    PHASE1_INGESTION_LEASE_SECONDS_ENV,
    Phase1IngestionPolicy,
    load_phase1_ingestion_policy,
    validate_phase1_ingestion_lease_seconds,
)
from crawler.phase1_ingestion_validation import (
    ValidatedIngestionTarget,
)
from crawler.phase1_ingestion_worker import (
    CATALOG_BOOTSTRAP_OUTCOME_UNKNOWN_ERROR_CODE,
    CATALOG_BOOTSTRAP_FAILED_ERROR_CODE,
    DUPLICATE_WATCH_ERROR_CODE,
    INVALID_PRODUCT_ERROR_CODE,
    INVALID_TARGET_ERROR_CODE,
    LEASE_RENEWAL_OUTCOME_UNKNOWN_ERROR_CODE,
    PROCESSING_OWNERSHIP_LOST_ERROR_CODE,
    REQUESTED_VARIANT_NOT_FOUND_ERROR_CODE,
    SCRAPE_FAILED_ERROR_CODE,
    UNSUPPORTED_ADAPTER_ERROR_CODE,
    WATCH_MATERIALIZATION_OUTCOME_UNKNOWN_ERROR_CODE,
    WATCH_MATERIALIZATION_FAILED_ERROR_CODE,
    Phase1IngestionResult,
    PreparedIngestionRequest,
    ProcessingStateError,
    build_phase1_catalog_bootstrap_request,
    build_phase1_ingestion_event_identity,
    process_phase1_ingestion_request,
    process_phase1_ingestion_requests,
)
from crawler.scrapers.browser_jsonld import (
    GuardedMainFrameHttpError,
    _main_frame_document_url,
)
from crawler.scrapers.nike import NikeScraper


class FakeQuery:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return Mock(data=self.data)


class FakeSupabase:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return FakeQuery(self.responses[name])


class FakeTableQuery:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name

    def select(self, columns):
        self.client.calls.append(
            ("select", self.table_name, columns)
        )
        return self

    def update(self, payload):
        self.client.calls.append(
            ("update", self.table_name, payload)
        )
        return self

    def eq(self, column, value):
        self.client.calls.append(
            ("eq", column, value)
        )
        return self

    def limit(self, value):
        self.client.calls.append(
            ("limit", value)
        )
        return self

    def execute(self):
        return Mock(data=self.client.response)


class FakeTableSupabase:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def table(self, name):
        self.calls.append(("table", name))
        return FakeTableQuery(self, name)


class IngestionPolicyTest(unittest.TestCase):
    def test_default_policy_is_explicit_and_valid(self):
        with patch.dict(
            "os.environ",
            {},
            clear=False,
        ):
            # Remove only the ingestion settings while preserving the
            # process environment used by imported crawler modules.
            import os

            os.environ.pop(
                PHASE1_INGESTION_LEASE_SECONDS_ENV,
                None,
            )
            policy = load_phase1_ingestion_policy()

        self.assertEqual(
            policy,
            Phase1IngestionPolicy(
                lease_duration_seconds=(
                    DEFAULT_PHASE1_INGESTION_LEASE_SECONDS
                ),
            ),
        )
        self.assertEqual(
            policy.lease_duration_seconds,
            600,
        )

    def test_policy_reads_valid_environment_overrides(self):
        with patch.dict(
            "os.environ",
            {
                PHASE1_INGESTION_LEASE_SECONDS_ENV: " 900 ",
            },
            clear=False,
        ):
            policy = load_phase1_ingestion_policy()

        self.assertEqual(
            policy.lease_duration_seconds,
            900,
        )

    def test_policy_rejects_malformed_environment_values(self):
        with patch.dict(
            "os.environ",
            {
                PHASE1_INGESTION_LEASE_SECONDS_ENV: "five minutes",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(
                ValueError,
                PHASE1_INGESTION_LEASE_SECONDS_ENV,
            ):
                load_phase1_ingestion_policy()

    def test_policy_rejects_unsafe_lease_bounds(self):
        for lease_seconds in (
            True,
            299,
            1201,
            600.0,
        ):
            with self.subTest(
                lease_seconds=lease_seconds,
            ):
                with self.assertRaises(ValueError):
                    validate_phase1_ingestion_lease_seconds(
                        lease_seconds
                    )

        self.assertEqual(
            validate_phase1_ingestion_lease_seconds(
                MIN_PHASE1_INGESTION_LEASE_SECONDS
            ),
            300,
        )
        self.assertEqual(
            validate_phase1_ingestion_lease_seconds(
                MAX_PHASE1_INGESTION_LEASE_SECONDS
            ),
            1200,
        )


def make_prepared(
    *,
    adapter_key="nike",
    variant_requirements=None,
    target_url=(
        "https://www.nike.in/test/p/123"
    ),
):
    return PreparedIngestionRequest(
        request={
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "requested_url": (
                target_url
            ),
            "normalized_url": (
                target_url
            ),
            "variant_requirements": (
                {"size": "UK 9"}
                if variant_requirements is None
                else variant_requirements
            ),
            "target_price": 10000,
            "target_currency": "INR",
            "conditions": {
                "require_in_stock": True,
            },
            "status": "processing",
            "attempt_count": 2,
            "started_at": (
                "2026-09-05T12:30:00+05:30"
            ),
        },
        target=ValidatedIngestionTarget(
            url=(
                target_url
            ),
            hostname="www.nike.in",
            adapter_key=adapter_key,
            merchant_slug="nike-india",
        ),
    )


def make_product(
    brand="Nike",
    final_url=(
        "https://www.nike.in/test/p/123"
    ),
):
    return ProductData(
        url=final_url,
        name="Nike Test Shoe",
        brand=brand,
        currency="INR",
        mrp=12000,
        current_price=10000,
        image_url="https://example.com/shoe.jpg",
        in_stock=True,
        variants=[
            ProductVariant(
                size="UK 9 (EU 44)",
                sku="sku-9",
                mrp=12000,
                current_price=10000,
                in_stock=True,
                stock_remaining=3,
            )
        ],
    )


def transport_error(message):
    return httpx.ConnectError(
        message,
        request=httpx.Request(
            "POST",
            "https://example.supabase.co/rest/v1/rpc/test",
        ),
    )


def api_error(message):
    return APIError(
        {
            "message": message,
            "code": "P0001",
            "hint": "private hint",
            "details": "private schema detail",
        }
    )


def make_bootstrap_result():
    return CatalogBootstrapResult(
        product_id=str(uuid4()),
        listing_id=str(uuid4()),
        listing_created=True,
        crawl_event_id=str(uuid4()),
        listing_observation_id=1,
        observation_created=True,
        variants=(
            CatalogBootstrapVariantResult(
                variant_key="size:uk-9",
                canonical_variant_id=(
                    str(uuid4())
                ),
                listing_variant_id=str(uuid4()),
            ),
        ),
    )


class NikeScraperFakeTest(unittest.TestCase):
    def test_guarded_final_404_is_rejected(self):
        guarded_scraper = NikeScraper(
            guard_main_frame_navigations=True
        )

        with self.assertRaisesRegex(
            GuardedMainFrameHttpError,
            "404",
        ):
            guarded_scraper.validate_main_frame_response_status(
                404
            )

        NikeScraper().validate_main_frame_response_status(
            404
        )

    def test_guarded_final_200_is_accepted(self):
        scraper = NikeScraper(
            guard_main_frame_navigations=True
        )

        scraper.validate_main_frame_response_status(
            200
        )

    def test_phase1_adapter_enables_main_frame_guard(self):
        product = make_product()

        self.assertFalse(
            NikeScraper().guard_main_frame_navigations
        )

        with patch(
            "crawler.phase1_ingestion_adapters.NikeScraper"
        ) as scraper_class:
            scraper_class.return_value.scrape.return_value = (
                product
            )

            result = NIKE_INGESTION_ADAPTER.scrape(
                "https://www.nike.in/test/p/123"
            )

        self.assertIs(result, product)
        scraper_class.assert_called_once_with(
            guard_main_frame_navigations=True
        )

    def test_browser_guard_distinguishes_main_frame_redirects(self):
        redirect_event = {
            "resourceType": "Document",
            "frameId": "main-frame",
            "request": {
                "url": "https://example.com/redirect",
            },
        }

        self.assertEqual(
            _main_frame_document_url(
                redirect_event,
                "main-frame",
            ),
            "https://example.com/redirect",
        )
        self.assertIsNone(
            _main_frame_document_url(
                {
                    **redirect_event,
                    "resourceType": "Script",
                },
                "main-frame",
            )
        )
        self.assertIsNone(
            _main_frame_document_url(
                {
                    **redirect_event,
                    "frameId": "child-frame",
                },
                "main-frame",
            )
        )

    def test_main_frame_navigation_rejects_external_host(self):
        scraper = NikeScraper()

        with self.assertRaisesRegex(
            ValueError,
            "Nike India hostname",
        ):
            scraper.validate_main_frame_navigation(
                "https://example.com/redirect"
            )

        scraper.validate_main_frame_navigation(
            "https://static.nike.in/canonical/p/123"
        )

    def test_extracts_normalized_product_from_fake_html(self):
        html = """
        <html><head>
          <meta property="og:title" content="Nike Test Shoe">
          <meta property="og:image" content="https://example.com/meta.jpg">
        </head><body>
          <script>
          window.DATA = {
            "skuData": {"product": {
              "price": 12000,
              "discountedPrice": 10000,
              "imageUrl": "https://example.com/shoe.jpg"
            }},
            "sizeOptions": {"options": [
              {
                "sizeName": "UK 9 (EU 44)",
                "sku": "sku-9",
                "price": 12000,
                "discountedPrice": 10000,
                "isOutOfStock": 0,
                "stock_remaining": 3
              }
            ]}
          };
          </script>
        </body></html>
        """

        scraper = NikeScraper()

        with patch.object(
            scraper,
            "fetch_rendered_html",
            return_value=(
                "https://www.nike.in/test/p/123",
                html,
            ),
        ):
            product = scraper.scrape(
                "https://www.nike.in/test/p/123"
            )

        self.assertEqual(product.brand, "Nike")
        self.assertEqual(product.current_price, 10000)
        self.assertEqual(len(product.variants), 1)
        self.assertTrue(product.variants[0].in_stock)
        self.assertEqual(
            product.variants[0].stock_remaining,
            3,
        )


class IngestionDatabaseFakeTest(unittest.TestCase):
    def test_claim_passes_explicit_lease_policy(self):
        request_id = str(uuid4())
        fake = FakeSupabase(
            {
                "claim_tracking_requests": [
                    {
                        "id": request_id,
                        "status": "processing",
                        "attempt_count": 4,
                        "lease_expires_at": (
                            "2026-09-05T08:10:00+00:00"
                        ),
                    }
                ]
            }
        )

        with patch(
            "crawler.phase1_ingestion_database.get_supabase",
            return_value=fake,
        ):
            claimed = claim_phase1_tracking_requests(
                1,
                lease_duration_seconds=600,
            )

        self.assertEqual(claimed[0]["id"], request_id)
        self.assertEqual(
            fake.calls,
            [
                (
                    "claim_tracking_requests",
                    {
                        "p_limit": 1,
                        "p_lease_duration_seconds": 600,
                    },
                )
            ],
        )

    def test_current_attempt_can_renew_lease(self):
        request_id = str(uuid4())
        request = {
            "id": request_id,
            "status": "processing",
            "attempt_count": 2,
        }
        renewed = {
            **request,
            "lease_expires_at": (
                "2026-09-05T08:20:00+00:00"
            ),
        }
        fake = FakeSupabase(
            {
                "renew_tracking_request_lease": [
                    renewed
                ]
            }
        )

        with patch(
            "crawler.phase1_ingestion_database.get_supabase",
            return_value=fake,
        ):
            result = renew_phase1_tracking_request_lease(
                request,
                lease_duration_seconds=600,
            )

        self.assertEqual(result, renewed)
        self.assertEqual(
            fake.calls[0][1],
            {
                "p_tracking_request_id": request_id,
                "p_attempt_count": 2,
                "p_lease_duration_seconds": 600,
            },
        )

    def test_stale_attempt_cannot_renew_or_mark_failed(self):
        request = {
            "id": str(uuid4()),
            "status": "processing",
            "attempt_count": 2,
        }

        with patch(
            "crawler.phase1_ingestion_database.get_supabase",
            return_value=FakeSupabase(
                {"renew_tracking_request_lease": []}
            ),
        ):
            with self.assertRaises(
                TrackingRequestOwnershipLostError
            ):
                renew_phase1_tracking_request_lease(
                    request,
                    lease_duration_seconds=600,
                )

        fake_table = FakeTableSupabase([])

        with patch(
            "crawler.phase1_ingestion_database.get_supabase",
            return_value=fake_table,
        ):
            with self.assertRaises(
                TrackingRequestOwnershipLostError
            ):
                mark_phase1_tracking_request_failed(
                    request,
                    error_code="safe_failure",
                    error_message="Safe failure.",
                )

        self.assertIn(
            ("eq", "attempt_count", 2),
            fake_table.calls,
        )

    def test_reconciliation_reads_authoritative_request_state(self):
        request = {
            "id": str(uuid4()),
            "status": "processing",
            "attempt_count": 2,
        }
        state = {
            **request,
            "status": "completed",
            "result_product_id": str(uuid4()),
            "result_listing_id": str(uuid4()),
            "result_watch_id": str(uuid4()),
            "error_code": None,
        }
        fake = FakeTableSupabase([state])

        with patch(
            "crawler.phase1_ingestion_database.get_supabase",
            return_value=fake,
        ):
            result = get_phase1_tracking_request_state(
                request
            )

        self.assertEqual(result, state)
        self.assertIn(
            ("eq", "id", request["id"]),
            fake.calls,
        )

    def test_catalog_and_materialization_rpc_contracts(self):
        product_id = str(uuid4())
        listing_id = str(uuid4())
        watch_id = str(uuid4())
        request_id = str(uuid4())
        crawl_event_id = str(uuid4())
        canonical_variant_id = str(uuid4())

        fake = FakeSupabase(
            {
                "bootstrap_phase1_catalog": {
                    "product_id": product_id,
                    "listing_id": listing_id,
                    "listing_created": True,
                    "crawl_event_id": crawl_event_id,
                    "listing_observation_id": 1,
                    "observation_created": True,
                    "variants": [],
                },
                "materialize_phase1_tracking_request": {
                    "outcome": "completed",
                    "tracking_request_id": request_id,
                    "product_id": product_id,
                    "listing_id": listing_id,
                    "watch_id": watch_id,
                    "already_completed": False,
                },
            }
        )

        bootstrap_request = CatalogBootstrapRequest(
            merchant_slug="nike-india",
            adapter_key="nike",
            brand_slug="nike",
            normalized_url=(
                "https://www.nike.in/test/p/123"
            ),
            crawl_event_id=crawl_event_id,
            checked_at="2026-09-05T07:00:00+00:00",
            product={"name": "Nike Test Shoe"},
        )

        materialization_request = (
            WatchMaterializationRequest(
                tracking_request_id=request_id,
                attempt_count=2,
                product_id=product_id,
                listing_id=listing_id,
                normalized_url=(
                    "https://www.nike.in/test/p/123"
                ),
                canonical_variant_id=(
                    canonical_variant_id
                ),
                variant_key="size:uk-9",
            )
        )

        with patch(
            "crawler.phase1_ingestion_database.get_supabase",
            return_value=fake,
        ):
            bootstrap = (
                persist_phase1_catalog_bootstrap(
                    bootstrap_request
                )
            )
            materialization = (
                persist_phase1_watch_materialization(
                    materialization_request
                )
            )

        self.assertEqual(bootstrap.product_id, product_id)
        self.assertEqual(materialization.watch_id, watch_id)
        self.assertEqual(
            [call[0] for call in fake.calls],
            [
                "bootstrap_phase1_catalog",
                "materialize_phase1_tracking_request",
            ],
        )


class IngestionWorkerTest(unittest.TestCase):
    def setUp(self):
        self.prepared = make_prepared()
        self.product = make_product()
        self.bootstrap = make_bootstrap_result()
        self.materialization = Mock(
            outcome="completed",
            tracking_request_id=(
                self.prepared.request["id"]
            ),
            product_id=self.bootstrap.product_id,
            listing_id=self.bootstrap.listing_id,
            watch_id=str(uuid4()),
            already_completed=False,
        )

        nike_adapter = (
            get_phase1_ingestion_adapter(
                "nike"
            )
        )

        self.adapter = Phase1IngestionAdapter(
            key="nike",
            brand_slug="nike",
            scrape=Mock(return_value=self.product),
            build_product_payload=(
                nike_adapter.build_product_payload
            ),
            requested_variant_key=(
                nike_adapter.requested_variant_key
            ),
            validate_target_url=(
                nike_adapter.validate_target_url
            ),
            validate_scraped_product=(
                nike_adapter.validate_scraped_product
            ),
        )

        lease_patcher = patch(
            "crawler.phase1_ingestion_worker."
            "renew_phase1_tracking_request_lease",
            return_value={
                **self.prepared.request,
                "lease_expires_at": (
                    "2026-09-05T07:10:00+00:00"
                ),
            },
        )
        self.renew_lease = lease_patcher.start()
        self.addCleanup(lease_patcher.stop)

    def test_happy_path_and_stable_retry_identity(self):
        bootstrap_calls = []

        def persist_bootstrap(request):
            bootstrap_calls.append(request)

            if len(bootstrap_calls) == 1:
                raise transport_error(
                    "response lost after bootstrap"
                )

            return self.bootstrap

        materialization_calls = []

        def persist_materialization(request):
            materialization_calls.append(
                request
            )

            if len(materialization_calls) == 1:
                raise transport_error(
                    "response lost after completion"
                )

            return self.materialization

        with (
            patch(
                "crawler.phase1_ingestion_worker.get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker.persist_phase1_catalog_bootstrap",
                side_effect=persist_bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker.persist_phase1_watch_materialization",
                side_effect=persist_materialization,
            ),
            patch(
                "crawler.phase1_ingestion_worker.mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            self.renew_lease.call_count,
            3,
        )
        self.assertEqual(len(bootstrap_calls), 2)
        self.assertEqual(
            bootstrap_calls[0],
            bootstrap_calls[1],
        )
        self.assertEqual(
            bootstrap_calls[0].checked_at,
            "2026-09-05T07:00:00+00:00",
        )
        self.assertEqual(
            bootstrap_calls[0].crawl_event_id,
            build_phase1_ingestion_event_identity(
                self.prepared
            )[0],
        )
        self.assertEqual(
            materialization_calls[0],
            materialization_calls[1],
        )
        watch_request = materialization_calls[0]
        self.assertEqual(
            watch_request.variant_key,
            "size:uk-9",
        )
        mark_failed.assert_not_called()

    def test_non_product_target_is_rejected_before_scrape(self):
        prepared = make_prepared(
            target_url="https://www.nike.in/w/new-releases"
        )
        scrape = Mock(return_value=self.product)
        adapter = replace(
            self.adapter,
            scrape=scrape,
        )
        failed = {
            "id": prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ),
        ):
            result = process_phase1_ingestion_request(
                prepared
            )

        self.assertEqual(
            result.error_code,
            INVALID_TARGET_ERROR_CODE,
        )
        scrape.assert_not_called()

    def test_external_final_url_is_rejected(self):
        product = make_product(
            final_url="https://example.com/test/p/123"
        )
        adapter = replace(
            self.adapter,
            scrape=Mock(return_value=product),
        )
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap"
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ),
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            result.error_code,
            INVALID_PRODUCT_ERROR_CODE,
        )
        persist_bootstrap.assert_not_called()

    def test_different_nike_product_identity_is_rejected(self):
        product = make_product(
            final_url=(
                "https://www.nike.in/new-name/p/999"
            )
        )
        adapter = replace(
            self.adapter,
            scrape=Mock(return_value=product),
        )
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap"
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ),
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            result.error_code,
            INVALID_PRODUCT_ERROR_CODE,
        )
        persist_bootstrap.assert_not_called()

    def test_canonical_redirect_with_same_product_identity_is_accepted(self):
        product = make_product(
            final_url=(
                "https://nike.in/canonical-product-name/p/123?locale=en-IN"
            )
        )
        adapter = replace(
            self.adapter,
            scrape=Mock(return_value=product),
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                return_value=self.materialization,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "completed")
        mark_failed.assert_not_called()

    def test_scraper_failure_is_persisted(self):
        self.adapter = Phase1IngestionAdapter(
            key="nike",
            brand_slug="nike",
            scrape=Mock(
                side_effect=requests.ConnectionError(
                    "SECRET proxy credential"
                )
            ),
            build_product_payload=(
                self.adapter.build_product_payload
            ),
            requested_variant_key=(
                self.adapter.requested_variant_key
            ),
            validate_target_url=(
                self.adapter.validate_target_url
            ),
            validate_scraped_product=(
                self.adapter.validate_scraped_product
            ),
        )

        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker.get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker.mark_phase1_tracking_request_failed",
                return_value=failed,
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.error_code,
            SCRAPE_FAILED_ERROR_CODE,
        )
        self.assertEqual(
            mark_failed.call_args.kwargs[
                "error_code"
            ],
            SCRAPE_FAILED_ERROR_CODE,
        )
        self.assertNotIn(
            "SECRET",
            mark_failed.call_args.kwargs[
                "error_message"
            ],
        )

    def test_guarded_http_error_uses_scrape_failure_path(self):
        adapter = replace(
            self.adapter,
            scrape=Mock(
                side_effect=GuardedMainFrameHttpError(
                    "Guarded retailer page returned HTTP status 404."
                )
            ),
        )
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            result.error_code,
            SCRAPE_FAILED_ERROR_CODE,
        )
        self.assertNotIn(
            "404",
            mark_failed.call_args.kwargs[
                "error_message"
            ],
        )

    def test_runtime_contract_failure_is_not_retried_or_hidden(self):
        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                side_effect=RuntimeError(
                    "malformed RPC identity"
                ),
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "malformed RPC identity",
            ):
                process_phase1_ingestion_request(
                    self.prepared
                )

        self.assertEqual(
            persist_bootstrap.call_count,
            1,
        )
        mark_failed.assert_not_called()

    def test_runtime_after_transport_retry_remains_visible(self):
        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                side_effect=[
                    transport_error(
                        "first response lost"
                    ),
                    RuntimeError(
                        "malformed retry result"
                    ),
                ],
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "malformed retry result",
            ):
                process_phase1_ingestion_request(
                    self.prepared
                )

        self.assertEqual(
            persist_bootstrap.call_count,
            2,
        )
        mark_failed.assert_not_called()

    def test_api_failure_is_not_retried_and_message_is_safe(self):
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        internal_detail = (
            "SECRET service key; relation private.catalog_internal"
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                side_effect=api_error(
                    internal_detail
                ),
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            persist_bootstrap.call_count,
            1,
        )
        self.assertEqual(
            result.error_code,
            CATALOG_BOOTSTRAP_FAILED_ERROR_CODE,
        )
        persisted_message = (
            mark_failed.call_args.kwargs[
                "error_message"
            ]
        )
        self.assertNotIn(
            "SECRET",
            persisted_message,
        )
        self.assertNotIn(
            "private.catalog_internal",
            persisted_message,
        )

    def test_api_failure_after_transport_retry_is_controlled(self):
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                side_effect=[
                    transport_error(
                        "first response lost"
                    ),
                    api_error(
                        "SECRET deterministic API failure"
                    ),
                ],
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            persist_bootstrap.call_count,
            2,
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.error_code,
            CATALOG_BOOTSTRAP_FAILED_ERROR_CODE,
        )
        self.assertNotIn(
            "SECRET",
            mark_failed.call_args.kwargs[
                "error_message"
            ],
        )

    def test_exhausted_transport_retry_leaves_request_processing(self):
        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                side_effect=[
                    transport_error(
                        "first response lost"
                    ),
                    transport_error(
                        "retry response lost"
                    ),
                ],
            ) as persist_bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            persist_bootstrap.call_count,
            2,
        )
        self.assertEqual(
            result.status,
            "processing",
        )
        self.assertEqual(
            result.error_code,
            CATALOG_BOOTSTRAP_OUTCOME_UNKNOWN_ERROR_CODE,
        )
        mark_failed.assert_not_called()

    def test_wrong_adapter_is_rejected_before_scrape(self):
        prepared = make_prepared(
            adapter_key="other"
        )
        failed = {
            "id": prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker.get_phase1_ingestion_adapter",
                side_effect=ValueError(
                    "Unsupported ingestion adapter"
                ),
            ),
            patch(
                "crawler.phase1_ingestion_worker.mark_phase1_tracking_request_failed",
                return_value=failed,
            ),
        ):
            result = process_phase1_ingestion_request(
                prepared
            )

        self.assertEqual(
            result.error_code,
            UNSUPPORTED_ADAPTER_ERROR_CODE,
        )

    def test_invalid_claim_started_at_is_operator_visible(self):
        self.prepared.request["started_at"] = (
            "not-a-timestamp"
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            with self.assertRaisesRegex(
                ProcessingStateError,
                "started_at",
            ):
                process_phase1_ingestion_request(
                    self.prepared
                )

        self.adapter.scrape.assert_not_called()
        mark_failed.assert_not_called()

    def test_reclaimed_attempt_gets_a_new_catalog_event_identity(self):
        original_event, _ = (
            build_phase1_ingestion_event_identity(
                self.prepared
            )
        )
        reclaimed_request = {
            **self.prepared.request,
            "attempt_count": 3,
            "started_at": (
                "2026-09-05T07:15:00+00:00"
            ),
        }
        reclaimed = replace(
            self.prepared,
            request=reclaimed_request,
        )
        reclaimed_event, _ = (
            build_phase1_ingestion_event_identity(
                reclaimed
            )
        )

        self.assertNotEqual(
            original_event,
            reclaimed_event,
        )

    def test_high_level_processor_rejects_batch_claim(self):
        with patch(
            "crawler.phase1_ingestion_worker."
            "prepare_phase1_ingestion_requests"
        ) as prepare:
            with self.assertRaisesRegex(
                ValueError,
                "exactly one",
            ):
                process_phase1_ingestion_requests(
                    2
                )

        prepare.assert_not_called()

    def test_high_level_processor_processes_one_claimed_item(self):
        processed = Phase1IngestionResult(
            tracking_request_id=(
                self.prepared.request["id"]
            ),
            status="completed",
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "prepare_phase1_ingestion_requests",
                return_value=[self.prepared],
            ) as prepare,
            patch(
                "crawler.phase1_ingestion_worker."
                "process_phase1_ingestion_request",
                return_value=processed,
            ) as process_one,
        ):
            results = process_phase1_ingestion_requests()

        self.assertEqual(results, [processed])
        prepare.assert_called_once_with(1)
        process_one.assert_called_once_with(
            self.prepared
        )

    def test_missing_requested_variant_is_persisted(self):
        bootstrap = CatalogBootstrapResult(
            product_id=self.bootstrap.product_id,
            listing_id=self.bootstrap.listing_id,
            listing_created=True,
            crawl_event_id=self.bootstrap.crawl_event_id,
            listing_observation_id=1,
            observation_created=True,
            variants=(),
        )
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(
            result.error_code,
            REQUESTED_VARIANT_NOT_FOUND_ERROR_CODE,
        )

    def test_materialization_api_failure_is_persisted_safely(self):
        failed = {
            "id": self.prepared.request["id"],
            "status": "failed",
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=api_error(
                    "SECRET watch_intents constraint detail"
                ),
            ) as persist_watch,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                return_value=failed,
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(persist_watch.call_count, 1)
        self.assertEqual(
            result.error_code,
            WATCH_MATERIALIZATION_FAILED_ERROR_CODE,
        )
        self.assertNotIn(
            "SECRET",
            (
                mark_failed.call_args.kwargs[
                    "error_message"
                ]
            ),
        )

    def test_stage_boundary_renewals_surround_long_operations(self):
        events = []

        def renew(*args, **kwargs):
            events.append("renew")
            return {
                **self.prepared.request,
                "lease_expires_at": (
                    "2026-09-05T07:10:00+00:00"
                ),
            }

        def scrape(url):
            events.append("scrape")
            return self.product

        def bootstrap(request):
            events.append("bootstrap")
            return self.bootstrap

        def materialize(request):
            events.append("materialize")
            return self.materialization

        self.renew_lease.side_effect = renew
        adapter = replace(
            self.adapter,
            scrape=scrape,
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                side_effect=bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=materialize,
            ),
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            events,
            [
                "renew",
                "scrape",
                "renew",
                "bootstrap",
                "renew",
                "materialize",
            ],
        )

    def test_confirmed_lease_loss_stops_before_scrape(self):
        self.renew_lease.side_effect = (
            TrackingRequestOwnershipLostError(
                "attempt was reclaimed"
            )
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap"
            ) as bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization"
            ) as materialize,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "ownership_lost")
        self.assertEqual(
            result.error_code,
            PROCESSING_OWNERSHIP_LOST_ERROR_CODE,
        )
        self.adapter.scrape.assert_not_called()
        bootstrap.assert_not_called()
        materialize.assert_not_called()

    def test_ambiguous_lease_renewal_stops_before_side_effects(self):
        self.renew_lease.side_effect = [
            transport_error("renew response lost"),
            transport_error("renew retry response lost"),
        ]

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap"
            ) as bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization"
            ) as materialize,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "processing")
        self.assertEqual(
            result.error_code,
            LEASE_RENEWAL_OUTCOME_UNKNOWN_ERROR_CODE,
        )
        self.assertEqual(self.renew_lease.call_count, 2)
        self.adapter.scrape.assert_not_called()
        bootstrap.assert_not_called()
        materialize.assert_not_called()
        mark_failed.assert_not_called()

    def test_lease_loss_after_bootstrap_prevents_materialization(self):
        renewed = {
            **self.prepared.request,
            "lease_expires_at": (
                "2026-09-05T07:10:00+00:00"
            ),
        }
        self.renew_lease.side_effect = [
            renewed,
            renewed,
            TrackingRequestOwnershipLostError(
                "attempt reclaimed after bootstrap"
            ),
        ]

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ) as bootstrap,
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization"
            ) as materialize,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "ownership_lost")
        bootstrap.assert_called_once()
        materialize.assert_not_called()
        mark_failed.assert_not_called()

    def test_stale_failure_is_reported_as_ownership_loss(self):
        adapter = replace(
            self.adapter,
            scrape=Mock(
                side_effect=requests.ConnectionError(
                    "scrape failed"
                )
            ),
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                side_effect=(
                    TrackingRequestOwnershipLostError(
                        "attempt was reclaimed"
                    )
                ),
            ),
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "ownership_lost")
        self.assertEqual(
            result.error_code,
            PROCESSING_OWNERSHIP_LOST_ERROR_CODE,
        )

    def test_stale_materialization_cannot_mark_new_attempt_failed(self):
        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=api_error("attempt is stale"),
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed",
                side_effect=(
                    TrackingRequestOwnershipLostError(
                        "newer attempt owns request"
                    )
                ),
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "ownership_lost")
        mark_failed.assert_called_once()

    def test_ambiguous_materialization_reconciles_completion(self):
        watch_id = str(uuid4())
        committed_state = {
            **self.prepared.request,
            "status": "completed",
            "result_product_id": self.bootstrap.product_id,
            "result_listing_id": self.bootstrap.listing_id,
            "result_watch_id": watch_id,
            "error_code": None,
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=[
                    transport_error("commit response lost"),
                    transport_error("replay response lost"),
                ],
            ) as materialize,
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_tracking_request_state",
                return_value=committed_state,
            ) as reconcile,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.watch_id, watch_id)
        self.assertEqual(materialize.call_count, 2)
        reconcile.assert_called_once_with(
            self.prepared.request
        )

    def test_ambiguous_duplicate_materialization_reconciles_failure(self):
        duplicate_state = {
            **self.prepared.request,
            "status": "failed",
            "result_product_id": None,
            "result_listing_id": None,
            "result_watch_id": None,
            "error_code": DUPLICATE_WATCH_ERROR_CODE,
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=[
                    transport_error("duplicate response lost"),
                    transport_error("duplicate replay lost"),
                ],
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_tracking_request_state",
                return_value=duplicate_state,
            ),
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.error_code,
            DUPLICATE_WATCH_ERROR_CODE,
        )

    def test_ambiguous_materialization_observes_newer_attempt_as_loss(self):
        reclaimed_state = {
            **self.prepared.request,
            "status": "processing",
            "attempt_count": (
                self.prepared.request["attempt_count"]
                + 1
            ),
            "result_product_id": None,
            "result_listing_id": None,
            "result_watch_id": None,
            "error_code": None,
        }

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=[
                    transport_error("materialization response lost"),
                    transport_error("materialization replay lost"),
                ],
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_tracking_request_state",
                return_value=reclaimed_state,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "ownership_lost")
        self.assertEqual(
            result.error_code,
            PROCESSING_OWNERSHIP_LOST_ERROR_CODE,
        )
        mark_failed.assert_not_called()

    def test_unknown_materialization_outcome_stays_processing(self):
        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                side_effect=[
                    transport_error(
                        "completion response lost"
                    ),
                    transport_error(
                        "reconciliation response lost"
                    ),
                ],
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_tracking_request_state",
                return_value={
                    **self.prepared.request,
                    "status": "processing",
                    "result_product_id": None,
                    "result_listing_id": None,
                    "result_watch_id": None,
                    "error_code": None,
                },
            ) as reconcile,
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "processing")
        self.assertEqual(
            result.error_code,
            WATCH_MATERIALIZATION_OUTCOME_UNKNOWN_ERROR_CODE,
        )
        reconcile.assert_called_once_with(
            self.prepared.request
        )
        mark_failed.assert_not_called()

    def test_duplicate_watch_result_is_not_completed(self):
        duplicate = Mock(
            outcome="duplicate_watch",
            tracking_request_id=(
                self.prepared.request["id"]
            ),
            product_id=self.bootstrap.product_id,
            listing_id=self.bootstrap.listing_id,
            watch_id=str(uuid4()),
            already_completed=False,
        )

        with (
            patch(
                "crawler.phase1_ingestion_worker."
                "get_phase1_ingestion_adapter",
                return_value=self.adapter,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_catalog_bootstrap",
                return_value=self.bootstrap,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "persist_phase1_watch_materialization",
                return_value=duplicate,
            ),
            patch(
                "crawler.phase1_ingestion_worker."
                "mark_phase1_tracking_request_failed"
            ) as mark_failed,
        ):
            result = process_phase1_ingestion_request(
                self.prepared
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.error_code,
            DUPLICATE_WATCH_ERROR_CODE,
        )
        mark_failed.assert_not_called()

    def test_wrong_brand_is_rejected_by_nike_adapter(self):
        prepared = make_prepared()

        with self.assertRaisesRegex(
            ValueError,
            "unexpected brand",
        ):
            build_phase1_catalog_bootstrap_request(
                prepared,
                make_product(brand="Adidas"),
                crawl_event_id=str(uuid4()),
                checked_at=(
                    "2026-09-05T07:00:00+00:00"
                ),
            )


if __name__ == "__main__":
    unittest.main()
