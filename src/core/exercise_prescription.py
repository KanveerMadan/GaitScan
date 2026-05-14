from groq import Groq
import json

EXERCISE_KNOWLEDGE_BASE = [
    {
        "id": 1,
        "name": "Single-leg squat",
        "targets": ["knee_asymmetry", "knee_weakness", "balance"],
        "muscle": "Quadriceps, glutes",
        "activity_relevance": ["Walking", "Brisk Walking", "Running", "Limping"],
        "mode_relevance": ["Clinical", "Runner", "Athlete", "Elderly"],
        "instructions": "Stand on one leg, slowly bend the knee to 45°, hold 2 seconds, return. 3 sets of 10 reps each side.",
        "difficulty": "Moderate"
    },
    {
        "id": 2,
        "name": "Hip abductor strengthening",
        "targets": ["hip_asymmetry", "knee_asymmetry", "limp"],
        "muscle": "Gluteus medius",
        "activity_relevance": ["Walking", "Brisk Walking", "Limping"],
        "mode_relevance": ["Clinical", "Runner", "Athlete", "Elderly"],
        "instructions": "Lie on your side, lift the top leg to 45°, hold 3 seconds, lower slowly. 3 sets of 15 reps each side.",
        "difficulty": "Easy"
    },
    {
        "id": 3,
        "name": "Heel-to-toe walking drill",
        "targets": ["low_cadence", "balance", "stride_irregularity"],
        "muscle": "Tibialis anterior, calves",
        "activity_relevance": ["Walking", "Brisk Walking", "Limping"],
        "mode_relevance": ["Clinical", "Elderly"],
        "instructions": "Walk in a straight line placing heel directly in front of opposite toe with each step. 2 sets of 20 steps.",
        "difficulty": "Easy"
    },
    {
        "id": 4,
        "name": "High knees drill",
        "targets": ["low_knee_flexion", "running_efficiency", "low_cadence"],
        "muscle": "Hip flexors, quadriceps",
        "activity_relevance": ["Running", "Brisk Walking"],
        "mode_relevance": ["Clinical", "Runner", "Athlete"],
        "instructions": "March in place driving knees up to hip height alternately. Start slow, build speed. 3 sets of 30 seconds.",
        "difficulty": "Moderate"
    },
    {
        "id": 5,
        "name": "Glute bridge",
        "targets": ["hip_asymmetry", "hip_weakness", "limp"],
        "muscle": "Gluteus maximus, hamstrings",
        "activity_relevance": ["Walking", "Running", "Limping", "Brisk Walking"],
        "mode_relevance": ["Clinical", "Runner", "Athlete", "Elderly"],
        "instructions": "Lie on back, feet flat, push hips up until body is straight, hold 3 seconds. 3 sets of 12 reps.",
        "difficulty": "Easy"
    },
    {
        "id": 6,
        "name": "Lateral band walks",
        "targets": ["knee_asymmetry", "hip_asymmetry", "knee_valgus"],
        "muscle": "Gluteus medius, hip abductors",
        "activity_relevance": ["Walking", "Running", "Brisk Walking"],
        "mode_relevance": ["Clinical", "Runner", "Athlete"],
        "instructions": "Place resistance band above knees, feet shoulder-width, bend slightly and walk sideways 15 steps each direction. 3 sets.",
        "difficulty": "Moderate"
    },
    {
        "id": 7,
        "name": "Calf raises",
        "targets": ["low_cadence", "stride_irregularity", "walking_efficiency"],
        "muscle": "Gastrocnemius, soleus",
        "activity_relevance": ["Walking", "Brisk Walking", "Running"],
        "mode_relevance": ["Clinical", "Runner", "Athlete", "Elderly"],
        "instructions": "Stand at edge of step, lower heel below step level, raise up on toes. 3 sets of 20 reps.",
        "difficulty": "Easy"
    },
    {
        "id": 8,
        "name": "Step-ups",
        "targets": ["knee_asymmetry", "knee_weakness", "limp"],
        "muscle": "Quadriceps, glutes",
        "activity_relevance": ["Walking", "Limping", "Brisk Walking"],
        "mode_relevance": ["Clinical", "Elderly"],
        "instructions": "Step up onto a sturdy box or step, drive through the heel, fully extend, step back down. 3 sets of 10 each leg.",
        "difficulty": "Moderate"
    },
    {
        "id": 9,
        "name": "Running cadence drills",
        "targets": ["running_efficiency", "overstriding", "low_cadence"],
        "muscle": "Full lower body",
        "activity_relevance": ["Running"],
        "mode_relevance": ["Runner", "Athlete"],
        "instructions": "Run at easy pace focusing on quick light steps. Use a metronome app set to 170 BPM. 5 minute intervals.",
        "difficulty": "Moderate"
    },
    {
        "id": 10,
        "name": "Hip flexor stretch",
        "targets": ["hip_asymmetry", "anterior_pelvic_tilt", "hip_tightness"],
        "muscle": "Iliopsoas, rectus femoris",
        "activity_relevance": ["Walking", "Running", "Brisk Walking", "Limping"],
        "mode_relevance": ["Clinical", "Runner", "Athlete", "Elderly"],
        "instructions": "Kneel on one knee, push hips forward gently until stretch felt in front of hip. Hold 30 seconds each side. 3 reps.",
        "difficulty": "Easy"
    },
    {
        "id": 11,
        "name": "Knee mobility circles",
        "targets": ["low_knee_flexion", "knee_stiffness", "limited_range"],
        "muscle": "Knee joint, surrounding tissue",
        "activity_relevance": ["Walking", "Limping", "Brisk Walking"],
        "mode_relevance": ["Clinical", "Elderly"],
        "instructions": "Stand feet together, hands on knees, make gentle circles with both knees. 10 clockwise, 10 anticlockwise. 2 sets.",
        "difficulty": "Easy"
    },
    {
        "id": 12,
        "name": "Single-leg deadlift",
        "targets": ["balance", "hip_asymmetry", "stride_irregularity"],
        "muscle": "Hamstrings, glutes, core",
        "activity_relevance": ["Walking", "Running", "Brisk Walking"],
        "mode_relevance": ["Clinical", "Runner", "Athlete"],
        "instructions": "Stand on one leg, hinge forward at hip lowering hands toward floor, keep back straight. 3 sets of 8 each side.",
        "difficulty": "Hard"
    },
    # ── Runner-specific ───────────────────────────────────────
    {
        "id": 13,
        "name": "A-skip drill",
        "targets": ["running_efficiency", "low_knee_flexion", "low_cadence"],
        "muscle": "Hip flexors, calves, quads",
        "activity_relevance": ["Running", "Brisk Walking"],
        "mode_relevance": ["Runner", "Athlete"],
        "instructions": "Skip forward driving one knee up to hip height while pushing off the opposite toe. 3 sets of 20m each side.",
        "difficulty": "Moderate"
    },
    {
        "id": 14,
        "name": "Strides (acceleration runs)",
        "targets": ["running_efficiency", "low_cadence", "overstriding"],
        "muscle": "Full lower body",
        "activity_relevance": ["Running"],
        "mode_relevance": ["Runner", "Athlete"],
        "instructions": "Run 80–100m gradually accelerating to 85% max effort, then decelerate. Focus on quick turnover. 4–6 reps.",
        "difficulty": "Hard"
    },
    {
        "id": 15,
        "name": "Plyometric box jumps",
        "targets": ["knee_asymmetry", "running_efficiency", "balance"],
        "muscle": "Quads, glutes, calves",
        "activity_relevance": ["Running"],
        "mode_relevance": ["Athlete"],
        "instructions": "Stand in front of a box, jump up landing softly with both feet, step down. 4 sets of 8 reps. Land quietly.",
        "difficulty": "Hard"
    },
    {
        "id": 16,
        "name": "Copenhagen adductor plank",
        "targets": ["hip_asymmetry", "knee_asymmetry", "knee_valgus"],
        "muscle": "Adductors, hip stabilisers",
        "activity_relevance": ["Running", "Brisk Walking"],
        "mode_relevance": ["Athlete", "Runner"],
        "instructions": "Side plank with top foot on a bench. Hold body straight. 3 sets of 20–30 seconds each side.",
        "difficulty": "Hard"
    },
    # ── Elderly-specific ──────────────────────────────────────
    {
        "id": 17,
        "name": "Seated leg raises",
        "targets": ["knee_weakness", "low_knee_flexion", "balance"],
        "muscle": "Quadriceps",
        "activity_relevance": ["Walking", "Limping"],
        "mode_relevance": ["Elderly"],
        "instructions": "Sit in a chair, straighten one leg holding 5 seconds, lower slowly. 3 sets of 12 reps each leg.",
        "difficulty": "Easy"
    },
    {
        "id": 18,
        "name": "Chair stand (sit-to-stand)",
        "targets": ["knee_weakness", "balance", "limp"],
        "muscle": "Quadriceps, glutes",
        "activity_relevance": ["Walking", "Limping"],
        "mode_relevance": ["Elderly"],
        "instructions": "From seated, stand up without using hands. Lower back slowly. 3 sets of 10 reps. Use hands only if needed for safety.",
        "difficulty": "Easy"
    },
    {
        "id": 19,
        "name": "Tandem stance balance hold",
        "targets": ["balance", "stride_irregularity", "limp"],
        "muscle": "Ankle stabilisers, core",
        "activity_relevance": ["Walking", "Limping"],
        "mode_relevance": ["Elderly"],
        "instructions": "Stand with one foot directly in front of the other (heel to toe). Hold 30 seconds. Repeat 3 times each side. Use a wall nearby for safety.",
        "difficulty": "Easy"
    },
]


