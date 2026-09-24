# Operations

## Observability

Default log groups:

```text
/aws/lambda/govvue-light-dev-api
/aws/lambda/govvue-light-dev-daily-feed
/aws/lambda/govvue-light-dev-notification
/aws/apigateway/govvue-light-dev
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
