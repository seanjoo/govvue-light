# HTTP API

Except for `/health`, requests require a Cognito ID token in `Authorization: Bearer <token>`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Unauthenticated service health |
| `GET` | `/me` | Current Cognito identity, role, and group memberships |
| `GET` | `/admin/users` | Admin-only Cognito user list |
| `POST` | `/admin/users` | Admin-only user invitation using `email` and optional `role` |
| `PUT` | `/admin/users/{username}` | Admin-only role and enabled-status update |
| `DELETE` | `/admin/users/{username}` | Admin-only account and GovVue user-data deletion |
| `POST` | `/admin/users/{username}/reset-password` | Admin-only reset email or invitation resend |
| `GET` | `/opportunities/search` | Search active SAM.gov opportunities |
| `GET` | `/opportunities/{noticeId}` | Basic details and plain-text description |
| `GET` | `/entities/search` | Search SAM.gov Entity Management API v4 |
| `GET` | `/saved-opportunities` | List the user's saved opportunities |
| `POST` | `/saved-opportunities` | Save or replace an opportunity snapshot |
| `DELETE` | `/saved-opportunities` | Bulk delete using `{"notice_ids":[...]}` |
| `GET` | `/saved-entities` | List the user's saved entity snapshots |
| `POST` | `/saved-entities` | Save or replace an entity snapshot |
| `DELETE` | `/saved-entities` | Bulk delete using `{"ueis":[...]}` |
| `GET` | `/saved-searches` | List named searches |
| `POST` | `/saved-searches` | Create using `{"name":"...","criteria":{...}}` |
| `DELETE` | `/saved-searches/{id}` | Delete one saved search |
| `GET` | `/saved-entity-searches` | List named entity searches |
| `POST` | `/saved-entity-searches` | Create using `{"name":"...","criteria":{...}}` |
| `DELETE` | `/saved-entity-searches/{id}` | Delete one saved entity search |
| `GET` | `/search-history` | Return the 50 most recent searches |
| `DELETE` | `/search-history` | Clear the user's search history |
| `GET` | `/daily-notifications` | List daily notification definitions |
| `POST` | `/daily-notifications` | Create using `name`, `criteria`, `enabled`, and `schedule_time` |
| `POST` | `/daily-notifications/run` | Queue an immediate refresh of the shared feed and all enabled notifications |
| `GET` | `/daily-notifications/{id}` | Retrieve one notification |
| `PUT` | `/daily-notifications/{id}` | Replace its name, criteria, enabled state, and schedule time |
| `DELETE` | `/daily-notifications/{id}` | Delete a notification definition |
| `GET` | `/daily-notifications/{id}/runs` | List retained daily runs |
| `GET` | `/daily-notifications/{id}/runs/{date}` | Return a cursor-paginated daily result page |

## Search parameters

Searches may use either a fixed range or a rolling window. `posted_from` and
`posted_to` use `YYYY-MM-DD` in the browser and are converted to the format
expected by SAM.gov. Alternatively, `posted_within` accepts `7`, `14`, `30`,
`60`, or `90`; the service resolves that value to a range ending on the day
each search executes (including that day). This keeps saved rolling searches
current. If neither form is supplied, the configured lookback window ending
today is used.

| Browser parameter | SAM.gov parameter |
|---|---|
| `posted_within` | Resolved at runtime to `postedFrom` and `postedTo` |
| `posted_from` | `postedFrom` |
| `posted_to` | `postedTo` |
| `ptype` | `ptype` |
| `solicitation_number` | `solnum` |
| `notice_id` | `noticeid` |
| `title` | `title` |
| `state` | `state` |
| `zip` | `zip` |
| `organization_code` | `organizationCode` |
| `organization_name` | `organizationName` |
| `set_aside` | `typeOfSetAside` |
| `naics_code` | `ncode` |
| `classification_code` | `ccode` |
| `response_deadline_from` | `rdlfrom` |
| `response_deadline_to` | `rdlto` |

`ptype`, `state`, `zip`, `organization_code`, `set_aside`, `naics_code`, and
`classification_code` accept comma-separated values. Values within one filter
use OR semantics; different filters use AND semantics. GovVue sends multiple
`ptype` parameters in one SAM.gov request. Because SAM.gov accepts only one
value for the other listed parameters, GovVue expands those selections into a
bounded cross-product, runs the requests concurrently, and deduplicates the
converged results by Notice ID. `search_max_fanout` limits that cross-product.

The browser's NAICS picker is generated from the official 2022 Census NAICS
hierarchy and emits comma-separated six-digit `naics_code` values. Parent
categories are navigation-only because SAM.gov's `ncode` filter requires the
specific six-digit industry code to return matching opportunities.

The server always sends `status=active` and independently removes any item whose returned `active` field is not `Yes`.

Local display controls are `page`, `per_page` (10–100), `record_history`, and
`sort`. Supported sort values are `response_deadline_desc`,
`response_deadline_asc`, `posted_desc`, and `posted_asc`. SAM.gov does not
provide upstream sorting, so GovVue loads the complete matching page set for
orders other than `posted_desc` and sorts after merging and deduplication. Records without
the selected date are placed last. `search_max_sort_pages` bounds the work and
causes overly broad searches to return a narrowing prompt instead of an
inaccurate page-local order. These display controls are never forwarded to
SAM.gov as filters.