def _match_exercises(findings, activity, mode):
    """Match exercises to findings based on tags, activity, and mode."""
    matched = []
    seen_ids = set()

    tag_map = {
        "knee_symmetry": ["knee_asymmetry", "knee_weakness"],
        "hip_symmetry":  ["hip_asymmetry", "hip_weakness"],
        "knee_flexion":  ["low_knee_flexion", "knee_stiffness", "limited_range"],
        "knee_drive":    ["low_knee_flexion", "running_efficiency"],
        "cadence":       ["low_cadence", "walking_efficiency", "running_efficiency"],
        "limp":          ["limp", "stride_irregularity", "balance"],
        "affected_side": ["limp", "balance", "stride_irregularity"],
    }

    for finding in findings:
        if finding.get("status") in ("mild", "flagged"):
            metric = finding.get("metric", "").lower().replace(" ", "_")
            tags = []
            for key, tag_list in tag_map.items():
                if key in metric:
                    tags.extend(tag_list)

            if activity == "Limping":
                tags.extend(["limp", "balance", "stride_irregularity"])
            if activity == "Running":
                tags.extend(["running_efficiency"])

            for exercise in EXERCISE_KNOWLEDGE_BASE:
                if exercise["id"] in seen_ids:
                    continue
                # Must be relevant to both activity AND mode
                if (activity in exercise["activity_relevance"]
                        and mode in exercise["mode_relevance"]):
                    if any(tag in exercise["targets"] for tag in tags):
                        matched.append(exercise)
                        seen_ids.add(exercise["id"])

    # Pad to at least 2 exercises from the same mode
    if len(matched) < 2:
        for exercise in EXERCISE_KNOWLEDGE_BASE:
            if exercise["id"] not in seen_ids and mode in exercise["mode_relevance"]:
                if activity in exercise["activity_relevance"]:
                    matched.append(exercise)
                    seen_ids.add(exercise["id"])
            if len(matched) >= 3:
                break

    return matched[:5]


