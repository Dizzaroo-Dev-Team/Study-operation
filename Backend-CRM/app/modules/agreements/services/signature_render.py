"""
signature_render.py — ONE reusable signature-manifestation service. Factors out the
"render the signer's name to a signature PNG, then stamp it onto the PDF" logic that
the unified signing module had inline, so it is shared and consistent. Wraps the
EXISTING helpers — no new rendering/stamping logic, no behavior change to signing:
  * utils/signature_image.render_signature_png_bytes — typed name -> signature PNG
  * utils/pdf_export.embed_signature_into_pdf       — overlay PNG + name/title on PDF
This is what makes typed-name signers get a visible block on the final artifact
(the §11.50 fix), now in one place.
"""
from __future__ import annotations

import base64
from typing import Optional


async def stamp_on_pdf(pdf_path: str, signer_name: str, signer_title: Optional[str] = None,
                       page_num: int = -1, *, role: Optional[str] = None,
                       stack_offset: int = 0, signed_on: Optional[str] = None) -> str:
    """Render `signer_name` as a signature image and stamp it (with title) onto the
    PDF. Returns the produced (`_signed`) PDF path. Reuses the proven helpers.

    When `role` is given, the mark is placed at that role's labeled signature line
    (site signers in the 'For Site' block, sponsor in 'For Sponsor'), stacking by
    `stack_offset` when several signers share a block; `signed_on` is the date shown
    beside the mark. With `role=None` the legacy fixed-corner placement is kept —
    so CTA/CDA callers are unaffected."""
    from app.utils.signature_image import render_signature_png_bytes
    from app.modules.agreements.utils.pdf_export import embed_signature_into_pdf

    png_b64 = base64.b64encode(render_signature_png_bytes(signer_name)).decode("ascii")
    return await embed_signature_into_pdf(
        pdf_path, png_b64, signer_name, signer_title or "", page_num,
        role=role, stack_offset=stack_offset, signed_on=signed_on,
    )
