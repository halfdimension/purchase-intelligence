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
    persist_phase1_catalog_bootstrap,
    persist_phase1_watch_materialization,
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
    REQUESTED_VARIANT_NOT_FOUND_ERROR_CODE,
    SCRAPE_FAILED_ERROR_CODE,
    UNSUPPORTED_ADAPTER_ERROR_CODE,
    WATCH_MATERIALIZATION_OUTCOME_UNKNOWN_ERROR_CODE,
    WATCH_MATERIALIZATION_FAILED_ERROR_CODE,
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
