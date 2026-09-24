interface SavedSearchCriteriaProps {
  criteria: Record<string, string>;
  emptyLabel: string;
}

export default function SavedSearchCriteria({ criteria, emptyLabel }: SavedSearchCriteriaProps) {
  const entries = Object.entries(criteria).filter(([, value]) => value);
  if (!entries.length) return <p className="saved-search-criteria__summary">{emptyLabel}</p>;

  const preview = [...entries]
    .sort(([leftKey, leftValue], [rightKey, rightValue]) => previewPriority(rightKey, rightValue) - previewPriority(leftKey, leftValue))
    .slice(0, 3);
  const hasDetails = entries.length > preview.length || entries.some(([, value]) => splitValues(value).length > 3 || value.length > 64);

  return (
    <section className="saved-search-criteria" aria-label="Search filters">
      <p className="saved-search-criteria__summary">
        {preview.map(([key, value], index) => (
          <span className="saved-search-criteria__item" key={key}>
            {index > 0 && <span aria-hidden="true"> · </span>}
            <strong>{labelFor(key)}:</strong> {previewValue(key, value)}
          </span>
        ))}
        {entries.length > preview.length && <span> · +{entries.length - preview.length} more filters</span>}
      </p>
      {hasDetails && (
        <details className="saved-search-criteria__details">
          <summary>Show all filters</summary>
          <dl>
            {entries.map(([key, value]) => (
              <div key={key}>
                <dt>{labelFor(key)}</dt>
                <dd>{displayValue(key, value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </section>
  );
}

function splitValues(value: string) {
  return value.split(',').map((part) => part.trim()).filter(Boolean);
}

function previewPriority(key: string, value: string) {
  if (key.includes('naics')) return 3;
  if (splitValues(value).length > 1) return 2;
  if (key === 'title' || key === 'legal_business_name') return 1;
  return 0;
}

function labelFor(key: string) {
  if (key === 'posted_within') return 'Posted date';
  if (key === 'open_deadlines_only') return 'Response deadline';
  if (key === 'sort') return 'Sort order';
  return key.replaceAll('_', ' ').replace(/^\w/, (character) => character.toUpperCase());
}

function previewValue(key: string, value: string) {
  if (key === 'posted_within') return `Last ${value} days`;
  if (key === 'open_deadlines_only') return 'Due today or later';
  if (key === 'sort') return sortLabel(value);
  const values = splitValues(value);
  if (values.length > 3) return `${values.slice(0, 3).join(', ')} +${values.length - 3} more`;
  return value.length > 64 ? `${value.slice(0, 61)}…` : displayValue(key, value);
}

function displayValue(key: string, value: string) {
  if (key === 'posted_within') return `Last ${value} days`;
  if (key === 'open_deadlines_only') return 'Due today or later';
  if (key === 'sort') return sortLabel(value);
  return splitValues(value).join(', ');
}

function sortLabel(value: string) {
  const labels: Record<string, string> = {
    posted_desc: 'Posted date — newest first',
    posted_asc: 'Posted date — oldest first',
    response_deadline_asc: 'Response due — soonest first',
    response_deadline_desc: 'Response due — latest first',
  };
  return labels[value] || value;
}
