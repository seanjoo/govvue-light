export default function PrivacyPage() {
  return (
    <article className="public-content public-policy">
      <p className="page-kicker">GovVue Light</p>
      <h1>Privacy Policy</h1>
      <p className="public-policy__date">Effective September 24, 2026</p>
      <p>
        This policy explains how GovVue Light collects, uses, and protects information when invited users access the application.
      </p>

      <section>
        <h2>Information we collect</h2>
        <ul>
          <li><strong>Account information:</strong> email address, account role, authentication identifiers, and basic profile information supplied by Google when Google sign-in is used.</li>
          <li><strong>Application information:</strong> searches, search history, saved opportunities and entities, saved searches, notification settings, and notification results.</li>
          <li><strong>Operational information:</strong> limited security, diagnostic, and service logs needed to operate and troubleshoot the application.</li>
        </ul>
      </section>

      <section>
        <h2>Google user data</h2>
        <p>
          GovVue Light uses Google only for authentication and requests the <code>openid</code>, <code>email</code>, and <code>profile</code> scopes. It uses this information to match a verified Google email address to an existing invited GovVue Light account. It does not request or access Gmail, Drive, contacts, calendars, or other Google product data.
        </p>
        <p>
          GovVue Light’s use and transfer of information received from Google APIs adheres to the Google API Services User Data Policy, including its Limited Use requirements.
        </p>
      </section>

      <section>
        <h2>How information is used</h2>
        <p>
          Information is used to authenticate users, perform requested SAM.gov searches, retain user-selected records and preferences, deliver configured notifications, maintain security, and diagnose service problems. GovVue Light does not use search results or account information for AI processing, advertising, or user profiling.
        </p>
      </section>

      <section>
        <h2>Service providers and disclosure</h2>
        <p>
          GovVue Light runs on Amazon Web Services, including Cognito, Lambda, DynamoDB, S3, CloudFront, and SES. Search criteria needed to fulfill a request are sent to SAM.gov. Google processes authentication when Google sign-in is selected. Information is not sold, rented, or shared for advertising. It may be disclosed when required by law or necessary to protect the application and its users.
        </p>
      </section>

      <section>
        <h2>Retention and deletion</h2>
        <p>
          Saved records and preferences remain until a user or administrator removes them or the account is deleted. Search history is normally retained for 90 days, daily feed snapshots for 30 days, notification run information for 90 days, and operational logs for 30 days. Backup or security records may persist for a limited additional period.
        </p>
        <p>
          To request account or associated-data deletion, contact <a href="mailto:admin@govvue.com">admin@govvue.com</a> from the email address associated with the account.
        </p>
      </section>

      <section>
        <h2>Security</h2>
        <p>
          GovVue Light uses access controls, encrypted connections, private storage, and managed authentication services intended to protect user information. No security method can guarantee absolute protection.
        </p>
      </section>

      <section>
        <h2>Policy changes and contact</h2>
        <p>
          This policy may be updated as the application changes. The effective date above will be revised when material changes are published. Questions can be sent to <a href="mailto:admin@govvue.com">admin@govvue.com</a>.
        </p>
      </section>
    </article>
  );
}
