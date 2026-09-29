# Deployment

This is the runbook for the initial `dev` deployment and every later release.
All AWS commands issued by the project use the `workshop` profile. The
configuration validator rejects a different profile.

## Prerequisites

- macOS or Linux with Bash
- Python 3.11 or newer
- Node.js 22 and npm
- AWS CLI v2
- `zip`, `jq`, and `shasum`
- a working AWS CLI profile named `workshop` with CloudFormation, IAM, Lambda, API Gateway, Cognito, DynamoDB, S3, CloudFront, Route 53, CloudWatch Logs, SSM, CodeBuild, EventBridge Scheduler, SQS, Cost Explorer, and KMS permissions
- Amazon Bedrock model access for the configured AI search model (the default is Amazon Nova Lite)

The development region comes from `config/dev.govvue-light.yml` and is
`us-east-1` by default.

These account-level prerequisites already exist and are deliberately not
created by the application stacks:

- the `workshop` AWS account and CLI profile;
- the public `govvue.com` Route 53 hosted zone and registrar delegation;
- issued ACM certificates for `app.govvue.com`, `admin.govvue.com`, and `auth.govvue.com` in `us-east-1`;
- a Google Cloud Web OAuth client configured for the Cognito callback; and
- the local `config/dev.govvue-light.yml`, including the SAM.gov API key and Google OAuth client values.

CloudFormation attaches the existing certificates and creates the
`app.govvue.com`, `admin.govvue.com`, and `auth.govvue.com` A and AAAA aliases. The certificates
themselves and the hosted zone remain external prerequisites.

CloudFormation also creates the SES `govvue.com` identity and its Route 53 DKIM
records. SES production-access approval is not a CloudFormation resource. The
workshop account can initially send only to SES-verified recipients while it
remains in the sandbox.

## Initial deployment checklist

### 1. Change to the project directory

```bash
cd /Users/seanjoo/Documents/dev/govvue_light
```

### 2. Confirm the AWS identity

```bash
aws sts get-caller-identity --profile workshop
```

Stop if this does not identify the intended workshop account. Do not substitute
a profile from the retired GovVue project.

Also confirm that the local configuration contains these deployment values:

```yaml
aws_profile: workshop
aws_region: us-east-1
app_domain_name: app.govvue.com
admin_domain_name: admin.govvue.com
hosted_zone_id: Z04260832ZB8NBYSOXBA7
acm_certificate_arn: arn:aws:acm:us-east-1:428613119099:certificate/f810f621-f8fb-449e-9f51-a793dcc69904
admin_acm_certificate_arn: arn:aws:acm:us-east-1:428613119099:certificate/34a81925-3834-4e8b-8f75-1e1e83a8bbce
cognito_domain_name: auth.govvue.com
cognito_certificate_arn: arn:aws:acm:us-east-1:428613119099:certificate/c95d7e53-6862-415a-8167-0b75af11e2ec
cors_allowed_origin: https://app.govvue.com
```

In the Google OAuth client, use exactly:

```text
Authorized JavaScript origin:
https://auth.govvue.com

Authorized redirect URI:
https://auth.govvue.com/oauth2/idpresponse
```

The application publishes these unauthenticated pages for Google OAuth branding:

```text
Application home page:          https://app.govvue.com/
Application privacy policy:     https://app.govvue.com/privacy
Application terms of service:   https://app.govvue.com/terms
Authorized domain:              govvue.com
```

Verify `govvue.com` as a DNS Domain property in Google Search Console before
requesting brand verification. Add Google's verification TXT value alongside
the existing apex TXT values; do not replace the Purelymail or SPF values.

Import the downloaded client JSON into the local configuration:

```bash
python3 scripts/import-google-oauth-config.py \
  --credentials /path/to/client_secret.json \
  --config config/dev.govvue-light.yml \
  --domain-name auth.govvue.com
```

Do not print or paste `sam_api_key` or `google_oauth_client_secret`. Keep the configuration file at mode
`0600`; it is ignored by Git.

### 3. Validate locally

```bash
./scripts/validate.sh --env dev
```

