"""Turn down pdfminer's running commentary.

Shadowrun PDFs are full of subsetted fonts whose descriptors omit an optional
FontBBox. pdfminer warns once per font per page:

    Could not get FontBBox from font descriptor because
    None cannot be parsed as 4 floats

It then falls back to a default bbox and carries on, and the extracted text is
unaffected -- we do not use glyph bounding boxes for anything. So the warning
reports nothing the user can act on, and there are enough of them to bury the
lines that DO matter in the import log.

Silenced rather than filtered by message text, because pdfminer phrases the
same complaint several ways. Errors still come through: only the noise floor
is raised, and only for pdfminer.
"""
from __future__ import annotations

import logging

#: The loggers that produce the per-font chatter.
NOISY = ("pdfminer", "pdfminer.pdffont", "pdfminer.pdfinterp",
         "pdfminer.pdfdocument", "pdfminer.pdfpage", "pdfplumber")


def quiet_pdf_noise() -> None:
    """Raise pdfminer/pdfplumber to ERROR. Idempotent; safe to call anywhere."""
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.ERROR)
