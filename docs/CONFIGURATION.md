# Configuration

## Source of truth

Each environment uses a local YAML file:

```text
config/dev.govvue-light.yml
config/stg.govvue-light.yml
config/prod.govvue-light.yml
```

Real environment files are Git-ignored. `config/example.govvue-light.yml` is the safe template. The dev file imports only the enabled SAM.gov key from the retired GovVue configuration. All AWS deployment operations use the `workshop` profile.

```bash
python3 scripts/import-govvue-config.py \
  --source /Users/seanjoo/Documents/dev/govvue/GovVuePOC/config/dev.govvue.yml \
  --output config/dev.govvue-light.yml
```

The import uses mode `0600` and never prints the key.

Import a downloaded Google Web OAuth client without printing its secret:

```bash
python3 scripts/import-google-oauth-config.py \
  --credentials /path/to/client_secret.json \
  --config config/dev.govvue-light.yml \
  --domain-name auth.govvue.com
```

The Google client must authorize this JavaScript origin:
`https://auth.govvue.com` and
this redirect URI:
`https://auth.govvue.com/oauth2/idpresponse`.

## YAML to SSM mapping

The default prefix is `/govvue-light/dev/`.

| YAML property | SSM parameter | Type | Consumer |
|---|---|---|---|
| `sam_api_key` | `SamApiKey` | `SecureString` | Lambda runtime |
| `sam_opportunities_api` | `SamOpportunitiesApi` | `String` | Lambda runtime |
| `sam_entities_api` | `SamEntitiesApi` | `String` | Lambda runtime |
| `sam_site_base_url` | `SamSiteBaseUrl` | `String` | Lambda runtime |
| `app_domain_name` | `AppDomainName` | `String` | CloudFormation/CloudFront and Route 53 |
| `admin_domain_name` | `AdminDomainName` | `String` | Admin CloudFront, Route 53, Cognito callback, API CORS |
| `hosted_zone_id` | `HostedZoneId` | `String` | CloudFormation/Route 53 |
| `acm_certificate_arn` | `AcmCertificateArn` | `String` | CloudFormation/CloudFront |
| `admin_acm_certificate_arn` | `AdminAcmCertificateArn` | `String` | Admin CloudFront distribution |
| `cognito_domain_name` | `CognitoDomainName` | `String` | CloudFormation/Cognito custom domain |
| `cognito_certificate_arn` | `CognitoCertificateArn` | `String` | CloudFormation/Cognito custom-domain certificate |
| `google_oauth_client_id` | `GoogleOAuthClientId` | `String` | CloudFormation/Cognito Google provider |
| `google_oauth_client_secret` | `GoogleOAuthClientSecret` | `SecureString` | CloudFormation/Cognito Google provider |
| `frontend_title` | `FrontendTitle` | `String` | Frontend deployment runtime config |
| `cors_allowed_origin` | `CorsAllowedOrigin` | `String` | CloudFormation/API Gateway |
| `search_cache_ttl_seconds` | `SearchCacheTtlSeconds` | `String` | Lambda runtime |
| `search_default_lookback_days` | `SearchDefaultLookbackDays` | `String` | Lambda runtime |
| `search_max_lookback_days` | `SearchMaxLookbackDays` | `String` | Lambda runtime |
| `search_max_fanout` | `SearchMaxFanout` | `String` | Lambda runtime |
| `search_max_sort_pages` | `SearchMaxSortPages` | `String` | Lambda runtime |
| `sam_page_size` | `SamPageSize` | `String` | Lambda runtime |
| `sam_request_timeout_seconds` | `SamRequestTimeoutSeconds` | `String` | Lambda runtime |
| `api_throttle_rate` | `ApiThrottleRate` | `String` | CloudFormation/API Gateway |
| `api_throttle_burst` | `ApiThrottleBurst` | `String` | CloudFormation/API Gateway |
| `lambda_reserved_concurrency` | `LambdaReservedConcurrency` | `String` | CloudFormation/Lambda |
| `log_retention_days` | `LogRetentionDays` | `String` | CloudFormation/CloudWatch Logs |
| `history_retention_days` | `HistoryRetentionDays` | `String` | Lambda runtime |
| `daily_feed_page_size` | `DailyFeedPageSize` | `String` | Daily feed Lambda runtime |
| `daily_feed_retention_days` | `DailyFeedRetentionDays` | `String` | S3 and DynamoDB feed retention |
| `notification_run_retention_days` | `NotificationRunRetentionDays` | `String` | Notification Lambda runtime |
| `ai_search_model_id` | `AiSearchModelId` | `String` | API Lambda/Amazon Bedrock |
| `ai_search_max_tokens` | `AiSearchMaxTokens` | `String` | API Lambda/Amazon Bedrock |
| `daily_notification_default_time` | `DailyNotificationDefaultTime` | `String` | API and daily-feed Lambda runtime |
| `ops_alert_email` | `OpsAlertEmail` | `String` | Daily ingestion health alert recipient |
| `daily_feed_schedule_expression` | `DailyFeedScheduleExpression` | `String` | CloudFormation/EventBridge Scheduler |
| `opportunity_daily_schedule_expression` | `OpportunityDailyScheduleExpression` | `String` | Opportunity full snapshot schedule |
| `opportunity_poll_schedule_expression` | `OpportunityPollScheduleExpression` | `String` | Recent-posted API polling schedule |
| `entity_monthly_schedule_expression` | `EntityMonthlyScheduleExpression` | `String` | Monthly entity ZIP schedule |
| `entity_daily_schedule_expression` | `EntityDailyScheduleExpression` | `String` | Daily entity JSON export schedule |
| `ingest_schedule_state` | `IngestScheduleState` | `String` | All four ingestion schedules; initially `DISABLED` |
| `local_search_enabled` | `LocalSearchEnabled` | `String` | API and daily-feed cutover; initially `false` |
| `daily_feed_timezone` | `DailyFeedTimezone` | `String` | CloudFormation/EventBridge Scheduler |
| `notification_from_email` | `NotificationFromEmail` | `String` | CloudFormation/notification Lambda |
| `ses_identity_domain` | `SesIdentityDomain` | `String` | CloudFormation/Amazon SES |

