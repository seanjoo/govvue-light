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
- a working AWS CLI profile named `workshop` with CloudFormation, IAM, Lambda, API Gateway, Cognito, DynamoDB, S3, CloudFront, Route 53, CloudWatch Logs, SSM, and KMS permissions

The development region comes from `config/dev.govvue-light.yml` and is
`us-east-1` by default.

These account-level prerequisites already exist and are deliberately not
created by the application stacks:

- the `workshop` AWS account and CLI profile;
- the public `govvue.com` Route 53 hosted zone and registrar delegation;
- an issued ACM certificate for `app.govvue.com` in `us-east-1`; and
- a Google Cloud Web OAuth client configured for the Cognito callback; and
- the local `config/dev.govvue-light.yml`, including the SAM.gov API key and Google OAuth client values.

CloudFormation attaches the existing certificate and creates the
`app.govvue.com` A and AAAA aliases. The certificate itself and the hosted zone
remain external prerequisites.

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
hosted_zone_id: Z04260832ZB8NBYSOXBA7
acm_certificate_arn: arn:aws:acm:us-east-1:428613119099:certificate/f810f621-f8fb-449e-9f51-a793dcc69904
cors_allowed_origin: https://app.govvue.com
cognito_domain_prefix: govvue-light-dev-428613119099
```

In the Google OAuth client, use exactly:

```text
Authorized JavaScript origin:
https://govvue-light-dev-428613119099.auth.us-east-1.amazoncognito.com

Authorized redirect URI:
https://govvue-light-dev-428613119099.auth.us-east-1.amazoncognito.com/oauth2/idpresponse
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
  --domain-prefix govvue-light-dev-428613119099
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

The application stack also enables the daily EventBridge schedule, SQS page and
notification queues, daily-feed and notification Lambdas, SES domain identity,
DKIM records, and daily-feed storage.

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

The Cognito invitation and SES recipient verification are separate messages.
The user pool uses the verified `govvue.com` SES identity with
`EmailSendingAccount` set to `DEVELOPER` for branded invitations, password
recovery, and verification messages. These account messages use the workshop
SES quota and sending-access status.

The application stack configures `app.govvue.com` as the CloudFront alternate domain name, attaches the workshop ACM certificate, and creates Route 53 A and AAAA alias records in the workshop hosted zone.

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

Changes to `app_domain_name`, `hosted_zone_id`, or `acm_certificate_arn` also
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
