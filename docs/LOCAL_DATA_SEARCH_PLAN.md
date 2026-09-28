# Local search, ingestion, and administration plan

Status: approved for implementation on 2026-09-28. Baseline Git tag:
`pre-local-search-entity-ingest-20260928`. This is the implementation contract;
individual stages must be validated before they replace the existing live paths.

Implementation note: the application and its existing live searches remain in
service during the backfill. The new schedules and local search begin disabled
in each environment's YAML. Enable them only after index counts, freshness,
filter semantics, and daily notification results have been checked. The four
intraday polls are best-effort freshness improvements, not guaranteed
real-time notice updates, because the public opportunity API exposes posted
dates but no documented modified-date filter.

## Goals and constraints

- Search a locally indexed copy of public active SAM opportunities and entities,
  rather than making a SAM API request per user search. Continue to offer an
  explicit live SAM lookup for a notice ID or UEI missing from the local copy.
  SAM's public opportunities API returns the latest active notice, so an
  unmatched/archived notice ID also gets a direct SAM.gov page link rather
  than a claim that the API can retrieve its inactive details.
- Preserve existing saved searches, saved items, daily notification definitions,
  Cognito identities, company profiles, and per-user AI feature flags.
- Keep public search and the Tabler administration UI separate at environment-
  aware `app` and `admin` hostnames; share one Cognito user pool and session.
- No permanently running database or container, OpenSearch, or NAT gateway.
  Provision infrastructure with CloudFormation and keep secrets in SSM.
- Download public data only. Do not download notice attachments or restricted
  FOUO/CUI entity extracts.

## Opportunity data

1. Backfill from SAM's active Contract Opportunities full CSV. It carries
   first-level fields, including description, but not attachments. Keep the raw
   versioned file in S3 and build a new immutable SQLite/FTS5 index from it.
2. Refresh from the full active CSV daily. Treat it as an authoritative active
   snapshot: records absent from the new snapshot become inactive in local
   search. Validate row count, uniqueness, required columns, and build integrity
   before switching an S3 manifest to the new index.
   Obtain the public CSV through SAM.gov's Data Services download route, which
   redirects to a short-lived signed S3 URL; the S3 object URL alone is not a
   stable unauthenticated download endpoint.
3. Run configurable incremental API polls at 08:00, 11:00, 14:00, and 17:00
   America/New_York by default. The public API documents posted-date filters,
   not an updated-date filter, so poll overlapping recent posted dates,
   deduplicate by notice ID, and overlay newer API records over the daily base.
   Changes to older notices may not appear until the next full snapshot.
   The next full snapshot clears stale overlay rows. Do not infer that an
   opportunity is inactive solely because a delta poll omitted it.
4. Index title, description, agency/organization, notice type, NAICS, PSC,
   set-aside, place of performance, posted date, and response deadline. Retain
   the SAM URL and source timestamps. Do not ingest attachments.
5. Continue the existing notification schedules and emails, but select each
   notification's matches from the locally ingested posted-today/yesterday
   records. Run notifications only after the daily index is published; failures
   should be visible and retryable without duplicating emails.

## Entity data

1. On the first Sunday of each month, download the public monthly entity ZIP.
   The file includes active entities plus entities expired in the preceding six
   months, so filter to active registrations during indexing. Build and validate
   a replacement SQLite index, then atomically publish it.
2. Each day request an asynchronous public Entity Management API export with
   `updateDate`, `registrationStatus=A`, and `format=json`. Save the generated
   file to S3, then apply its rows as upserts in a small daily overlay. SAM may
   take time to generate the file: persist its token/status and poll later,
   never sleep through a Lambda execution. JSON avoids the CSV-to-JSON parser
   mismatch in old GovVue. No synchronous 10-record-per-page fallback for bulk
   updates.
3. On monthly replacement, replay all daily files newer than the monthly
   snapshot date before publishing. Keep the prior index version for rollback.
4. Expire registrations by their local expiration date. Active-only deltas do
   not reliably report early deactivations; such records may remain searchable
   until the next monthly replacement. Label entity freshness clearly. A
   targeted live UEI lookup can check status when the user opens a record.
5. Keep saved entities in the existing user-owned DynamoDB records; replacing
   the search index must not delete saved records.

## Search behavior

- Local search preserves current manual filters and saved-search schemas.
  Values within a field are OR; different fields are AND. Full-text title and
  description search supports multiple terms. Include/exclude agency, terms,
  and notice types as explicit local criteria where the UI exposes them.
- Remove the 12-SAM-request fan-out restriction, the 24-upstream-page sorting
  restriction, and the arbitrary 20-value-per-field selection cap from the
  **local** path. Keep reasonable input byte/term limits and query timeouts to
  protect the service; these are not SAM fan-out limits. An explicit live SAM
  fallback remains subject to its own API constraints.
- Apply all selected filters to the entire local result set, then sort and
  paginate deterministically. Do not sort one fetched page in isolation.
- Default to active opportunities and exclude passed response deadlines when
  that option is selected. Rolling 7/14/30/60/90-day dates are resolved at
  execution time; the underlying active index covers all available posted dates.
