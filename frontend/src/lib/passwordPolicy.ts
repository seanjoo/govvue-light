export interface PasswordRule {
  id: string;
  label: string;
  test: (password: string) => boolean;
}

export const PASSWORD_RULES: PasswordRule[] = [
  { id: 'length', label: 'At least 12 characters', test: (password) => password.length >= 12 },
  { id: 'uppercase', label: 'At least one uppercase letter', test: (password) => /[A-Z]/.test(password) },
  { id: 'lowercase', label: 'At least one lowercase letter', test: (password) => /[a-z]/.test(password) },
  { id: 'number', label: 'At least one number', test: (password) => /[0-9]/.test(password) },
  { id: 'symbol', label: 'At least one symbol', test: (password) => /[^A-Za-z0-9\s]/.test(password) },
];

export function passwordMeetsPolicy(password: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(password));
}
