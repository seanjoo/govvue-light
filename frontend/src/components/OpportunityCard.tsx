import { Link } from 'react-router-dom';
import { detailUrl } from '../lib/detailNavigation';
import type { Opportunity, ResultNavigation } from '../types';

interface Props {
  opportunity: Opportunity;
  onSave?: (opportunity: Opportunity) => void;
  navigation?: ResultNavigation;
  returnTo?: string;
  sourceLabel?: string;
}

export default function OpportunityCard({ opportunity, onSave, navigation, returnTo, sourceLabel }: Props) {
  const destination = navigation?.return_to || returnTo;
  const label = navigation?.source_label || sourceLabel;
  return (
    <article className="opportunity-card">
      <div className="opportunity-card__heading">
        <div>
          <div className="opportunity-card__eyebrow">
            {opportunity.type || 'Opportunity'}
            {opportunity.set_aside && <span className="usa-tag">{opportunity.set_aside}</span>}
          </div>
          <h2 className="font-heading-lg margin-y-1">
            <Link
              to={detailUrl(`/opportunities/${encodeURIComponent(opportunity.notice_id)}`, destination, label)}
              state={destination ? {
                resultNavigation: navigation,
                returnTo: destination,
                sourceLabel: label,
              } : undefined}
            >{opportunity.title}</Link>
          </h2>
        </div>
        {onSave && (
          <button type="button" className="usa-button usa-button--outline" onClick={() => onSave(opportunity)}>
            Save
          </button>
        )}
      </div>
      <dl className="opportunity-meta">
        <div><dt>Notice ID</dt><dd>{opportunity.notice_id || '—'}</dd></div>
        <div><dt>Solicitation</dt><dd>{opportunity.solicitation_number || '—'}</dd></div>
        <div><dt>Response due</dt><dd>{opportunity.response_deadline || 'Not provided'}</dd></div>
        <div><dt>NAICS</dt><dd>{opportunity.naics_code || '—'}</dd></div>
      </dl>
      <p className="text-base margin-bottom-0">{opportunity.agency_path || opportunity.organization_name}</p>
    </article>
  );
}
