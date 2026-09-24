import { Link } from 'react-router-dom';

export default function AboutPage() {
  return (
    <article className="public-content">
      <div className="public-hero">
        <p className="page-kicker">Private federal market research</p>
        <h1>About GovVue Light</h1>
        <p className="public-hero__lead">
          GovVue Light helps a small group of invited users search, review, and organize public federal contracting information from SAM.gov.
        </p>
        <div className="public-actions">
          <Link className="usa-button" to="/login">Sign in to GovVue Light</Link>
          <Link className="usa-button usa-button--outline" to="/privacy">Read our privacy policy</Link>
        </div>
      </div>

      <section>
        <h2>What the application does</h2>
        <p>
          Invited users can search active contract opportunities and public entity registrations, save useful records and searches, and receive scheduled opportunity notifications. Search results link back to SAM.gov for authoritative details.
        </p>
      </section>

      <section>
        <h2>How Google sign-in is used</h2>
        <p>
          Google sign-in is optional. GovVue Light requests only basic identity information—your email address and basic profile—to authenticate an account that an administrator has already invited. It does not request access to Gmail, Google Drive, contacts, calendars, or other Google services.
        </p>
      </section>

      <section>
        <h2>Access and data sources</h2>
        <p>
          Access is invitation-only. Opportunity and entity information comes from public SAM.gov APIs and may change after it is displayed. GovVue Light is not affiliated with, endorsed by, or operated by SAM.gov, the General Services Administration, or any other U.S. government agency.
        </p>
      </section>

      <aside className="public-callout">
        <h2>Questions?</h2>
        <p>Email <a href="mailto:admin@govvue.com">admin@govvue.com</a>.</p>
      </aside>
    </article>
  );
}
