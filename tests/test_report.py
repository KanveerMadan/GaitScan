"""F20: PDF rendering survives markup characters in any interpolated text."""

from synthetic import synthetic_clip


def test_pdf_survives_markup_characters_in_any_text():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip()[0]).to_dict()
    result["model"]["version"] = "float16/1 <b> & </i>"
    pdf = build_pdf(result, patient_name="A <b>bold</b> & L<R name", created_at=None)
    assert pdf[:4] == b"%PDF"
