"""F20: PDF rendering survives markup characters in any interpolated text."""

import io

from pypdf import PdfReader
from synthetic import synthetic_clip


def test_pdf_survives_markup_characters_in_any_text():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip()[0]).to_dict()
    result["model"]["version"] = "float16/1 <b> & </i>"
    pdf = build_pdf(result, patient_name="A <b>bold</b> & L<R name", created_at=None)
    assert pdf[:4] == b"%PDF"


def test_pdf_never_shows_hip_excursion_even_from_an_older_stored_result():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip()[0]).to_dict()
    result["metrics"]["hip_sagittal_excursion"] = {"left": {"value": 40.2, "sd": 1.0, "n": 3, "unit": "deg"}}
    pdf = build_pdf(result, patient_name="Anonymous", created_at=None)
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Cadence" in text
    assert "hip" not in text.lower()
