const ALLOWED_RETURN_PATHS = [
  '/search',
  '/entities',
  '/saved',
  '/saved-entities',
  '/notifications',
];

export function detailUrl(path: string, returnTo?: string, sourceLabel?: string) {
  if (!returnTo) return path;
  const params = new URLSearchParams({ return_to: returnTo });
  if (sourceLabel) params.set('source_label', sourceLabel);
  return `${path}?${params}`;
}

export function safeReturnTo(value: string | null | undefined, fallback: string) {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return fallback;
  const pathname = value.split(/[?#]/, 1)[0];
  return ALLOWED_RETURN_PATHS.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
    ? value
    : fallback;
}

export function safeSourceLabel(value: string | null | undefined, fallback: string) {
  const normalized = value?.trim();
  return normalized && normalized.length <= 60 ? normalized : fallback;
}
