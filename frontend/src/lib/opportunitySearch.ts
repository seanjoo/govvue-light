export const DEFAULT_OPPORTUNITY_SORT = 'response_deadline_desc';

export const OPPORTUNITY_SORT_OPTIONS = [
  ['response_deadline_desc', 'Response due — latest first'],
  ['response_deadline_asc', 'Response due — soonest first'],
  ['posted_desc', 'Posted date — newest first'],
  ['posted_asc', 'Posted date — oldest first'],
] as const;

export function compactSearchCriteria(criteria: Record<string, string>) {
  return Object.fromEntries(Object.entries(criteria).filter(([, value]) => value));
}

export function opportunityResultsUrl(criteria: Record<string, string>, page = 1) {
  const params = new URLSearchParams(compactSearchCriteria(criteria));
  params.set('page', String(page));
  return `/search/results?${params}`;
}

export function opportunityFiltersUrl(criteria: Record<string, string>) {
  const params = new URLSearchParams(compactSearchCriteria(criteria));
  return params.size ? `/search?${params}` : '/search';
}

export function opportunityResultsQuery(search: string) {
  const params = new URLSearchParams(search);
  const rawPage = Number(params.get('page'));
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? Math.min(rawPage, 10_000) : 1;
  params.delete('page');
  params.delete('per_page');
  params.delete('record_history');
  const criteria = Object.fromEntries(params.entries());
  if (!OPPORTUNITY_SORT_OPTIONS.some(([value]) => value === criteria.sort)) {
    criteria.sort = DEFAULT_OPPORTUNITY_SORT;
  }
  return { criteria, page };
}
