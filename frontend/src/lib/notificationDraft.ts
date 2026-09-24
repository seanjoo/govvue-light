export interface NotificationDraft {
  name: string;
  criteria: Record<string, string>;
}

const DAILY_NOTIFICATION_FILTERS = new Set([
  'title',
  'notice_id',
  'solicitation_number',
  'ptype',
  'naics_code',
  'classification_code',
  'set_aside',
  'state',
  'zip',
  'organization_code',
  'organization_name',
  'response_deadline_from',
  'response_deadline_to',
  'open_deadlines_only',
]);

export function createNotificationDraft(
  sourceName: string,
  criteria: Record<string, string>,
): NotificationDraft {
  const notificationCriteria = Object.fromEntries(
    Object.entries(criteria).filter(([key, value]) => (
      DAILY_NOTIFICATION_FILTERS.has(key) && value.trim()
    )),
  );
  const cleanName = sourceName.trim() || 'Search';
  return {
    name: `Daily: ${cleanName}`.slice(0, 100),
    criteria: notificationCriteria,
  };
}
