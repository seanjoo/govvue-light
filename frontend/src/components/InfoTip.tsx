import { useId } from 'react';

export default function InfoTip({ text, label = 'More information' }: { text: string; label?: string }) {
  const tooltipId = useId();
  return (
    <span className="info-tip">
      <button className="info-tip__button" type="button" aria-label={label} aria-describedby={tooltipId}>i</button>
      <span className="info-tip__content" id={tooltipId} role="tooltip">{text}</span>
    </span>
  );
}
