# Operations

## Observability

Default log groups:

```text
/aws/lambda/govvue-light-dev-api
/aws/lambda/govvue-light-dev-daily-feed
/aws/lambda/govvue-light-dev-notification
/aws/apigateway/govvue-light-dev
/aws/lambda/govvue-light-dev-entity-export
/aws/lambda/govvue-light-dev-ingest-health
/aws/codebuild/govvue-light-dev-ingest
```

The Lambda does not log the SAM.gov URL containing the API key. API Gateway access logs contain route, status, response size, and latency but no authorization token.

Useful commands:

```bash
aws logs tail /aws/lambda/govvue-light-dev-api --follow --profile workshop --region us-east-1
aws logs tail /aws/lambda/govvue-light-dev-daily-feed --follow --profile workshop --region us-east-1
aws logs tail /aws/lambda/govvue-light-dev-notification --follow --profile workshop --region us-east-1
aws cloudformation describe-stacks --stack-name govvue-light-dev --profile workshop --region us-east-1
```

## Health check

`GET /health` is the only unauthenticated API route. Retrieve `ApiEndpoint` from the application stack, then request `<ApiEndpoint>/health`.

## Local index operations

`https://admin.govvue.com` shows index counts/source dates, the last ten
CodeBuild runs and logs, schedule state, SQS/DLQ depth, and manual job buttons.
It also has a read-only Cost Explorer page. Costs are for the whole workshop
account, not just GovVue Light, and current-month figures may lag.
The admin navigation has separate **Users** and **Companies** directories.
Both tables support search, filters, sorting, and client-side pagination over
the complete Cognito user list. Select a user to change their platform role,
enabled status, company assignment, company role, or feature flags; resend an
invitation, send a password reset, or delete the account. Select a company to
see its members, open a member's user details, or edit the shared company
profile. New invitations and company workspaces are started from their
respective directory pages.
Administrators can run the read-only `POST /admin/ingestion/validate` API with
`{"kind":"opportunities"}` or `{"kind":"entities"}` to measure a full cold
local-search path before setting `local_search_enabled: true`.

The local index and ingest schedules are controlled by the Git-ignored
environment YAML (`local_search_enabled` and `ingest_schedule_state`), copied
to SSM and then resolved into CloudFormation. The four ingest schedules and
health check default to
disabled until both baselines are built and sampled. The full opportunity CSV
is authoritative for active/inactive state each day. Recent-posted API polls
cannot detect every modification to an older notice. The public monthly entity
ZIP is authoritative for active registrations at replacement time; daily
active-only JSON updates cannot immediately remove early deactivations, so
entity freshness can lag until the next replacement. The opportunity manifest
tracks the last full-snapshot date separately from the intraday poll date so
the health alert can detect a missed full download. Expiration dates are
enforced locally. The first daily entity export after a monthly replacement
requests updates from that replacement date through the current day, rather
than only the previous day. The public extract's blank exclusion flag maps to
the app's **No active exclusion** value.

At 9:30 AM Eastern, a health check emails `ops_alert_email` only when an index
is stale or missing, a recent batch build failed, or the ingestion DLQ is not
empty. It is disabled together with the ingest schedules until cutover. The
alert links to the admin Operations page; healthy days do not generate mail.

Raw files, indexes, and the current manifest are in the private versioned
`LocalIndexBucket`. The manifest changes only after checksum, count, and SQLite
integrity checks. A failed build must leave the previous manifest in place.
The SQLite artifacts are gzip-compressed in S3; API Lambdas verify each
uncompressed SHA-256 while expanding it into `/tmp` on a cold start.
Immutable index versions expire after 45 days, and superseded S3 object
versions expire after 45 days, to bound S3 cost; a prolonged
ingestion outage can therefore make local search fall back to SAM until an
administrator rebuilds the index.
Check the build log and the ingest DLQ before manually retrying. Do not turn
on local search if a baseline manifest is absent or fails sample queries.

