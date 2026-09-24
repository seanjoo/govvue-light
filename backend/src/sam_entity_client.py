"""SAM.gov Entity Management API v4 client and public-result normalizer."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from runtime_config import RuntimeConfig
from sam_client import RETRYABLE_STATUSES, SamApiError


ENTITY_FILTERS = {
    "uei": "ueiSAM",
    "cage_code": "cageCode",
    "dodaac": "dodaac",
    "legal_business_name": "legalBusinessName",
    "dba_name": "dbaName",
    "sam_registered": "samRegistered",
    "registration_status": "registrationStatus",
    "debt_subject_to_offset": "debtSubjectToOffset",
    "exclusion_status": "exclusionStatusFlag",
    "purpose_registration_code": "purposeOfRegistrationCode",
    "purpose_registration_description": "purposeOfRegistrationDesc",
    "city": "physicalAddressCity",
    "congressional_district": "physicalAddressCongressionalDistrict",
    "country_code": "physicalAddressCountryCode",
    "state": "physicalAddressProvinceOrStateCode",
    "zip": "physicalAddressZipPostalCode",
    "entity_structure_code": "entityStructureCode",
    "entity_structure_description": "entityStructureDesc",
    "organization_structure_code": "organizationStructureCode",
    "organization_structure_description": "organizationStructureDesc",
    "business_type_code": "businessTypeCode",
    "business_type_description": "businessTypeDesc",
    "sba_business_type_code": "sbaBusinessTypeCode",
    "sba_business_type_description": "sbaBusinessTypeDesc",
    "primary_naics": "primaryNaics",
    "naics_code": "naicsCode",
    "naics_description": "naicsDesc",
    "naics_limited_small_business": "naicsLimitedSB",
    "psc_code": "pscCode",
    "psc_description": "pscDesc",
    "incorporation_state_code": "stateOfIncorporationCode",
    "incorporation_state_description": "stateOfIncorporationDesc",
    "incorporation_country_code": "countryOfIncorporationCode",
    "incorporation_country_description": "countryOfIncorporationDesc",
    "disaster_state_code": "servedDisasterStateCode",
    "disaster_state_name": "servedDisasterStateName",
    "disaster_county_code": "servedDisasterCountyCode",
    "disaster_county_name": "servedDisasterCountyName",
    "disaster_msa": "servedDisasterMSA",
    "disaster_response_participant": "isDisasterResponseParticipant",
}

DATE_FILTERS = {
    "registration_date": "registrationDate",
    "activation_date": "activationDate",
    "update_date": "updateDate",
    "expiration_date": "registrationExpirationDate",
    "uei_creation_date": "ueiCreationDate",
}

MULTI_VALUE_FILTERS = {
    "uei",
    "cage_code",
    "registration_status",
    "purpose_registration_code",
    "state",
    "business_type_code",
    "sba_business_type_code",
    "primary_naics",
    "naics_code",
    "psc_code",
    "incorporation_state_code",
    "disaster_state_code",
}

MAX_VALUES_PER_FILTER = 100
MAX_TEXT_LENGTH = 300
DISALLOWED_VALUE_CHARACTERS = re.compile(r"[&|{}^\\]")
UI_FILTERS = set(ENTITY_FILTERS) | {
    f"{name}_{boundary}" for name in DATE_FILTERS for boundary in ("from", "to")
}


def sanitize_entity_criteria(criteria: dict[str, Any]) -> dict[str, str]:
    """Keep only supported browser filters and scalar string values."""
    clean: dict[str, str] = {}
    for key in sorted(UI_FILTERS):
        value = criteria.get(key)
        if value is None:
            continue
        if not isinstance(value, (str, int, float)):
            raise ValueError(f"{key} must be a string")
        text = str(value).strip()
        if text:
            clean[key] = text[:MAX_TEXT_LENGTH]
    return clean


def _clean_value(value: str, name: str) -> str:
    clean = value.strip()
    if DISALLOWED_VALUE_CHARACTERS.search(clean):
        raise ValueError(f"{name} contains a character SAM.gov does not allow")
    return clean[:MAX_TEXT_LENGTH]


def _multi_value(value: str, name: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        clean = _clean_value(part, name)
        normalized = clean.casefold()
        if clean and normalized not in seen:
            seen.add(normalized)
            values.append(clean)
    if len(values) > MAX_VALUES_PER_FILTER:
        raise ValueError(f"{name} accepts at most {MAX_VALUES_PER_FILTER} values")
    if not values:
        return ""
    joined = "~".join(values)
    return f"[{joined}]" if len(values) > 1 else values[0]


def _sam_date(value: str, name: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def build_entity_search_parameters(criteria: dict[str, Any]) -> dict[str, str]:
    clean = sanitize_entity_criteria(criteria)
    params: dict[str, str] = {}
    for browser_name, sam_name in ENTITY_FILTERS.items():
        value = clean.get(browser_name, "")
        if not value:
            continue
        params[sam_name] = (
            _multi_value(value, browser_name)
            if browser_name in MULTI_VALUE_FILTERS
            else _clean_value(value, browser_name)
        )

    for browser_name, sam_name in DATE_FILTERS.items():
        start_raw = clean.get(f"{browser_name}_from", "")
        end_raw = clean.get(f"{browser_name}_to", "")
        if not start_raw and not end_raw:
            continue
        start = _sam_date(start_raw, f"{browser_name}_from") if start_raw else ""
        end = _sam_date(end_raw, f"{browser_name}_to") if end_raw else ""
        if start and end:
            start_date = datetime.strptime(start, "%m/%d/%Y").date()
            end_date = datetime.strptime(end, "%m/%d/%Y").date()
            if start_date > end_date:
                raise ValueError(f"{browser_name}_from cannot be later than {browser_name}_to")
            params[sam_name] = f"[{start},{end}]"
        else:
            params[sam_name] = start or end

    # Match the SAM.gov web search's active-only default while still allowing
    # the browser to explicitly request expired or both statuses.
    if params.get("samRegistered", "").casefold() == "no":
        params.pop("registrationStatus", None)
    else:
        params.setdefault("registrationStatus", "A")
    return params


def _request_json(url: str, params: dict[str, str], config: RuntimeConfig) -> dict[str, Any]:
    request_params = {**params, "api_key": config.sam_api_key}
    request = Request(
        f"{url}?{urlencode(request_params)}",
        headers={"Accept": "application/json", "User-Agent": "GovVue-Light/1.0"},
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=config.sam_request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in RETRYABLE_STATUSES and attempt < 2:
                retry_after = exc.headers.get("Retry-After")
                wait = min(float(retry_after), 5.0) if retry_after else 0.5 * (2**attempt)
                time.sleep(wait)
                continue
            if exc.code in {401, 403}:
                raise SamApiError("SAM.gov rejected the configured entity API access", 502) from exc
            if exc.code == 429:
                raise SamApiError("SAM.gov request limit reached; try again shortly", 429) from exc
            if exc.code == 400:
                raise SamApiError("SAM.gov rejected one or more entity search filters", 400) from exc
            raise SamApiError(f"SAM.gov entity API returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < 2:
                time.sleep(0.5 * (2**attempt))
                continue
            raise SamApiError("SAM.gov entity search is temporarily unavailable") from exc
    raise SamApiError("SAM.gov entity search failed")


def search_entities(
    params: dict[str, str], page_index: int, config: RuntimeConfig
) -> dict[str, Any]:
    upstream = {
        **params,
        "includeSections": "entityRegistration,coreData,assertions",
        "page": str(max(0, page_index)),
        "size": "10",
    }
    payload = _request_json(config.sam_entities_api, upstream, config)
    records = payload.get("entityData") or []
    total = min(int(payload.get("totalRecords") or len(records)), 10_000)
    return {
        "total_records": total,
        "records": [normalize_entity(record, config) for record in records],
    }


def _compact_list(values: Any, code_key: str, description_key: str) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        code = str(item.get(code_key) or "").strip()
        description = str(item.get(description_key) or "").strip()
        identity = (code, description)
        if (code or description) and identity not in seen:
            seen.add(identity)
            result.append({"code": code, "description": description})
        if len(result) >= 50:
            break
    return result


def normalize_entity(record: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    registration = record.get("entityRegistration") or {}
    core = record.get("coreData") or {}
    assertions = record.get("assertions") or {}
    physical = core.get("physicalAddress") or {}
    mailing = core.get("mailingAddress") or {}
    entity_information = core.get("entityInformation") or {}
    general = core.get("generalInformation") or {}
    business_types = core.get("businessTypes") or {}
    goods = assertions.get("goodsAndServices") or {}
    disaster = assertions.get("disasterReliefData") or {}
    uei = str(registration.get("ueiSAM") or "").strip()
    status = str(registration.get("registrationStatus") or "").strip()
    sam_url = (
        f"{config.sam_site_base_url.rstrip('/')}/entity/{uei}/coreData"
        f"?status={status or 'Active'}"
        if uei
        else f"{config.sam_site_base_url.rstrip('/')}/entity-information"
    )

    naics = _compact_list(
        goods.get("naicsList"), "naicsCode", "naicsDescription"
    )
    psc = _compact_list(goods.get("pscList"), "pscCode", "pscDescription")
    return {
        "uei": uei,
        "legal_business_name": registration.get("legalBusinessName") or "Unnamed entity",
        "dba_name": registration.get("dbaName") or "",
        "cage_code": registration.get("cageCode") or "",
        "dodaac": registration.get("dodaac") or "",
        "sam_registered": registration.get("samRegistered") or "",
        "registration_status": status,
        "purpose_of_registration": registration.get("purposeOfRegistrationDesc") or "",
        "registration_date": registration.get("registrationDate") or "",
        "activation_date": registration.get("activationDate") or "",
        "last_update_date": registration.get("lastUpdateDate") or "",
        "expiration_date": registration.get("registrationExpirationDate") or "",
        "uei_status": registration.get("ueiStatus") or "",
        "exclusion_status": registration.get("exclusionStatusFlag") or "",
        "address": {
            "line1": physical.get("addressLine1") or "",
            "line2": physical.get("addressLine2") or "",
            "city": physical.get("city") or "",
            "state": physical.get("stateOrProvinceCode") or "",
            "zip": "-".join(
                part for part in (str(physical.get("zipCode") or ""), str(physical.get("zipCodePlus4") or "")) if part
            ),
            "country": physical.get("countryCode") or "",
        },
        "mailing_address": {
            "city": mailing.get("city") or "",
            "state": mailing.get("stateOrProvinceCode") or "",
            "zip": mailing.get("zipCode") or "",
            "country": mailing.get("countryCode") or "",
        },
        "website": entity_information.get("entityURL") or entity_information.get("entityUrl") or "",
        "entity_structure": general.get("entityStructureDesc") or "",
        "organization_structure": general.get("organizationStructureDesc") or "",
        "business_types": _compact_list(
            business_types.get("businessTypeList"), "businessTypeCode", "businessTypeDesc"
        ),
        "sba_business_types": _compact_list(
            business_types.get("sbaBusinessTypeList"), "sbaBusinessTypeCode", "sbaBusinessTypeDesc"
        ),
        "primary_naics": goods.get("primaryNaics") or "",
        "naics": naics,
        "psc": psc,
        "disaster_response_participant": disaster.get("disasterRegistryFlag") or "",
        "sam_url": sam_url,
    }