This validates the YAML, parses every shell script, runs backend tests, lints
both CloudFormation templates, audits frontend dependencies, and makes a
production frontend build. It does not create or update AWS resources.

### 4. Preview the SSM synchronization

```bash
./scripts/sync-config.sh --env dev --dry-run
```

Review the parameter names and non-secret values. The SAM.gov key is displayed
only as `<redacted>`.

### 5. Run the end-to-end deployment

```bash
./scripts/deploy.sh --env dev
```

This is the supported initial deployment command. Do not start with
`--component infra` or `--component frontend`, because those modes expect the
application stack to exist already.

The end-to-end command performs these operations in order:

1. validates the local environment YAML;
2. writes ordinary values to SSM `String` parameters and the SAM.gov and Google OAuth secrets to `SecureString` parameters;
3. deploys the bootstrap CloudFormation stack containing the versioned artifact bucket;
4. runs backend tests and builds a timestamped Lambda ZIP;
5. uploads Lambda and CloudFormation artifacts under `releases/<build-id>/`;
6. deploys the application CloudFormation stack using the S3 object key and version ID;
7. runs `npm ci`, audits dependencies, and produces the Vite frontend build;
8. writes deployment-specific Cognito/API values to `runtime-config.js`;
9. uploads a timestamped frontend ZIP to the artifact bucket;
10. publishes the built frontend to the private website bucket; and
11. invalidates CloudFront.

The application stack also enables the daily notification EventBridge schedule, SQS page and
notification queues, daily-feed and notification Lambdas, SES domain identity,
DKIM records, and daily-feed storage.
The local data ingestion schedules are initially **DISABLED**. The build and
download resources are provisioned, but do not spend SAM.gov quota or replace
the live search automatically before the backfill is verified.

The final command prints the custom website URL. CloudFront creation can take
several minutes. The two expected stacks are `govvue-light-dev-bootstrap` and
`govvue-light-dev`.

### 6. Create the first user

```bash
./scripts/create-user.sh --env dev --email administrator@example.com --role admin
./scripts/create-user.sh --env dev --email user@example.com
```

The script first ensures that the supplied address exists as an Amazon SES email
identity. In the SES sandbox, a new user receives an SES verification message
and must follow its link before GovVue Light can send daily notifications to
that address. Existing verified or pending identities are detected so the step
is safe to repeat.

If `--role` is omitted, the user is assigned to the `user` group. Valid values
are `user` and `admin`. Group membership can also be updated in the Cognito
console. Users with the `admin` role see the Admin menu and can manage users
from the application; backend routes verify the signed group claim.

The script does not prompt for or handle a password. Cognito separately
generates a random temporary password and sends a branded GovVue Light
invitation from `GovVue Light <notifications@govvue.com>`. The invitation
identifies the application, links to the sign-in page, and explains the
first-login password change. The temporary password expires after seven days.
The user can sign in at `https://app.govvue.com` with the temporary password
and replace it, or choose Google using the same invited email address. Google
identities are linked to the invited Cognito user, preserving the user's role
and saved data. Uninvited Google accounts are rejected. Password users continue
to see the Google option on the sign-in screen. Self-registration is disabled.

All signed-in users can select their email address in the header to open the
Account page and change their own password. The sign-in page also supports the
Cognito email-code password recovery flow. Administrators can send a password
reset from the Admin page; users who have not completed first sign-in receive a
new generated temporary password and invitation instead. The invitation explains
both the password setup and the matching-email Google option.

An invited user who is not assigned to a company can open **Company profile**,
enter a company name and profile, and create the shared workspace. The creator
becomes its first company manager. This self-service operation preserves the
invitation-only access model and cannot replace an existing company assignment.
A company can contain any number of users and has one shared profile. A company
manager can edit that profile, invite regular users from the Company profile
page, promote other company managers, and remove a member's company assignment.
Regular company members can view the shared profile but cannot edit it, see the
member list, or invite and manage users. A platform administrator who is a
company member can edit the profile, but uses the separate Admin area to manage
company users and access.
Removing a company member does not delete the Cognito account or personal
GovVue data. Per-user feature flags remain platform-admin controls.

