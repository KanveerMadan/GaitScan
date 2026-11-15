"""README screenshot of the PDF report's first page (docs/images/report-page-1.png), at 2x (144 dpi).

Built from the synthetic walker the tests use (tests/synthetic.py), so there's no real user data: the
same walker as the frontend's e2e mock data. Run:
    ENV=dev PYTHONPATH=.:tests uv run --with pypdfium2 python tools/readme_pdf_page.py [out.png]
"""

import sys
from datetime import datetime

import pypdfium2 as pdfium
from synthetic import synthetic_clip

from app.services.report_full import build_report
from gaitcore.pipeline import analyse


def main(out: str = "docs/images/report-page-1.png") -> None:
    result = analyse(synthetic_clip(passes=3, pass_secs=6.0, width=2000, swing_profile="brisk")[0]).to_dict()
    pdf = build_report(
        result,
        patient_name="Example walker",
        created_at=datetime(2026, 11, 14, 9, 30),
        lang="en",
        person=None,
        report_id="00000000-0000-4000-8000-000000000001",
        session_number=1,
    )
    page = pdfium.PdfDocument(pdf)[0]
    page.render(scale=2).to_pil().save(out)
    print(out)  # noqa: T201  (a command-line tool)


if __name__ == "__main__":
    main(*sys.argv[1:])