`project_name`, `environment`, `aws_profile`, and `aws_region` are deployment identifiers needed before an SSM path or AWS connection can be resolved. `aws_profile` is validated as `workshop`; profiles from the retired GovVue project are not accepted.

The initial AI search model is `amazon.nova-lite-v1:0`. The API Lambda is
permitted to invoke Bedrock foundation models, but no model call occurs unless
the authenticated user has the `natural_language_search` feature flag and
submits the AI builder form. The model produces filter criteria only; the
published local index supplies results after cutover, with direct SAM.gov as
the fallback before cutover or when the index is unavailable.

## Synchronization

Preview without contacting AWS:

```bash
./scripts/sync-config.sh --env dev --dry-run
```

Write or overwrite the parameters:

```bash
./scripts/sync-config.sh --env dev
```

The command prints only the name and type of secure parameters.

## Google OAuth rotation

1. Download the replacement Google Web OAuth client JSON.
2. Run `scripts/import-google-oauth-config.py` with the environment config and its Cognito custom domain name.
3. Run `./scripts/deploy.sh --env dev --component infra`.

A CloudFormation custom resource reads the Google client secret directly from
SSM SecureString and applies it to Cognito. The secret is never stored in Git,
a plaintext stack parameter, frontend code, or deployment output.

## API-key rotation

1. Replace `sam_api_key` in the local YAML.
2. Preserve file permissions (`chmod 600 config/dev.govvue-light.yml`).
3. Run `./scripts/deploy.sh --env dev --component config`.
4. Wait up to five minutes for warm Lambda runtimes to refresh, or publish a backend release to force new runtimes.

Never place the key in `infrastructure/*.yaml`, frontend code, a Lambda environment variable, or a shell history entry.

## Multi-value search limit

`search_max_fanout` bounds the number of SAM.gov requests generated by one
on-demand multi-value search. The default is 12. Selecting multiple notice
types does not consume fan-out slots because SAM.gov accepts repeated `ptype`
parameters in one request. Selections for state, set-aside, NAICS, PSC, ZIP,
organization code, and organization name are multiplied together. Organization
names use `|` as their separator; the other multi-value fields use commas. For example, three states and
two NAICS codes require six SAM.gov searches. Cached upstream pages are reused
across display pages and equivalent searches.

These are **live SAM fallback controls only**. Once
`local_search_enabled: true`, local searches do not make a SAM request per
filter combination and do not truncate NAICS, set-aside, or agency selections
to satisfy a SAM request cap. The old parameters remain in YAML so the
fallback path can operate safely.

`search_max_sort_pages` bounds the total number of upstream SAM.gov pages that
GovVue will load to produce an exact order other than posted date, newest first.
The default is 24. If a result set exceeds the limit, GovVue asks the user to narrow the
filters instead of presenting a misleading page-local sort.

Entity searches do not use this fan-out allowance. The Entity Management API
accepts the supported multi-value filters natively, so each displayed entity
page requires at most one upstream call and equivalent pages share the same S3
cache TTL.

## NAICS catalog

The frontend packages the official 2022 U.S. Census Bureau NAICS structure as
a build-time JSON catalog. The picker presents sectors, subsectors, industry
groups, industries, and national industries hierarchically; only six-digit
national-industry codes are selectable because the SAM.gov Opportunities API
does not return parent-category matches for `ncode`.

To refresh the catalog from the official Census workbook after a NAICS
revision, run:

```bash
./scripts/update-naics-catalog.py
./scripts/validate.sh --env dev
./scripts/deploy.sh --env dev --component frontend
```

The generated JSON records the source URL and SHA-256 digest of the workbook.
Catalog generation uses only the Python standard library and does not add a
runtime network dependency to GovVue Light.

## Daily notification configuration

The EventBridge dispatcher defaults to `cron(0/5 * * * ? *)` in
`America/New_York`, so it checks for due notifications every five minutes.
Each notification stores its own run time in `HH:MM` format on a five-minute
increment. `daily_notification_default_time` supplies the initial and legacy
fallback value (`06:15` by default). Changing an individual notification's
time needs no infrastructure deployment; changing the dispatcher expression,
time zone, or default value uses the normal deployment flow. The dispatcher
does not contact SAM.gov when no notification is due.

Notifications due in the same dispatcher window share one feed download. Feed
pages contain up to 1,000 SAM.gov results, daily S3 snapshots expire after 30
days, and materialized per-notification runs expire after 90 days.

`notification_from_email` must be an address within `ses_identity_domain`.
CloudFormation creates the SES domain identity and its three Route 53 Easy DKIM
records. SES production-access approval remains an account-level operation;
while the account is in the SES sandbox, every recipient must be verified in
SES before daily mail can be delivered.
