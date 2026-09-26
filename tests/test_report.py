"""F19, F20: PDF rendering robustness."""
import os
import subprocess
import sys

from conftest import ROOT

BASE = {
    "scores": {"overall_risk_score": 0, "knee_symmetry_index": 1.0, "hip_symmetry_index": 1.0,
               "knee_flexion_range_L": 60.0, "knee_flexion_range_R": 60.0, "cadence": 100.0},
    "findings": [{"metric": "Knee <Symmetry>", "value": "1% & <2%", "status": "good",
                  "plain_english": "L<R & R>L"}],
    "recommendations": ["Balance <both> sides & more"],
    "activity": {"activity": "Walking", "confidence": 70},
    "risk_label": "x", "risk_meaning": "x",
}


def test_pdf_survives_markup_characters_in_any_text(tmp_path):
    from src.core.report_generator import generate_pdf_report
    data = dict(BASE, exercises=[{"name": "Bridge <1>", "muscle": "a&b", "difficulty": "Easy",
                                  "instructions": "Hold <3 s>", "why": "Keeps your L<R imbalance in check"}])
    out = tmp_path / "r.pdf"
    generate_pdf_report(data, output_path=str(out), plots_dir=str(tmp_path))
    assert out.read_bytes()[:4] == b"%PDF"


def test_plotting_module_selects_agg_backend_itself():
    env = {k: v for k, v in os.environ.items() if k != "MPLBACKEND"}
    r = subprocess.run([sys.executable, "-c",
                        "import src.utils.visualise, matplotlib; print(matplotlib.get_backend())"],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    assert r.stdout.strip().lower() == "agg"
