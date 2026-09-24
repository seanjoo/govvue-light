import { Link } from 'react-router-dom';
import { detailUrl } from '../lib/detailNavigation';
import type { Entity, ResultNavigation } from '../types';

interface Props {
  entity: Entity;
  onSave?: (entity: Entity) => void;
  selected?: boolean;
  onSelect?: (uei: string, selected: boolean) => void;
  navigation?: ResultNavigation;
  returnTo?: string;
  sourceLabel?: string;
}

function address(entity: Entity) {
  return [
    entity.address.line1,
    entity.address.line2,
    [entity.address.city, entity.address.state, entity.address.zip].filter(Boolean).join(', '),
    entity.address.country,
  ].filter(Boolean).join(' · ');
}

export default function EntityCard({ entity, onSave, selected, onSelect, navigation, returnTo, sourceLabel }: Props) {
  const destination = navigation?.return_to || returnTo;
  const label = navigation?.source_label || sourceLabel;
  const businessTypes = [...entity.business_types, ...entity.sba_business_types]
    .map((item) => item.description || item.code)
    .filter(Boolean)
    .slice(0, 6);
  return (
    <article className="opportunity-card entity-card">
      <div className="opportunity-card__heading">
        <div>
          <div className="opportunity-card__eyebrow">
            {entity.registration_status || 'Registration status unavailable'}
            {entity.cage_code && <span className="usa-tag">CAGE {entity.cage_code}</span>}
          </div>
          <h2 className="font-heading-lg margin-y-1">
            <Link
              to={detailUrl(`/entities/${encodeURIComponent(entity.uei)}`, destination, label)}
              state={{
                resultNavigation: navigation,
                entity,
                returnTo: destination,
                sourceLabel: label,
              }}
            >{entity.legal_business_name}</Link>
          </h2>
          {entity.dba_name && <p className="margin-y-0">Doing business as {entity.dba_name}</p>}
        </div>
        {onSave && <button type="button" className="usa-button usa-button--outline" onClick={() => onSave(entity)}>Save</button>}
        {onSelect && (
          <div className="usa-checkbox saved-entity-select">
            <input className="usa-checkbox__input" id={`saved-entity-${entity.uei}`} type="checkbox" checked={selected} onChange={(event) => onSelect(entity.uei, event.target.checked)} />
            <label className="usa-checkbox__label" htmlFor={`saved-entity-${entity.uei}`}>Select</label>
          </div>
        )}
      </div>
      <dl className="opportunity-meta entity-meta">
        <div><dt>UEI</dt><dd>{entity.uei || '—'}</dd></div>
        <div><dt>Registration expires</dt><dd>{entity.expiration_date || 'Not provided'}</dd></div>
        <div><dt>Primary NAICS</dt><dd>{entity.primary_naics || '—'}</dd></div>
        <div><dt>Purpose</dt><dd>{entity.purpose_of_registration || '—'}</dd></div>
      </dl>
      {address(entity) && <p className="text-base margin-bottom-1">{address(entity)}</p>}
      {businessTypes.length > 0 && <p className="entity-card__classifications"><strong>Business types:</strong> {businessTypes.join(' · ')}</p>}
      <div className="entity-card__actions">
        <a href={entity.sam_url} target="_blank" rel="noreferrer">View full entity on SAM.gov</a>
        {entity.website && <a href={/^https?:\/\//i.test(entity.website) ? entity.website : `https://${entity.website}`} target="_blank" rel="noreferrer">Entity website</a>}
      </div>
    </article>
  );
}
