# Repository Instructions for AI Coding Agents

Before significant work, read:

1. `PROJECT_CONTEXT.md`
2. relevant files under `docs/`
3. existing migrations under `supabase/migrations/`
4. relevant implementation files

This repository is an evolving production-style project, not a disposable demo.

## Core Rule

Do not add features merely because they are convenient to implement.

Significant changes must remain consistent with the architecture and product direction documented in `PROJECT_CONTEXT.md`.

If work materially changes architecture:

1. inspect the current implementation,
2. understand existing behavior,
3. document the intended architecture,
4. identify migration/compatibility impact,
5. implement in verified milestones.

Do not leave important architecture decisions only in chat history.

## Development Workflow

For each meaningful milestone:

1. modify code,
2. run relevant validation,
3. manually verify behavior where necessary,
4. inspect `git diff`,
5. commit with a meaningful message,
6. push to GitHub,
7. update project documentation when architecture or working scope changed.

GitHub is the durable project history and source of truth.

## Important Project Files

`PROJECT_CONTEXT.md`
- product vision
- current working state
- architecture direction
- roadmap
- major decisions

`AGENTS.md`
- instructions for AI/Codex sessions

`docs/`
- detailed architecture/design documents
- `docs/phase-2-general-purchase-intelligence.md` is the target design and
  ordered roadmap for general discovery, comparison, tracking, and purchase
  intelligence beyond the Nike-specific Phase 1 implementation

`supabase/migrations/`
- database evolution

`.github/workflows/`
- automation and scheduled jobs

## Security

Never commit:

- `.env`
- `.env.local`
- Supabase secret/service keys
- Resend API keys
- access tokens
- passwords

Secrets belong in:

- ignored local environment files
- deployment environment variables
- GitHub Actions Secrets

## Validation

For frontend changes:

cd apps/web
npm run lint
npm run build

For changed Python files, run `python -m py_compile` followed by the actual Python file paths.

For crawler integration when appropriate:

python -m crawler.run_tracked

If GitHub Actions behavior changes, manually dispatch the workflow and inspect the cloud run.

## Database Changes

Long-term database changes must be represented by SQL migrations under:

`supabase/migrations/`

If a migration must be executed manually in Supabase, clearly tell the human operator:

- which migration to run,
- what it changes,
- how to verify success.

Do not make undocumented production-schema changes.

## Scraper Architecture

Retailer-specific extraction belongs behind adapters/providers.

Do not expose retailer-specific HTML, embedded JSON, selectors, or scraping details directly to frontend components.

Normalize retailer data into shared internal domain models.

## AI / ML

Do not introduce ML just for novelty.

Live products, prices, stock and offers must come from real retrieval/provider/crawler data.

AI can later be used for:

- conversational intent interpretation,
- product/category classification when deterministic evidence is insufficient,
- attribute extraction from unstructured product data,
- product/listing matching,
- ranking,
- grounded recommendation explanations,
- personalization.

Price prediction and other learned models should only be introduced when enough real historical data exists.

## Current Architectural Warning

The repository is currently in a migration window between legacy Phase 0
compatibility and the active Phase 1 model.

Do not deepen dependencies on legacy Phase 0 assumptions:

- legacy `products` mixes canonical-product and merchant-listing concerns,
- legacy ownership is email-based,
- legacy `desired_size` is category-specific,
- legacy `price_snapshots` still supports the current price-history read path,
- Phase 0 product/snapshot compatibility writes remain temporarily.

The active Phase 1 architecture already uses:

- Supabase Auth-backed identity,
- canonical products and canonical variants,
- merchant listings and listing variants,
- authenticated `watch_intents`,
- Phase 1-driven crawl scheduling,
- Phase 1 observations,
- Phase 1 evaluation and notifications.

Read `PROJECT_CONTEXT.md`, `docs/phase-1-domain-architecture.md`,
`docs/phase-1-new-product-ingestion.md`, and
`docs/phase-2-general-purchase-intelligence.md` before changing these
boundaries.

## Large Refactors

For substantial multi-file architecture changes, prefer Codex or another repository-aware coding agent rather than dozens of fragile terminal patches.

Before a large refactor:

1. make sure Git is clean,
2. push a checkpoint,
3. document the target design,
4. identify migration strategy,
5. then perform the refactor.