- Return result-source and freshness metadata. When the index is unavailable,
  use the existing direct SAM search path and state that clearly, rather than
  serving partial local results silently.
- The locally indexed entity subset supports the core code, address, status,
  and date filters; an unsupported entity parameter uses the existing live
  Entity Management API rather than silently dropping that parameter.
- Entity searches move to the local entity index. Preserve all public manual
  filters, saved searches, and detail navigation. A direct UEI lookup may use
  SAM when the entity is missing or a current status check is requested.

## AI search builder

- Keep the existing per-user feature toggle and company-profile modes (`auto`,
  `include`, `exclude`). The server, not the model, decides whether to retrieve
  the shared company profile and includes only the fields needed for planning.
- Have the model produce a typed local-search plan: positive and negative
  capability terms, agency/sector inclusion and exclusion, notice types,
  set-asides, NAICS/PSC suggestions, date/deadline constraints, and optional
  sort. Validate codes and semantics server-side before showing editable
  criteria. Never let model output become SQL or an unrestricted SAM query.
- Represent `civilian` as an agency exclusion of DoD and military departments,
  not as a broad organization-name guess. Show this in the interpreted-plan
  explanation. Other ambiguous sector claims should be surfaced as assumptions.
- Do not discard generated set-asides, NAICS, or agencies to satisfy the old
  SAM-request cross-product cap. Show any genuinely unsupported or uncertain
  interpretation in the UI, and let the user review/edit before execution.
- AI builds searches; it does not process every search result. Company-profile
  relevance ranking/AI daily matching remains a separate, future feature.

## Batch and runtime architecture

- Keep CloudFront/S3, API Gateway/Lambda, Cognito, DynamoDB user state, SQS,
  EventBridge Scheduler, and SES. Add a private versioned raw/index S3 bucket,
  CloudFormation-managed schedules, queues/DLQs, and ingestion worker roles.
- Use short Lambda invocations for scheduling, SAM API delta pages, async export
  initiation/polling, and job state. Use on-demand batch compute for full-file
  parsing and SQLite index creation when the dataset exceeds Lambda's 15-minute
  limit. No always-on ECS service, Step Functions, RDS, or NAT gateway is
  required solely to coordinate downloads.
- Publish an index only after validation. Readers keep using the previous
  manifest until the new version is complete. Search Lambdas cache the current
  immutable index in `/tmp` and refresh when the manifest version changes.
  Both indexes are stored as gzip-compressed SQLite artifacts in S3 and
  decompressed on cold start to keep first-request transfer and storage costs
  bounded; the uncompressed SHA-256 is checked before use.
- Track each run's source timestamp, checksum, counts, duration, status,
  failures, retry count, index version, and last successful publish. Alert on
  failures and stale data. Retain raw files and previous indexes for a bounded
  rollback window.

The implementation records the immutable artifact checksum/count/date in the
S3 manifest and build status/log link in CodeBuild. A daily quiet-on-success
health check emails the configured operator if a build fails, an index goes
stale, or the ingest DLQ receives a message. S3 lifecycle expires old index
versions after 45 days; S3 bucket versioning and the prior manifest support
manual rollback. Automated rollback remains future work.

## Separate admin application

- Build `admin.<domain>` with Tabler for jobs, run history, errors, index
  freshness, source counts, manual reruns/backfills, schedule settings, user
  administration, and a read-only AWS Cost Explorer view with monitored
  service-level costs. Keep the public app on USWDS.
- Both hostnames use the same Cognito pool, app client, and custom auth domain.
  Add both callback/logout URLs and environment-aware cross-links. A hidden,
  same-site iframe on the other GovVue hostname can supply a fresh ID token
  by origin-checked `postMessage` when the current hostname has no session;
  no token is placed in a URL or shared cookie. Direct sign-in on either host
  remains possible. Require the existing `admin` group in the admin API, not
  just the UI.
- Parameterize domain names, bucket names, schedules, model IDs, and links per
  `dev`, `stg`, and `prod`. Provision via CloudFormation; keep local YAML -> SSM
  configuration and timestamped S3 build artifacts.

## Release sequence and acceptance

1. Create isolated ingestion/index resources and a backfill command. Run
   opportunity and entity builds without changing live search.
2. Validate counts and sample searches against SAM; test code OR/field AND,
   date windows, exclusions, full-result sorting, pagination, saved searches,
   details, and inactive status behavior.
3. Enable local opportunity and entity search behind environment/feature flags;
   preserve a visible fallback until data freshness is proven.
4. Migrate notification matching to the published local index. Confirm no
   duplicate mail and unchanged user definitions.
5. Update the AI search plan schema and UI; test civilian-vs-DoD, company
   profile inclusion, multi-NAICS/set-aside selections, and no 12-call
   truncation.
6. Deploy the Tabler admin app, shared sign-in, schedules, run controls,
   monitoring, and Cost Explorer view. Exercise dev/stg before production.
7. Measure real SAM generation time, batch duration, index size, Lambda cold
   starts, API quota usage, and AWS costs; adjust schedules and compute size
   from observed data.

Do not retire the direct SAM search and current feed until the local index
is populated and its replacements have passed the acceptance checks.