The application distinguishes two administrative scopes:

1. A **GovVue administrator** belongs to Cognito's `admin` group and can manage
   every user, company assignment, and feature flag.
2. A **company manager** is a regular GovVue user with manager access to one
   company. Company managers maintain that shared profile and membership but
   cannot grant the GovVue administrator role.

To create a company in the UI:

1. If necessary, use **Admin → Add user** to invite the intended manager.
2. Under **Create company workspace**, enter the company name and select an
   unassigned user as the initial company manager.
3. Select **Create company and profile**. GovVue creates the workspace, an
   empty shared profile, and the manager assignment together.
4. The manager signs in and opens **Company profile** to complete capabilities,
   NAICS, agencies, keywords, and other profile fields.
5. From the same page, the manager can invite members or designate additional
   company managers. A GovVue administrator can later change any company role
   from the user cards in Admin.

The administrator-created workflow remains available alongside self-service
creation. Every company card in Admin includes **Manage profile**, which lets a
GovVue administrator view and edit that company's shared profile without
changing the administrator's own company assignment.

For an idempotent scripted company setup after the users already exist, use:

```bash
.venv/bin/python scripts/configure-company.py \
  --config config/dev.govvue-light.yml \
  --name "LatticeWorks, Inc." \
  --profile-json docs/LATTICEWORKS_PROFILE.json \
  --manager sean.joo@latticeworksinc.com \
  --member sean.joo@gmail.com \
  --feature-user sean.joo@gmail.com
```

This reuses the company when its name already exists, replaces the shared
profile with the reviewed JSON, assigns the company roles, and enables the AI
search builder only for the listed feature user. It does not create Cognito
users; use the invitation UI or `create-user.sh` first.

The Cognito invitation and SES recipient verification are separate messages.
The user pool uses the verified `govvue.com` SES identity with
`EmailSendingAccount` set to `DEVELOPER` for branded invitations, password
recovery, and verification messages. These account messages use the workshop
SES quota and sending-access status.

The application stack configures `app.govvue.com` as the application CloudFront alternate domain and `auth.govvue.com` as the Cognito custom domain, attaches their workshop ACM certificates, and creates Route 53 A and AAAA alias records in the workshop hosted zone.

### 7. Verify the deployment

Check the stacks and retrieve their outputs:

```bash
aws cloudformation describe-stacks \
  --stack-name govvue-light-dev-bootstrap \
  --profile workshop \
  --region us-east-1 \
  --query 'Stacks[0].StackStatus' \
  --output text

aws cloudformation describe-stacks \
  --stack-name govvue-light-dev \
  --profile workshop \
  --region us-east-1 \
  --query 'Stacks[0].{Status:StackStatus,Outputs:Outputs}'
```

Both statuses should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`. Then verify:

```bash
curl --fail --silent --show-error https://app.govvue.com/ >/dev/null

API_URL="$(aws cloudformation describe-stacks \
  --stack-name govvue-light-dev \
  --profile workshop \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)"
curl --fail --silent --show-error "$API_URL/health"
```

Finally, sign in at `https://app.govvue.com`, change the temporary Cognito
password, and perform one SAM.gov search.

## Local-data migration and first backfill

The original live search remains active after deployment because
`local_search_enabled: false` and `ingest_schedule_state: DISABLED` are the
initial YAML values. The admin console is at `https://admin.govvue.com` and
uses the same Cognito pool. Admins can open it directly or follow the **Admin**
link in the app. Because the two sites have different browser origins, each
can authenticate directly. When one is already signed in, the other can reuse
that session through a same-site, origin-checked sign-in bridge. This does not
put tokens in URLs or domain-wide cookies. If the browser blocks the bridge,
sign in directly on the second hostname. The API enforces the `admin` group on
every admin operation.

Run the two baselines from **Admin → Operations** in this order:

1. **Opportunity full snapshot**. The batch worker downloads the public active
   CSV, keeps the raw file, builds and validates SQLite/FTS, uploads an immutable
   version, and switches `indexes/opportunities/current.json` last.
