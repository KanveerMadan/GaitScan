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


def test_pdf_shows_the_result_notes():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse
    from gaitcore.result import LEGS_NOT_TOLD_APART

    result = analyse(synthetic_clip()[0]).to_dict()
    result["notes"] = [LEGS_NOT_TOLD_APART]
    pdf = build_pdf(result, patient_name="Anonymous", created_at=None)
    text = " ".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "couldn't be told apart reliably" in text


def test_pdf_never_shows_stride_time_even_from_an_older_stored_result():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip()[0]).to_dict()
    result["metrics"]["stride_time"] = {
        "left": {"value": 1.1, "sd": 0.01, "n": 3, "unit": "s"},
        "right": None,
    }
    pdf = build_pdf(result, patient_name="Anonymous", created_at=None)
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Cadence" in text
    assert "stride time" not in text.lower()


def test_pdf_marks_knee_flexion_not_yet_validated():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    pdf = build_pdf(analyse(synthetic_clip()[0]).to_dict(), patient_name="Anonymous", created_at=None)
    text = " ".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Not yet validated" in text.split("Peak knee flexion")[1][:200]


def test_pdf_marks_older_stored_knee_values_not_yet_validated():
    """Results stored before the accuracy block existed still get the label."""
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip()[0]).to_dict()
    del result["accuracy"]
    pdf = build_pdf(result, patient_name="Anonymous", created_at=None)
    text = " ".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Not yet validated" in text.split("Peak knee flexion")[1][:200]


def test_pdf_shows_each_pass_and_the_spread_between_passes():
    from app.services.report_pdf import build_pdf
    from gaitcore.pipeline import analyse

    result = analyse(synthetic_clip(passes=3, pass_secs=6.0, width=2000)[0]).to_dict()
    pdf = build_pdf(result, patient_name="Anonymous", created_at=None)
    text = " ".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Each pass" in text and "left to right" in text and "right to left" in text
    sd = result["pass_variability"]["cadence_sd"]["value"]
    assert f"Spread between passes (SD): cadence {sd} steps/min" in text


def test_pdf_shows_the_error_range_next_to_each_validated_metric():
    from app.services.report_pdf import build_pdf
    from gaitcore.accuracy import VALIDATED
    from gaitcore.pipeline import analyse

    pdf = build_pdf(analyse(synthetic_clip()[0]).to_dict(), patient_name="Anonymous", created_at=None)
    text = " ".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert f"± {VALIDATED['cadence']['error_95']} steps/min" in text.split("Cadence")[1][:200]
    assert f"± {VALIDATED['step_time']['error_95']} s" in text.split("Step time")[1][:200]
    assert "have not been measured yet" not in text