def get_exercise_prescription(findings, activity, scores, risk_label, mode="Clinical"):
    """
    Match exercises to findings and use Groq/Llama to write
    personalised explanations for each one. Mode-aware.
    """
    matched_exercises = _match_exercises(findings, activity, mode)

    if not matched_exercises:
        return []

    flagged = [f for f in findings if f.get("status") in ("mild", "flagged")]
    findings_summary = "\n".join([
        f"- {f['metric']}: {f['value']} — {f['plain_english']}"
        for f in flagged
    ]) if flagged else "- No significant issues detected, but general conditioning recommended"

    exercises_list = "\n".join([
        f"{i+1}. {ex['name']} (targets: {', '.join(ex['targets'][:2])})"
        for i, ex in enumerate(matched_exercises)
    ])

    mode_context = {
        "Clinical":  "standard physiotherapy patient",
        "Runner":    "recreational or competitive runner focused on performance and injury prevention",
        "Athlete":   "high-performance athlete optimising for peak biomechanical efficiency",
        "Elderly":   "older adult prioritising fall prevention, stability, and safe movement",
    }.get(mode, "standard physiotherapy patient")

    prompt = f"""You are a physiotherapist writing exercise recommendations for a {mode_context}.

Patient gait analysis results:
- Activity: {activity}
- Analysis mode: {mode}
- Risk level: {risk_label}
- Findings:
{findings_summary}

Recommended exercises:
{exercises_list}

For each exercise, write a single clear sentence (max 25 words) explaining WHY this specific exercise helps THIS patient based on their findings and their profile as a {mode_context}. Be direct and personal — say "your" not "the patient's". Do not mention the exercise name in the explanation. Return as a JSON array only, no other text:

[
  {{"exercise_number": 1, "why": "..."}},
  {{"exercise_number": 2, "why": "..."}},
  ...
]"""

    try:
        client = Groq()
        message = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        explanations = json.loads(raw.strip())
        why_map = {item["exercise_number"]: item["why"] for item in explanations}
    except Exception as e:
        print(f"Groq API error: {e}")
        why_map = {}

    result = []
    for i, ex in enumerate(matched_exercises):
        result.append({
            "name":         ex["name"],
            "muscle":       ex["muscle"],
            "difficulty":   ex["difficulty"],
            "instructions": ex["instructions"],
            "why":          why_map.get(i + 1, f"Helps address the gait issues detected in your {activity.lower()} pattern.")
        })

    return result