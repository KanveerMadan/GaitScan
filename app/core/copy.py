"""User-facing copy shared by the API and the PDF (wording rules: FUNDAMENTALS_REVIEW 4.3)."""

# Owner decision D4 (2026-11-13): general wellness and information; "not a medical device" stays; no
# screening, detection or referral language. The same words as the verdict's disclaimer
# (app/core/verdict_copy.py), so the app, the PDFs and the README agree.
DISCLAIMER = (
    "GaitScan is for general wellness and information. It is an experimental measurement tool, not a "
    "medical device: it does not assess health conditions or predict outcomes, and its measurements "
    "have not been clinically validated."
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
CONSENT_VERSION = "2026-11-01"
CONSENT_TEXT = (
    "Before you analyse a video, please confirm:\n"
    "- I am 18 or older, and I am the person in the videos I upload, or I have that adult's permission.\n"
    "- GaitScan reads the video to measure how I walk. The video is deleted as soon as the analysis "
    "ends; the measurements are kept in my account until I delete them.\n"
    "- To compare my walks, GaitScan also keeps an outline of one average stride: the positions of the "
    "hips, knees, ankles, heels and toes, scaled to my leg length. Never the video or my face.\n"
    "- Only clinicians I choose to link with can see my results.\n"
    "- I can withdraw this consent, export my data, or delete sessions or my whole account at any time "
    "in Privacy.\n"
    f"- {DISCLAIMER}"
)
