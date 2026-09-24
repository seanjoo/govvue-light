# GovVue Light

GovVue Light is a small, private search-and-view application for SAM.gov contract opportunities and entities. It searches SAM.gov on demand, caches upstream pages to reduce API calls, and lets each Cognito user keep reusable searches and saved opportunity and entity snapshots.

The frontend uses the U.S. Web Design System (USWDS). The deployment is serverless and does not attach Lambda to a VPC, so it does not require a NAT gateway.

## Included

- React 19, TypeScript, Vite, and USWDS frontend
- Cognito email/password or Google authentication with invited-user account linking, `admin` and `user` roles, emailed temporary passwords, self-service password changes, and an administrator user-management screen
- API Gateway HTTP API with a Cognito JWT authorizer
- Python Lambda API packaged separately from CloudFormation
- Direct, active-only SAM.gov search with hierarchical 2022 NAICS selection, multi-value filters, converged results, 1,000-record upstream caching, and 25-record UI pages
- Direct SAM.gov Entity Management API v4 search with public-data filters, native multi-value parameters, saved entity searches, 10-record cached pages, and a saved-entity watchlist
- Opportunity detail and plain-text description retrieval
- Saved opportunities with bulk removal
- Saved entities with bulk removal and direct SAM.gov detail links
- Saved searches and expiring per-user search history, with direct conversion of saved or completed searches into daily notifications
- Editable daily notifications with per-notification Eastern-time schedules, shared SAM.gov feed ingestion, result history, and SES email
- DynamoDB on-demand storage and private S3 search cache
- Private S3 website origin behind CloudFront
- `app.govvue.com` Route 53 aliases managed by CloudFormation, using the existing workshop ACM certificate
- YAML-to-SSM configuration, including SecureString SAM.gov and Google OAuth secrets
- Timestamped Lambda, frontend, and CloudFormation release artifacts
- Component deployment scripts and one end-to-end deployment command

## Quick start

The local development configuration has been imported to `config/dev.govvue-light.yml`. That file is permissioned `0600` and ignored by Git.

```bash
cd /Users/seanjoo/Documents/dev/govvue_light
./scripts/validate.sh --env dev
./scripts/sync-config.sh --env dev --dry-run
./scripts/deploy.sh --env dev
./scripts/create-user.sh --env dev --email you@example.com
```

While the workshop SES account is sandboxed, this also requests SES
verification for the user's address. The user must follow that verification
link before daily-feed emails can be delivered. Cognito sends a separate
invitation containing the generated temporary password.

`deploy.sh` creates one UTC build identifier such as `20260919T153012Z` and uses it for every artifact in that release.

No AWS resources are deployed merely by building or validating the project.

All application deployment commands use only the `workshop` AWS profile.

The ACM certificate, `govvue.com` hosted zone, domain delegation, local YAML,
SSM synchronization, release uploads, frontend publication, and Cognito user
creation are prerequisites or script-managed operations. Runtime application
infrastructure and the `app.govvue.com` A/AAAA aliases are CloudFormation-managed.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Initial deployment and updates](docs/DEPLOYMENT.md)
- [Configuration and SSM mapping](docs/CONFIGURATION.md)
- [Operations and troubleshooting](docs/OPERATIONS.md)
- [HTTP API](docs/API.md)

## Repository layout

```text
backend/          Lambda source and tests
config/           local environment YAML; real files are Git-ignored
docs/             architecture and operating documentation
frontend/         React/Vite/USWDS application
infrastructure/   CloudFormation templates (no embedded Lambda source)
scripts/          build, validation, configuration, and deployment commands
```
