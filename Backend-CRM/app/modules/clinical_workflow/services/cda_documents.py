"""CDA document HTML generation + filesystem path resolution.

These helpers are called by the workflow_steps POST endpoint when the
CDA-execution step transitions to SENT / SIGNED. They build the HTML body
that gets emailed for signature and compute the on-disk path where the
final signed PDF / DOCX lands.

Pure functions, no DB access.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from app.config import settings


def generate_cda_document_html(
    study_name: str,
    site_name: str,
    cda_template: str,
    step_data: dict,
    site_signer_name: Optional[str] = None,
    site_signer_title: Optional[str] = None,
    site_signed_at: Optional[str] = None,
) -> str:
    """
    Generate CDA document HTML at any stage (draft, internally signed, fully signed).
    Uses the actual CDA template and injects signatures into placeholder lines.
    """
    from datetime import datetime
    
    internal_signer_name = step_data.get('internal_signer_name', '')
    internal_signer_title = step_data.get('internal_signer_title', '')
    internal_signed_at = step_data.get('internal_signed_at', '')
    cda_status = step_data.get('cda_status', 'draft')
    
    # Format dates for display
    def format_date(date_str):
        if not date_str:
            return ''
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%B %d, %Y')
        except:
            return date_str
    
    # Format signature line - show value if signed, otherwise show empty line
    def format_signature_line(value):
        if value:
            return f'<div class="signature-line"><strong>{value}</strong></div>'
        else:
            return '<div class="signature-line"></div>'
    
    # Get current date for the document
    current_date = datetime.now().strftime('%B %d, %Y')
    
    # Format internal signature date
    internal_date = format_date(internal_signed_at) if internal_signed_at else ''
    
    # Format external signature date
    external_date = format_date(site_signed_at) if site_signed_at else ''
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Confidential Disclosure Agreement (CDA) - {study_name} - {site_name}</title>

  <style>
    body {{
      font-family: "Aptos", "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.6;
      color: #000;
      margin: 40px;
    }}

    h1, h2 {{
      font-family: "Aptos Display", "Segoe UI", sans-serif;
      font-weight: normal;
      color: #0f4761;
      page-break-after: avoid;
      page-break-inside: avoid;
    }}

    h1 {{
      font-size: 20pt;
      margin: 18pt 0 6pt;
    }}

    h2 {{
      font-size: 16pt;
      margin: 16pt 0 6pt;
    }}

    p {{
      margin: 8pt 0;
    }}

    hr {{
      border: none;
      border-top: 2px solid #ddd;
      margin: 14pt 0;
    }}

    ul {{
      margin-left: 28pt;
    }}

    ul li {{
      margin: 4pt 0;
    }}

    /* Alphabetical lists: a), b), c) */
    .alpha-list {{
      list-style: none;
      counter-reset: alpha;
      padding-left: 0;
      margin-left: 28pt;
    }}

    .alpha-list > li {{
      counter-increment: alpha;
      position: relative;
      padding-left: 22pt;
      margin: 6pt 0;
    }}

    .alpha-list > li::before {{
      content: counter(alpha, lower-latin) ")";
      position: absolute;
      left: 0;
    }}

    .logo {{
      margin-bottom: 14pt;
    }}

    .signature-block {{
      margin-top: 18pt;
    }}

    .signature-line {{
      margin: 6pt 0;
      border-bottom: 1px solid #000;
      min-height: 20px;
      padding-bottom: 2px;
    }}

    .signature-filled {{
      margin: 6pt 0;
      border-bottom: 1px solid #000;
      min-height: 20px;
      padding-bottom: 2px;
    }}

    .footer {{
      margin-top: 30pt;
      font-size: 11px;
      color: #555;
    }}
  </style>
</head>

<body>

  <!-- LOGO -->
  <div class="logo">
    <img src="data:image/png;base64,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"
         alt="Dizzaroo Logo">
  </div>

  <h1>Confidential Disclosure Agreement (CDA)</h1>
  <p><strong>(Mutual – Plain-English Version)</strong></p>

  <p><strong>Study:</strong> {study_name}</p>
  <p>This Agreement is between:</p>

  <p>
    <strong>Dizzaroo Private Limited</strong><br>
    SR NO 3112, Speciality Business Center, B-211, Baner Gaon,<br>
    Pune, Maharashtra, India, 411045 ("Dizzaroo")
  </p>

  <p><strong>and</strong></p>

  <p>
    <strong>{site_name}</strong><br>
    ("Site")
  </p>

  <p>Dizzaroo and the Site are together called "the parties".</p>

  <p><strong>Date:</strong> {current_date}</p>
  <hr>

  <h2>1. Purpose</h2>
  <p>
    The parties want to share confidential information with each other to explore and evaluate
    a potential working relationship, collaboration, project, service arrangement, or any
    related business discussion (the <strong>"Purpose"</strong>).
  </p>
  <hr>

  <h2>2. Confidential Information</h2>
  <p>
    "Confidential Information" means any non-public information one party ("Disclosing Party")
    shares with the other ("Receiving Party"), in any form, including:
  </p>
  <ul>
    <li>technical information, software, models, algorithms, research, designs;</li>
    <li>business plans, strategies, forecasts, pricing, and financials;</li>
    <li>customer, partner, or supplier information;</li>
    <li>presentations, documents, reports, data, analyses, or summaries;</li>
    <li>any notes or copies based on the above.</li>
  </ul>
  <hr>

  <h2>3. What is not Confidential Information</h2>
  <p>Information is not considered Confidential Information if the Receiving Party can show that:</p>
  <ol class="alpha-list">
    <li>it was already public when received;</li>
    <li>it became public later without breaking this Agreement;</li>
    <li>it was already in the Receiving Party's possession legally;</li>
    <li>it was received from someone authorised to share it; or</li>
    <li>it was developed independently.</li>
  </ol>
  <hr>

  <h2>4. Obligations of the Receiving Party</h2>
  <ol class="alpha-list">
    <li>use Confidential Information only for the Purpose;</li>
    <li>
      not share it except with people who need to know and are bound to confidentiality;
    </li>
    <li>
      protect the information with reasonable care;
    </li>
    <li>
      immediately notify of unauthorised use or disclosure.
    </li>
  </ol>
  <hr>

  <h2>5. Disclosures required by law</h2>
  <ol class="alpha-list">
    <li>notify the Disclosing Party as soon as legally allowed; and</li>
    <li>share only the minimum information required.</li>
  </ol>
  <hr>

  <h2>6. Ownership</h2>
  <p>
    Confidential Information remains the property of the Disclosing Party. Nothing grants
    ownership or licence rights beyond the Purpose.
  </p>
  <hr>

  <h2>7. Term and confidentiality duration</h2>
  <p>This Agreement begins on the Date above.</p>
  <p>
    Confidentiality obligations continue for <strong>five (5) years</strong> after last disclosure.
  </p>
  <hr>

  <h2>8. Return or destruction of information</h2>
  <ol class="alpha-list">
    <li>return or destroy Confidential Information; and</li>
    <li>confirm in writing that this has been done.</li>
  </ol>
  <p>Except where retention is legally required.</p>
  <hr>

  <h2>9. Breach and remedies</h2>
  <p>
    Unauthorised disclosure may cause serious harm. Remedies include injunctions and damages.
  </p>
  <hr>

  <h2>10. Governing law and jurisdiction</h2>
  <p>This Agreement is governed by the laws of <strong>India</strong>.</p>
  <p>Courts of <strong>Pune, Maharashtra</strong> have jurisdiction.</p>
  <hr>

  <h2>11. General</h2>
  <ol class="alpha-list">
    <li>This Agreement is the complete agreement.</li>
    <li>Changes must be in writing and signed.</li>
    <li>Invalid provisions do not affect the rest.</li>
  </ol>
  <hr>

  <h2>Signatures</h2>

  <div class="signature-block">
    <p><strong>For Dizzaroo Private Limited</strong></p>
    <div class="signature-line">Name: {internal_signer_name if internal_signer_name else ''}</div>
    <div class="signature-line">Title: {internal_signer_title if internal_signer_title else ''}</div>
    <div class="signature-line">Signature: {'✓ Electronically Signed' if internal_signer_name else ''}</div>
    <div class="signature-line">Date: {internal_date if internal_date else ''}</div>
  </div>

  <div class="signature-block">
    <p><strong>For {site_name}</strong></p>
    <div class="signature-line">Name: {site_signer_name if site_signer_name else ''}</div>
    <div class="signature-line">Title: {site_signer_title if site_signer_title else ''}</div>
    <div class="signature-line">Signature: {'✓ Electronically Signed' if site_signer_name else ''}</div>
    <div class="signature-line">Date: {external_date if external_date else ''}</div>
  </div>

  <div class="footer">
    Speciality Business Center, B-211, Baner – Balewadi Rd, Pune – 411045<br>
    www.dizzaroo.com
  </div>

</body>
</html>"""
    
    return html_content


def get_cda_document_path(study_site_id: Optional[UUID], site_id: UUID, study_name: str, site_name: str):
    """
    Get the file path for a CDA document. Returns the same path for a given study-site combination.
    This ensures we update the same document file rather than creating new ones.
    """
    upload_dir = Path(settings.upload_dir)
    if not upload_dir.is_absolute():
        import pathlib
        app_dir = pathlib.Path(__file__).parent.parent
        upload_dir = app_dir / upload_dir
    
    cda_dir = upload_dir / "cda_snapshots"
    cda_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a deterministic filename based on study-site combination
    if study_site_id:
        file_id = str(study_site_id)
    else:
        # For site-level CDA, use site_id
        file_id = str(site_id)
    
    # Sanitize names for filename
    safe_study = "".join(c for c in study_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
    safe_site = "".join(c for c in site_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
    
    html_file_path = cda_dir / f"{file_id}_{safe_study}_{safe_site}.html"
    file_id_for_url = html_file_path.stem  # Use filename without extension for URL
    
    return html_file_path, file_id_for_url


