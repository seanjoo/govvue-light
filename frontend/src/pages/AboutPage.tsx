import { Link } from 'react-router-dom';

export default function AboutPage() {
  return (
    <article className="public-content public-landing">
      <div className="public-hero">
        <p className="page-kicker">Private federal market research</p>
        <h1>GovVue Light</h1>
        <p className="public-hero__lead">
          GovVue Light helps a small group of invited users search, review, and organize public federal contracting information from SAM.gov.
        </p>
        <div className="public-actions">
          <Link className="usa-button" to="/login">Sign in to GovVue Light</Link>
          <Link className="usa-button usa-button--outline" to="/privacy">Read our privacy policy</Link>
        </div>
      </div>
    </article>
  );
}
