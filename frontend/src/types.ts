export interface Opportunity {
  notice_id: string;
  title: string;
  solicitation_number: string;
  type: string;
  type_code: string;
  posted_date: string;
  response_deadline: string;
  archive_date: string;
  active: boolean;
  naics_code: string;
  classification_code: string;
  set_aside: string;
  set_aside_code: string;
  organization_name: string;
  agency_path: string;
  place_of_performance: {
    city: string;
    state: string;
    zip: string;
    country: string;
  };
  contact: {
    name: string;
    email: string;
    phone: string;
  };
  sam_url: string;
  description?: string;
  saved_at?: number;
}

export interface SearchResponse {
  items: Opportunity[];
  page: number;
  per_page: number;
  total_records: number;
  has_next: boolean;
  cache_hit: boolean;
  upstream_queries: number;
  sort: string;
}

export interface Company {
  company_id: string;
  name: string;
  created_at: number;
  updated_at: number;
}

export interface AdminCompany extends Company {
  member_count: number;
  managers: Array<{ username: string; email: string }>;
}

export interface UserContext {
  sub: string;
  email: string;
  role: 'admin' | 'user';
  groups: string[];
  company_id: string;
  company_role: 'manager' | 'member';
  company: Company | null;
  features: string[];
  can_edit_company_profile: boolean;
}

export interface CompanyProfile {
  overview: string;
  capabilities: string;
  differentiators: string;
  past_performance: string;
  naics_codes: string;
  psc_codes: string;
  target_agencies: string;
  set_aside_eligibility: string;
  positive_keywords: string;
  negative_keywords: string;
}

export interface CompanyProfileResponse {
  company: Company;
  profile: CompanyProfile;
  can_edit: boolean;
}

export interface CompanyMember {
  username: string;
  sub: string;
  email: string;
  enabled: boolean;
  status: string;
  company_id: string;
  company_role: 'manager' | 'member';
  features: string[];
  ses_status?: string;
}

export interface SearchInterpretation {
  used_company_profile: boolean;
  interpretation: string;
  assumptions: string[];
  criteria: Record<string, string>;
  company_id: string;
  company_name: string;
}

export interface ResultNavigation {
  kind: 'opportunity' | 'entity';
  ids: string[];
  index: number;
  page: number;
  per_page: number;
  total_records: number;
  has_next: boolean;
  criteria: Record<string, string>;
  return_to: string;
  source_label: string;
  paginated: boolean;
  entities?: Entity[];
}

export interface ResultNavigationState {
  resultNavigation?: ResultNavigation;
  entity?: Entity;
  returnTo?: string;
  sourceLabel?: string;
}

export interface EntityClassification {
  code: string;
  description: string;
}

export interface Entity {
  uei: string;
  legal_business_name: string;
  dba_name: string;
  cage_code: string;
  dodaac: string;
  sam_registered: string;
  registration_status: string;
  purpose_of_registration: string;
  registration_date: string;
  activation_date: string;
  last_update_date: string;
  expiration_date: string;
  uei_status: string;
  exclusion_status: string;
  address: {
    line1: string;
    line2: string;
    city: string;
    state: string;
    zip: string;
    country: string;
  };
  mailing_address: {
    city: string;
    state: string;
    zip: string;
    country: string;
  };
  website: string;
  entity_structure: string;
  organization_structure: string;
  business_types: EntityClassification[];
  sba_business_types: EntityClassification[];
  primary_naics: string;
  naics: EntityClassification[];
  psc: EntityClassification[];
  disaster_response_participant: string;
  sam_url: string;
  saved_at?: number;
}

export interface EntitySearchResponse {
  items: Entity[];
  page: number;
  per_page: number;
  total_records: number;
  has_next: boolean;
  cache_hit: boolean;
}

export interface SavedSearch {
  id: string;
  name: string;
  criteria: Record<string, string>;
  created_at: number;
}

export interface SearchHistory {
  criteria: Record<string, string>;
  result_count: number;
  created_at: number;
}

export interface DailyNotification {
  id: string;
  name: string;
  criteria: Record<string, string>;
  enabled: boolean;
  schedule_time: string;
  recipient_email: string;
  created_at: number;
  updated_at: number;
}

export interface DailyNotificationRun {
  run_date: string;
  criteria: Record<string, string>;
  match_count: number;
  status: string;
  email_status: string;
  completed_at: number;
}

export interface DailyNotificationRunsResponse {
  notification: DailyNotification;
  items: DailyNotificationRun[];
}

export interface DailyNotificationResultsResponse {
  notification: DailyNotification;
  run: DailyNotificationRun;
  items: Opportunity[];
  next_cursor: string | null;
}

export interface AdminUser {
  username: string;
  sub: string;
  email: string;
  email_verified: boolean;
  role: 'admin' | 'user';
  groups: string[];
  enabled: boolean;
  status: string;
  created_at: string;
  updated_at: string;
  ses_status?: string;
  company_id: string;
  company_name: string;
  company_role: 'manager' | 'member';
  features: string[];
}