2. **Entity monthly baseline**. This downloads the latest first-Sunday public
   UTF-8 ZIP, indexes active records, replays any newer daily JSON files, then
   switches `indexes/entities/current.json` last. It can take over an hour.

The equivalent workshop CLI command is:

```bash
INGEST_QUEUE_URL="$(aws cloudformation describe-stacks \
  --stack-name govvue-light-dev --profile workshop --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`IngestQueueUrl`].OutputValue' \
  --output text)"
aws sqs send-message --queue-url "$INGEST_QUEUE_URL" \
  --message-body '{"action":"build","dataset":"opportunity-daily"}' \
  --profile workshop --region us-east-1
aws sqs send-message --queue-url "$INGEST_QUEUE_URL" \
  --message-body '{"action":"build","dataset":"entity-monthly"}' \
  --profile workshop --region us-east-1
```

Inspect build status, count, date, and CloudWatch log links in Admin. Compare
representative searches—especially multi-NAICS OR, field-level AND, civilian
agency exclusion, active status, response deadlines, and the saved WON entity
queries—against live SAM. A raw source or missing manifest is a failed
backfill, not a reason to enable the new path. Leave the old live path in place
while discrepancies are investigated. Use **Test local search** on each Admin
index card before cutover; it exercises the published index even while the
public search flag is off and reports the first-request duration. Keep the
cold request below the API Gateway timeout before switching users over.

After the baselines are sound, set these values in the environment YAML:

```yaml
local_search_enabled: true
ingest_schedule_state: ENABLED
```

Then run `./scripts/deploy.sh --env dev --component config` followed by
`./scripts/deploy.sh --env dev --component infra`. Because CloudFormation
resolves the SSM values into Lambda environment variables, the stack update is
required to turn on local search. The schedule expressions are also driven by
YAML/SSM; changing one requires the same config + infrastructure update. The
defaults are opportunity full snapshot at 06:00, recent-posted API polls at
08:00/11:00/14:00/17:00, entity JSON update at 04:00, and monthly public
entity replacement at 09:00 on days 1–10 (the worker runs only once the
first-Sunday file is available), all `America/New_York`.

The daily notification schedule remains per user. When local search is enabled,
its shared feed reads a pinned, published local index instead of making one SAM
request per feed page. The index selects the latest posting version for
matching office, notice type, solicitation number, and similar title, while
preserving older records for existing saved links. Rebuild the full opportunity
snapshot after deploying a change to version-selection logic; deploying Lambda
code alone does not rewrite the already-published index. Scheduled notifications wait for the day's full opportunity
snapshot and catch up after it publishes if their configured time has passed.
A manually requested run can fall back to the existing SAM feed when the index
is missing; the source choice is pinned in run metadata so pages do not mix.

To roll search back without deleting data, set `local_search_enabled: false`,
sync config, and redeploy infrastructure. Leave ingestion disabled or enabled
separately. S3 versioning preserves earlier manifests and index objects; do not
delete them during a rollback.

## Subsequent updates

All commands create a new UTC timestamp build ID unless `--build-id YYYYMMDDTHHMMSSZ` is supplied.

Run local validation before a release that changes source code, dependencies,
or CloudFormation:

```bash
./scripts/validate.sh --env dev
```

Choose the narrowest command that includes every changed component:

| Change | Command |
|---|---|
| Multiple components or uncertain scope | `./scripts/deploy.sh --env dev` |
| Lambda/backend source or dependencies | `./scripts/deploy.sh --env dev --component backend` |
| CloudFormation only | `./scripts/deploy.sh --env dev --component infra` |
| Frontend only | `./scripts/deploy.sh --env dev --component frontend` |
| Runtime YAML/SSM only | `./scripts/deploy.sh --env dev --component config` |

The backend mode also applies pending CloudFormation edits. The infrastructure
mode reuses the Lambda package already recorded in the application stack.

### Complete release

Use when backend, infrastructure, and frontend should stay on one release identifier:

```bash
./scripts/deploy.sh --env dev
```

### Lambda/backend update

