import { PASSWORD_RULES } from '../lib/passwordPolicy';

export default function PasswordRequirements({
  password,
  confirmPassword,
  id = 'password-requirements',
}: {
  password: string;
  confirmPassword: string;
  id?: string;
}) {
  const started = password.length > 0;
  const confirmationStarted = confirmPassword.length > 0;
  const passwordsMatch = confirmationStarted && password === confirmPassword;
  const metCount = PASSWORD_RULES.filter((rule) => rule.test(password)).length;

  return (
    <div className="password-requirements" id={id}>
      <p className="password-requirements__heading">Password requirements</p>
      <ul>
        {PASSWORD_RULES.map((rule) => {
          const met = rule.test(password);
          const state = met ? 'met' : started ? 'unmet' : 'pending';
          return (
            <li className={`password-requirement password-requirement--${state}`} key={rule.id}>
              <span aria-hidden="true">{met ? '✓' : started ? '×' : '○'}</span>
              {rule.label}
            </li>
          );
        })}
      </ul>
      <p
        id={`${id}-match`}
        className={`password-requirement password-requirement--${passwordsMatch ? 'met' : confirmationStarted ? 'unmet' : 'pending'}`}
      >
        <span aria-hidden="true">{passwordsMatch ? '✓' : confirmationStarted ? '×' : '○'}</span>
        Passwords match
      </p>
      <span className="usa-sr-only" aria-live="polite">
        {started ? `${metCount} of ${PASSWORD_RULES.length} password requirements met.` : 'Enter a new password.'}
        {confirmationStarted ? (passwordsMatch ? ' Passwords match.' : ' Passwords do not match.') : ''}
      </span>
    </div>
  );
}
