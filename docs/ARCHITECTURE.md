# Architecture

## Request path

```text
Browser
  ├─ HTTPS ─> CloudFront ─> private S3 website bucket
  ├─ password sign-in ─> Amazon Cognito user pool
  ├─ Google sign-in ─> auth.govvue.com (Cognito managed login) ─> Google OAuth
  └─ JWT API request ─> API Gateway HTTP API ─> Lambda (not VPC-attached)
                                                   ├─ SAM.gov opportunity and entity HTTPS APIs
                                                   ├─ SSM Parameter Store
                                                   ├─ private S3 search cache
                                                   └─ DynamoDB user state
```

Lambda runs in the AWS-managed Lambda network. It is deliberately not attached to the existing VPC. Public SAM.gov calls therefore need neither a NAT gateway nor the VPC's internet gateway. The VPC and subnets are not part of GovVue Light v1.

## Daily notification path

```text
EventBridge Scheduler (five-minute dispatcher, America/New_York)
  └─ SQS FIFO fetch queue
       └─ Daily Feed Lambda
            ├─ selects notifications due at their configured daily time
            ├─ exits without a SAM.gov call when none are due
            ├─ downloads one SAM page per invocation when work is due
            ├─ SAM.gov offset 0, 1, 2, ... with limit 1,000
            ├─ private S3 daily-feed page snapshots
            ├─ DynamoDB feed-run manifest
            └─ SQS notification message per enabled filter
                 └─ Notification Lambda
                      ├─ local filtering of the shared feed
                      ├─ DynamoDB daily run and paginated results
                      └─ Amazon SES email
```

SQS, not a continuously running Lambda or Step Functions workflow, coordinates
the download. The dispatcher groups notifications due in the same window into
one feed run. A successful page invocation queues the next zero-based SAM page
index. The last page fans out only those due notifications. Deterministic S3 keys,
DynamoDB run state, SQS retries, and dead-letter queues make the process
restartable and prevent partial feeds from being presented as complete.

## AWS resources

The bootstrap stack creates the versioned artifact bucket. The application stack creates:

- a Cognito user pool, `auth.govvue.com` custom managed-login domain, Google identity provider, public web client, and pre-sign-up account-link Lambda;
- Cognito `admin` and `user` groups, with backend authorization based on the signed `cognito:groups` token claim;
- an API Gateway HTTP API with Cognito JWT authorization;
- API, daily-feed, and notification Lambda functions with immutable versions and `live` aliases;
- an on-demand DynamoDB table with point-in-time recovery and TTL;
- a private, one-day-lifecycle S3 search cache;
- a private S3 daily-feed bucket with 30-day lifecycle retention;
- FIFO page-fetch and standard notification SQS queues with dead-letter queues;
- a time-zone-aware EventBridge Scheduler dispatcher;
- an SES domain identity with Route 53 Easy DKIM records;
- a private, versioned frontend bucket;
- CloudFront with origin access control, the `app.govvue.com` ACM certificate, and security headers;
- Route 53 A and AAAA aliases from `app.govvue.com` to the application CloudFront distribution and from `auth.govvue.com` to the AWS-managed Cognito distribution; and
- CloudWatch API and Lambda log groups.

Stateful resources use `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`.

## Search and caching

The SAM.gov Opportunities API allows a maximum request size of 1,000. GovVue Light intentionally separates upstream pagination from display pagination:

1. The browser requests a 25-record display page.
2. Lambda normalizes allowlisted filters. Repeated notice types remain one
   native SAM.gov request; other multi-value code filters expand into a bounded
   set of single-value requests.
3. A SHA-256 hash of each SAM parameter set and zero-based SAM page index
   addresses a private S3 cache object.
4. Missing branches run concurrently, while valid cache entries avoid another
   SAM.gov call.
5. Lambda merges branch results, removes duplicate Notice IDs, sorts by the
   selected date and direction, and slices the requested 25-record display page.
6. A second converged-page cache avoids repeating the merge, and navigating
   among display pages within already-loaded 1,000-record upstream batches
   reuses those cached SAM responses.

The default cache TTL is 15 minutes. S3 lifecycle removal after one day provides cleanup if a cache object is never read again.

Entity searches use the SAM.gov Entity Management API v4 directly. The API
provides fixed 10-record pages and permits only the first 10,000 synchronous
results. GovVue maps each browser page to one zero-based SAM page, uses SAM's
native OR syntax for multi-value filters, and caches normalized pages under a
separate entity-search namespace. It requests `entityRegistration`,
`coreData`, and `assertions`, retains only the public-facing display fields,
and never stores the raw upstream response in user records.

## User data model

One DynamoDB table stores user-owned records. Cognito's immutable `sub` claim is the partition namespace.

| PK | SK prefix | Purpose |
|---|---|---|
| `USER#<sub>` | `SAVED_OPP#` | Compact saved opportunity snapshot |
| `USER#<sub>` | `SAVED_SEARCH#` | Named reusable search criteria |
| `USER#<sub>` | `SAVED_ENTITY#` | Compact saved entity snapshot keyed by UEI |
| `USER#<sub>` | `SAVED_ENTITY_SEARCH#` | Named reusable entity-search criteria |
| `USER#<sub>` | `HISTORY#` | Search history with a DynamoDB expiration timestamp |
| `USER#<sub>` | `DAILY_NOTIFICATION#` | Editable notification definition and recipient |
| `USER#<sub>` | `NOTIFICATION_RUN#` | Daily run summary, criteria snapshot, and email status |
| `NOTIFICATION_RESULTS#...` | `RESULT#` | Cursor-paginated opportunity snapshots for one daily run |
| `DAILY_FEED#<date>` | `META` / `PAGE#` | Feed status and completed-page manifest |

The `GSI1` index contains only enabled daily-notification definitions so the
feed finalizer can fan out work without scanning the table. Browser requests
remain scoped to the authenticated user's partition key.

## Security boundaries

- The SAM.gov key exists in a Git-ignored, mode-`0600` local YAML file and in SSM as a `SecureString`.
- The key is not in CloudFormation, a stack parameter, Lambda environment variables, build output, or frontend code.
- Lambda reads the secure parameter at runtime and caches it in memory for five minutes.
- API Gateway validates Cognito JWT issuer and audience before Lambda is invoked.
- Google sign-in is limited to verified Google email addresses that match an existing invited Cognito user. The pre-sign-up trigger links the provider to that user so the original Cognito `sub`, role groups, and DynamoDB data remain unchanged.
- Lambda independently requires the `admin` group for every `/admin/*` operation; hiding the Admin menu is not the authorization boundary.
- Website and cache buckets block all public access.
- CloudFront alone can read the website bucket through signed origin access control.
- Search descriptions are converted to plain text; frontend code never renders SAM.gov HTML.
- Daily emails show type, response deadline, a short plain-text description, and a GovVue Light detail link for the first 10 matches. Description text is fetched on demand instead of for every record in the shared daily feed.
- Description URLs are accepted only when they use HTTPS and a `sam.gov` hostname.
- Entity responses are normalized to public registration, address, business-type, NAICS, PSC, and disaster-response fields; sensitive banking, tax, and point-of-contact data is neither returned to the browser nor stored.
- API Gateway throttling and Lambda reserved concurrency bound accidental request bursts.

The USWDS official-site banner and federal agency identifier are intentionally omitted because GovVue Light is a personal tool, not an official government service.