Runs tests, creates and uploads a new Lambda ZIP, publishes a new Lambda version, moves the `live` alias, and applies any pending CloudFormation edits:

```bash
./scripts/deploy.sh --env dev --component backend
```

### Infrastructure-only update

Reuses the Lambda artifact currently recorded in the stack and applies the CloudFormation templates:

```bash
./scripts/deploy.sh --env dev --component infra
```

This is also the correct command after changing a YAML value consumed directly by CloudFormation, such as API throttling, log retention, reserved concurrency, or CORS.

Changes to `app_domain_name`, `hosted_zone_id`, `acm_certificate_arn`,
`cognito_domain_name`, or `cognito_certificate_arn` also
require an infrastructure update after the new external DNS/certificate
prerequisites are ready.

### Frontend-only update

Builds, versions, publishes, and invalidates only the frontend:

```bash
./scripts/deploy.sh --env dev --component frontend
```

### Configuration-only update

```bash
./scripts/deploy.sh --env dev --component config
```

Lambda refreshes runtime configuration from SSM within five minutes. Configuration read directly by CloudFormation still requires an infrastructure update.

## Retry and recovery

All deployment commands are safe to rerun after correcting a failure. Omit
`--build-id` to generate a fresh release identifier; this is the normal retry
path.

- If local validation fails, fix it before contacting AWS.
- If SSM synchronization fails, correct the workshop credentials or permission
  and rerun the same component command.
- If the application stack fails, inspect its CloudFormation events. A failed
  update rolls back to the preceding stack state.
- If frontend publication fails after the stack succeeds, rerun
  `./scripts/deploy.sh --env dev --component frontend`.
- If user creation fails, the infrastructure deployment remains valid; correct
  the user input or permissions and rerun `scripts/create-user.sh`.

Do not delete either stack as a retry technique. Several data-bearing resources
have `Retain` policies, so stack deletion is not a clean rollback and can leave
resources that conflict with a replacement deployment.

After any retry, repeat the stack, website, health endpoint, and sign-in checks
from the verification section.

## Provisioning boundary

CloudFormation provisions the artifact, website, and cache buckets; DynamoDB;
Cognito pool and client; Lambda, IAM role, and log groups; API Gateway;
CloudFront; and the `app.govvue.com` A/AAAA records.

The deployment scripts manage SSM synchronization, timestamped artifact
uploads, website publication, CloudFront invalidation, and Cognito user
creation. The ACM certificate, hosted zone, registrar delegation, workshop
profile, and local secret-bearing YAML remain outside CloudFormation.

## Individual scripts

| Script | Purpose |
|---|---|
| `scripts/validate.sh` | Local config, shell, Python, CloudFormation, npm audit, and production-build checks |
| `scripts/sync-config.sh` | YAML-to-SSM synchronization |
| `scripts/build-lambda.sh` | Tests and timestamped Lambda ZIP |
| `scripts/deploy-infrastructure.sh` | Bootstrap, artifact upload, and application stack deployment |
| `scripts/build-frontend.sh` | Locked dependency install and timestamped frontend ZIP |
| `scripts/deploy-frontend.sh` | Frontend artifact upload, website publication, and invalidation |
| `scripts/create-user.sh` | Create a Cognito `user` or `admin` and email a generated temporary password |
| `scripts/update-naics-catalog.py` | Regenerate the bundled hierarchical NAICS picker data from the official Census workbook |
| `scripts/deploy.sh` | End-to-end/component orchestrator |

## CloudFormation stack names

With the default configuration:

- bootstrap: `govvue-light-dev-bootstrap`
- application: `govvue-light-dev`

## Release artifacts

Every deployable package is stored in the bootstrap bucket using this pattern:

```text
releases/20260919T153012Z/
  cloudformation/app-20260919T153012Z.yaml
  cloudformation/bootstrap-20260919T153012Z.yaml
  frontend/govvue-light-frontend-20260919T153012Z.zip
  lambda/govvue-light-api-20260919T153012Z.zip
```

S3 versioning adds an object version ID on top of the timestamped key. Local release manifests are written under `.build/<build-id>/`.
