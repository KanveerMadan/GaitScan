"""The words of a gait-profile verdict, in English and Hindi (Plan V3 Phase 11, owner decision D4).

General wellness and information: what to do next, never a judgement of the person. No condition is
named, and the words the owner ruled out never appear (the list is in tests/test_gait_profile_api.py,
which scans every string here in both languages). The Hindi is a draft for the
owner to review, like the rest of the app's Hindi (src/i18n/hi.js in the app).
"""

from typing import Any

COPY: dict[str, dict[str, Any]] = {
    "en": {
        "headline": {
            "typical": "Looks typical.",
            "keep_an_eye": "Worth keeping an eye on.",
            "outside": "Outside the typical range.",
        },
        "overall": {
            "typical": "Your walk looks typical for the comparison group.",
            "keep_an_eye": "Slightly outside the typical range — worth re-testing in 2–4 weeks.",
            "outside": "Outside the typical range. If you have concerns about your walking, a physiotherapist can assess it properly.",
        },
        "no_verdict": {
            "too_few_steps": "Not enough steps were measured for an overall summary. The measurements that had enough data are shown.",
            "too_little_steady_walking": "Too little steady walking was measured for an overall summary.",
            "low_confidence": "The legs weren't seen clearly enough for an overall summary.",
        },
        "tips": {
            "walk_more_passes": "Walk across the frame and back two or three times.",
            "whole_body_in_view": "Keep the whole body, feet included, in view all the time.",
            "landscape_waist_height": "Hold the phone in landscape at waist height.",
            "distance": "Stand the phone 3–4 m from the walking line.",
            "steady_pace": "Walk at your usual, steady pace.",
            "camera_still": "Keep the phone still: on a tripod or propped on something.",
        },
        "next_steps": {
            "typical": "Re-test whenever you like to follow changes over time.",
            "keep_an_eye": "Re-test in 2–4 weeks, filmed the same way.",
            "outside": "Re-test in 2–4 weeks, filmed the same way. If you have concerns about your walking, a physiotherapist can assess it properly.",
        },
        "notice": "Experimental estimate from a phone video, not a medical assessment.",
        "disclaimer": "GaitScan is for general wellness and information. It is not a medical device: it does not assess health conditions, and its measurements have not been clinically validated.",
        "level": {"typical": "Typical", "slightly_outside": "Slightly outside", "clearly_outside": "Outside"},
        "direction": {"above": "above", "below": "below"},
        "finding": "{metric} is {direction} the typical range: {value} {unit} (typical {lo}–{hi} {unit}).",
        "fallback": {
            "all_adults": "No age-specific reference for your age; compared with all adults.",
            "no_sex": "No sex-specific reference; compared with adults of your age.",
        },
        "label": {
            "same_method": "compared with healthy adults measured by this app",
            "literature": "compared with a published study of healthy adults (Mobbs et al. 2025)",
            "gps": "compared with healthy adults measured by this app",
        },
        "metric": {
            "cadence": "Cadence",
            "step_time_cv": "Step-time variability",
            "knee_peak_swing": "Knee bend in swing",
            "knee_rom": "Knee range of motion",
            "hip_rom": "Hip range of motion",
            "hip_peak_ext": "Hip extension at push-off",
            "knee_ic": "Knee at heel strike",
            "hip_peak_flex": "Hip flexion in swing",
            "ankle_ic": "Ankle at heel strike",
            "ankle_rom": "Ankle range of motion",
            "trunk_lean_deg": "Trunk lean",
            "arm_swing_deg": "Arm swing",
            "stance_pct": "Stance",
            "swing_pct": "Swing",
            "double_support_pct": "Double support",
        },
        "unit": {"steps/min": "steps/min", "%": "%", "deg": "°"},
        "error": "Error range: about ±{mae}° (a similar video method against motion capture, Stenum et al. 2021).",
        "error_note": {
            "ljmu_thigh_offset": "On healthy test walkers, GaitScan's thigh range read about 9° more than a sensor worn on the thigh, on average. The cause isn't known yet.",
        },
    },
    "hi": {
        "headline": {
            "typical": "सामान्य सीमा में है।",
            "keep_an_eye": "ध्यान रखने लायक।",
            "outside": "सामान्य सीमा से बाहर।",
        },
        "overall": {
            "typical": "तुलना वाले समूह के हिसाब से आपकी चाल सामान्य सीमा में है।",
            "keep_an_eye": "सामान्य सीमा से थोड़ा बाहर — 2–4 हफ़्ते में दोबारा जाँचना अच्छा रहेगा।",
            "outside": "सामान्य सीमा से बाहर। अगर आपको अपनी चाल को लेकर चिंता है, तो एक फ़िज़ियोथेरेपिस्ट इसे ठीक से परख सकते हैं।",
        },
        "no_verdict": {
            "too_few_steps": "कुल सारांश के लिए काफ़ी कदम नहीं मापे गए। जिन मापों के लिए काफ़ी डेटा था, वे दिखाए गए हैं।",
            "too_little_steady_walking": "कुल सारांश के लिए बहुत कम स्थिर चलना मापा गया।",
            "low_confidence": "कुल सारांश के लिए पैर साफ़ नहीं दिखे।",
        },
        "tips": {
            "walk_more_passes": "फ़्रेम के आर-पार दो-तीन बार चलकर आएँ-जाएँ।",
            "whole_body_in_view": "पूरा शरीर, पैरों समेत, हर समय फ़्रेम में रखें।",
            "landscape_waist_height": "फ़ोन को आड़ा, कमर की ऊँचाई पर रखें।",
            "distance": "फ़ोन को चलने की रेखा से 3–4 मीटर दूर रखें।",
            "steady_pace": "अपनी सामान्य, एक-सी चाल से चलें।",
            "camera_still": "फ़ोन को स्थिर रखें: ट्राइपॉड पर या किसी चीज़ के सहारे।",
        },
        "next_steps": {
            "typical": "समय के साथ बदलाव देखने के लिए जब चाहें दोबारा जाँचें।",
            "keep_an_eye": "2–4 हफ़्ते में उसी तरह फ़िल्म करके दोबारा जाँचें।",
            "outside": "2–4 हफ़्ते में उसी तरह फ़िल्म करके दोबारा जाँचें। अगर आपको अपनी चाल को लेकर चिंता है, तो एक फ़िज़ियोथेरेपिस्ट इसे ठीक से परख सकते हैं।",
        },
        "notice": "फ़ोन वीडियो से प्रायोगिक अनुमान, यह चिकित्सकीय आकलन नहीं है।",
        "disclaimer": "GaitScan सामान्य सेहत और जानकारी के लिए है। यह चिकित्सा उपकरण नहीं है: यह स्वास्थ्य स्थितियों का आकलन नहीं करता, और इसके माप चिकित्सकीय रूप से प्रमाणित नहीं हैं।",
        "level": {"typical": "सामान्य", "slightly_outside": "थोड़ा बाहर", "clearly_outside": "बाहर"},
        "direction": {"above": "ऊपर", "below": "नीचे"},
        "finding": "{metric} सामान्य सीमा से {direction} है: {value} {unit} (सामान्य {lo}–{hi} {unit})।",
        "fallback": {
            "all_adults": "आपकी उम्र के लिए अलग तुलना उपलब्ध नहीं; सभी वयस्कों से तुलना की गई।",
            "no_sex": "लिंग के अनुसार तुलना उपलब्ध नहीं; आपकी उम्र के वयस्कों से तुलना की गई।",
        },
        "label": {
            "same_method": "इसी ऐप से मापे गए स्वस्थ वयस्कों से तुलना",
            "literature": "स्वस्थ वयस्कों के एक प्रकाशित अध्ययन से तुलना (Mobbs et al. 2025)",
            "gps": "इसी ऐप से मापे गए स्वस्थ वयस्कों से तुलना",
        },
        "metric": {
            "cadence": "कैडेंस (कदम प्रति मिनट)",
            "step_time_cv": "कदम के समय में अंतर",
            "knee_peak_swing": "झूलते पैर में घुटने का मोड़",
            "knee_rom": "घुटने की गति-सीमा",
            "hip_rom": "कूल्हे की गति-सीमा",
            "hip_peak_ext": "पैर पीछे धकेलते समय कूल्हे का खिंचाव",
            "knee_ic": "एड़ी टिकते समय घुटना",
            "hip_peak_flex": "झूलते पैर में कूल्हे का मोड़",
            "ankle_ic": "एड़ी टिकते समय टखना",
            "ankle_rom": "टखने की गति-सीमा",
            "trunk_lean_deg": "धड़ का झुकाव",
            "arm_swing_deg": "बाँहों का झूलना",
            "stance_pct": "पैर ज़मीन पर",
            "swing_pct": "पैर हवा में",
            "double_support_pct": "दोनों पैर ज़मीन पर",
        },
        "unit": {"steps/min": "कदम/मिनट", "%": "%", "deg": "°"},
        "error": "त्रुटि सीमा: लगभग ±{mae}° (मोशन कैप्चर से तुलना किया गया एक मिलता-जुलता वीडियो तरीका, Stenum et al. 2021)।",
        "error_note": {
            "ljmu_thigh_offset": "स्वस्थ परीक्षण प्रतिभागियों में, GaitScan की जाँघ की गति-सीमा जाँघ पर पहने सेंसर से औसतन लगभग 9° ज़्यादा आई। इसका कारण अभी पता नहीं है।",
        },
    },
}