Daily notifications accept the same multi-value criteria except `posted_from`,
`posted_to`, and `posted_within`; the service always supplies yesterday through
the run date. The UI can prefill a notification from a saved search or from the
most recently completed search result while omitting those posted-date fields.
Notifications due in the same five-minute dispatcher window match one shared
feed locally and therefore do not create one SAM.gov search per notification.
Daily result pagination uses `limit` and an opaque
`cursor`. The returned `next_cursor` should be passed unchanged and is
validated against the authenticated user's notification run.

`schedule_time` uses 24-hour `HH:MM` in five-minute increments. It defaults to
`06:15` and is interpreted in the configured `America/New_York` time zone. A
five-minute EventBridge dispatcher starts a feed only when one or more
notifications are due. The manual run endpoint refreshes the same
yesterday-through-today feed and then processes every enabled notification.
Reprocessing an existing run date updates its stored matches without sending
an email that was already sent for that notification and date.

## Entity search parameters

Entity search uses SAM.gov Entity Management API v4 and maps a one-based
browser `page` to SAM's zero-based page number. SAM fixes the synchronous page
size at 10 and makes only the first 10,000 matching records available. GovVue
caches each normalized page using the normal search-cache TTL.

If `registration_status` is omitted, GovVue sends `A` so searches default to
active registrations. Comma-separated values for UEI, CAGE, registration
status, purpose, state, business/SBA type code, NAICS, PSC, incorporation
state, and disaster-response state are converted to SAM's native OR syntax.
Different parameters use AND semantics.

| Browser parameter | SAM.gov parameter |
|---|---|
| `uei` | `ueiSAM` |
| `cage_code` | `cageCode` |
| `dodaac` | `dodaac` |
| `legal_business_name` | `legalBusinessName` |
| `dba_name` | `dbaName` |
| `sam_registered` | `samRegistered` |
| `registration_status` | `registrationStatus` |
| `debt_subject_to_offset` | `debtSubjectToOffset` |
| `exclusion_status` | `exclusionStatusFlag` |
| `purpose_registration_code` | `purposeOfRegistrationCode` |
| `purpose_registration_description` | `purposeOfRegistrationDesc` |
| `city` | `physicalAddressCity` |
| `congressional_district` | `physicalAddressCongressionalDistrict` |
| `country_code` | `physicalAddressCountryCode` |
| `state` | `physicalAddressProvinceOrStateCode` |
| `zip` | `physicalAddressZipPostalCode` |
| `entity_structure_code` | `entityStructureCode` |
| `entity_structure_description` | `entityStructureDesc` |
| `organization_structure_code` | `organizationStructureCode` |
| `organization_structure_description` | `organizationStructureDesc` |
| `business_type_code` | `businessTypeCode` |
| `business_type_description` | `businessTypeDesc` |
| `sba_business_type_code` | `sbaBusinessTypeCode` |
| `sba_business_type_description` | `sbaBusinessTypeDesc` |
| `primary_naics` | `primaryNaics` |
| `naics_code` | `naicsCode` |
| `naics_description` | `naicsDesc` |
| `naics_limited_small_business` | `naicsLimitedSB` |
| `psc_code` | `pscCode` |
| `psc_description` | `pscDesc` |
| `incorporation_state_code` | `stateOfIncorporationCode` |
| `incorporation_state_description` | `stateOfIncorporationDesc` |
| `incorporation_country_code` | `countryOfIncorporationCode` |
| `incorporation_country_description` | `countryOfIncorporationDesc` |
| `disaster_state_code` | `servedDisasterStateCode` |
| `disaster_state_name` | `servedDisasterStateName` |
| `disaster_county_code` | `servedDisasterCountyCode` |
| `disaster_county_name` | `servedDisasterCountyName` |
| `disaster_msa` | `servedDisasterMSA` |
| `disaster_response_participant` | `isDisasterResponseParticipant` |

Each date family accepts browser parameters ending in `_from` and `_to`, using
`YYYY-MM-DD`. GovVue converts one boundary to a single SAM date or both
boundaries to SAM's bracketed range syntax.

| Browser date family | SAM.gov parameter |
|---|---|
| `registration_date_from`, `registration_date_to` | `registrationDate` |
| `activation_date_from`, `activation_date_to` | `activationDate` |
| `update_date_from`, `update_date_to` | `updateDate` |
| `expiration_date_from`, `expiration_date_to` | `registrationExpirationDate` |
| `uei_creation_date_from`, `uei_creation_date_to` | `ueiCreationDate` |

GovVue fixes `includeSections` to `entityRegistration,coreData,assertions` and
normalizes only the public-facing registration summary, addresses, website,
business classifications, NAICS, PSC, and disaster-response flag. It does not
expose FOUO/sensitive banking, tax, or point-of-contact fields.