For the first backfill, cutover, and rollback commands, see
[Deployment](DEPLOYMENT.md#local-data-migration-and-first-backfill).

## Throttling and SAM.gov protection

Three controls reduce calls and bursts:

- the browser displays 25 records while Lambda fetches/caches as many as 1,000 per SAM.gov call;
- API Gateway defaults to two requests per second and a burst of five; and
- Lambda reserved concurrency defaults to two.

SAM.gov HTTP 429 and temporary server errors are retried twice with a short bounded backoff. A final 429 is returned to the browser with a human-readable message.

The daily fetch uses a FIFO queue, batch size one, and fetch-Lambda reserved
concurrency one. Each invocation downloads one SAM page and queues the next
page. Failed messages are retried five times before entering the daily-feed
DLQ. Notification messages use a separate queue and DLQ so an SES problem does
not repeat SAM.gov downloads.

## Manual daily-feed run

Each notification has its own daily time in `America/New_York`; the default is
6:15 AM. The EventBridge dispatcher checks every five minutes and makes no
SAM.gov request when nothing is due. Edit a notification in the application to
change its time. Authenticated users with at least one enabled notification can
use **Run now** on the Daily Notifications page. It refreshes the shared feed
and processes all enabled notifications. An email already sent for the same
notification and date is not sent again.

To queue the scheduled behavior from the AWS CLI instead:

```bash
FEED_QUEUE_URL="$(aws cloudformation describe-stacks \
  --stack-name govvue-light-dev \
  --profile workshop \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`DailyFeedQueueUrl`].OutputValue' \
  --output text)"
aws sqs send-message \
  --queue-url "$FEED_QUEUE_URL" \
  --message-body '{"action":"tick"}' \
  --message-group-id daily-feed \
  --profile workshop \
  --region us-east-1
```

The CLI tick is a no-op when no notification is currently due. The application
Run now action explicitly refreshes the feed and runs all enabled
notifications. Inspect the feed Lambda logs, queue depths, DLQs, and the
`DAILY_FEED#<date>` DynamoDB records if a run does not complete.

Each email includes up to 10 matching opportunities with the notice type,
response deadline, a short description, and a direct GovVue Light detail link.
The displayed Notice ID is the SAM.gov solicitation number (`Sol#` in the
public CSV); the separate Record ID remains the stable GovVue Light detail
URL key. When the public CSV contains multiple active posting versions for the
same office, notice type, and sufficiently similar title, the local index and
daily feed expose only the newest posting timestamp. Older record IDs remain
available for saved-detail links. The intraday API overlay uses the API's
latest-active record to reconcile same-day versions. Distinct titles or offices
are not collapsed solely because they share a solicitation number.
The published manifest reports both `raw_record_count` and `record_count`;
the source-size safety check uses the raw count so expected version reduction
does not look like a truncated download.
The notification run page remains the complete, paginated result for that day.
Runs with no matches are recorded with an email status of `SKIPPED`; no email
is submitted to SES for those runs.

## SES delivery

Daily notification mail is sent from `notifications@govvue.com`. Cognito
account invitations and password-recovery messages are sent as
`GovVue Light <notifications@govvue.com>` through the same verified SES domain.
The stack provisions the `govvue.com` SES identity and DKIM DNS records.

The workshop SES account must be out of the sandbox to send to arbitrary user
addresses. Until production access is approved, `scripts/create-user.sh`
registers each new user's address as an SES email identity. The user must follow
the separate SES verification link before daily notifications can be delivered.
A failed or expired verification is recreated automatically so SES sends a new
verification message. The notification Lambda can address verified sandbox
recipients but restricts the From address to the configured
`notification_from_email` value.
A failed delivery remains `FAILED` in the daily run and is retried through the
notification queue before reaching its DLQ.

## User roles and password operations

Every newly created account is assigned to the Cognito `user` group unless
`--role admin` is passed to `scripts/create-user.sh` or an administrator chooses
Administrator in the application. Existing sessions can retain an older group
claim for up to the token lifetime; sign out and back in to apply a role change
immediately.

The Admin page can invite, enable, disable, change the role of, reset, and
delete other users. Administrators cannot modify, reset, or delete their own
account from that page. Account deletion disables the Cognito user first,
removes its active GovVue records (including daily notification definitions),
and then deletes the Cognito account. Expiring notification-result snapshots
remain protected in DynamoDB until their TTL removes them.

All users can change their own password from Account. Password-reset email uses
Cognito's verified-email recovery channel; application administrators never
receive or set another user's password.

## Data retention

- Search cache: runtime TTL defaults to 15 minutes; S3 removes objects after one day.
- Search history: DynamoDB TTL defaults to 90 days.
- Daily feed S3 pages and feed manifests: 30 days by default.
- Daily notification runs and result snapshots: 90 days by default.
- Saved searches, opportunities, entity searches, and entities: retained until the user deletes them.
- Website bucket, search cache bucket, DynamoDB table, Cognito pool, and log groups: retained if a stack is deleted.
- Release objects: current versions expire after one year; noncurrent S3 versions expire after 90 days.

## Failed deployment

CloudFormation retains the previous Lambda alias target when an update rolls back. Timestamped and S3-versioned packages remain available in the artifact bucket for investigation.

For a failed frontend publication, rerun the previous source revision with a new build ID or unzip a retained frontend release package and synchronize it to the website bucket. CloudFront must be invalidated afterward.

## Cost posture

There are no continuously running containers, RDS instances, NAT gateways, or provisioned DynamoDB capacity. Charges are request/storage based: CloudFront, S3, SQS, EventBridge Scheduler, SES, API Gateway, Lambda, DynamoDB, CloudWatch Logs, SSM API calls, and Cognito monthly active users. At two or three occasional users, usage should remain very small, subject to normal AWS account pricing.

## Backup and deletion

DynamoDB point-in-time recovery is enabled. S3 versioning is enabled for website and artifact content. Retained resources are intentionally not removed by stack deletion; remove them manually only after confirming that their contents and recovery history are no longer needed.
