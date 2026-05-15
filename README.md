# GaitScan — Backend

AI-powered gait and posture analysis API built with FastAPI and MediaPipe.

## What it does
- Accepts walking/running/CCTV video uploads
- Extracts 33 body landmarks per frame via MediaPipe
- Classifies activity (Walking / Brisk Walking / Running / Limping)
- Calculates knee/hip symmetry, flexion range, cadence
- Scores gait risk 0–100 with plain English findings
- Recommends corrective exercises via Groq/Llama RAG pipeline
- Generates downloadable PDF reports
- Multi-user auth (JWT), clinician dashboard, progress tracking

## Tech Stack
FastAPI · MediaPipe · OpenCV · SQLAlchemy · PostgreSQL · Groq API · ReportLab

## Live API
https://gaitscan.onrender.com

## Endpoints
POST /analyze — upload video, get full analysis
GET  /report/{job_id} — download PDF report
GET  /sessions — session history
POST /auth/register, /auth/login
GET  /clinician/patients
