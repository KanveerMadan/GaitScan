"""User-facing copy shared by the API and the PDF (wording rules: FUNDAMENTALS_REVIEW 4.3)."""

DISCLAIMER = (
    "GaitScan is an experimental measurement tool, not a medical device. "
    "It does not diagnose conditions or predict outcomes, and its measurements "
    "have not been clinically validated. A qualified clinician should interpret them."
)

LEGACY_NOTE = (
    "This recording was analysed with an earlier version of GaitScan whose measurements were not "
    "reliable, so they are no longer shown. Record a new video to get current measurements."
)

ERROR_RANGES = (
    "Error range: in an accuracy check on side-view walks from a public dataset (LJMU, Topham et al. "
    "2023, CC BY 4.0), 95% of measurements were within this much of the reference. Values are from "
    "one side-view video of one person and depend on following the recording guidance."
)

# Consent before the first analysis (ADR-007). Changing the text means a new version: accounts then
# consent again before their next analysis.
CONSENT_VERSION = "2026-10-27"
CONSENT_TEXT = (
    "Before you analyse a video, please confirm:\n"
    "- I am 18 or older, and I am the person in the videos I upload, or I have that adult's permission.\n"
    "- GaitScan reads the video to measure how I walk. The video is deleted as soon as the analysis "
    "ends; the measurements are kept in my account until I delete them.\n"
    "- Only clinicians I choose to link with can see my results.\n"
    "- I can withdraw this consent, export my data, or delete sessions or my whole account at any time "
    "in Privacy.\n"
    f"- {DISCLAIMER}"
)
