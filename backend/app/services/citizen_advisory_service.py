"""Citizen health advisories with English / Hindi / Kannada content.

Structure
---------
- Risk-band templates per language: headline, recommendations, caution_note
- Profile modifiers (child, elderly, …) per language
- Localized medical disclaimers and helper notes

Technical tokens (PM2.5, confidence level labels High/Medium/Low) stay in English
where they are categorical system values; explanatory prose is localized.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.config import (
    ADVISORY_PROFILES,
    MEDICAL_DISCLAIMER,
    PM25_RISK_THRESHOLDS,
    SUPPORTED_LANGUAGES,
)
from backend.app.services.artifact_adapter import (
    MissingArtifactError,
    NoValidForecastError,
    UnknownStationError,
    UnsupportedCityError,
    get_station_snapshot,
)
from backend.app.services.confidence_service import get_forecast_confidence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Medical disclaimers
# ---------------------------------------------------------------------------
MEDICAL_DISCLAIMER_BY_LANG: dict[str, str] = {
    "en": MEDICAL_DISCLAIMER,
    "hi": (
        "यह सामान्य वायु-गुणवत्ता संबंधी मार्गदर्शन है, चिकित्सा सलाह नहीं है। "
        "गंभीर लक्षण होने पर चिकित्सक से संपर्क करें।"
    ),
    "kn": (
        "ಇದು ಸಾಮಾನ್ಯ ಗಾಳಿ-ಗುಣಮಟ್ಟ ಮಾರ್ಗದರ್ಶನ; ವೈದ್ಯಕೀಯ ಸಲಹೆ ಅಲ್ಲ. "
        "ಗಂಭೀರ ಲಕ್ಷಣಗಳಿದ್ದರೆ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ."
    ),
}

# ---------------------------------------------------------------------------
# Risk-band advisories (general)
# ---------------------------------------------------------------------------
_ADVISORY_EN: dict[str, dict[str, str | list[str]]] = {
    "Good": {
        "headline": "Air quality is satisfactory.",
        "recommendations": [
            "Normal outdoor activities are generally appropriate.",
            "Enjoy fresh air and outdoor exercise.",
        ],
        "caution_note": "No special precautions needed for most people.",
    },
    "Satisfactory": {
        "headline": "Air quality is acceptable.",
        "recommendations": [
            "Normal outdoor activities are generally appropriate.",
            "Sensitive individuals may experience mild discomfort.",
        ],
        "caution_note": "Sensitive individuals should monitor for symptoms.",
    },
    "Moderate": {
        "headline": "Moderate air quality.",
        "recommendations": [
            "Sensitive groups may reduce prolonged strenuous outdoor activity.",
            "Consider shorter outdoor exercise sessions.",
        ],
        "caution_note": "Children, elderly, and people with respiratory conditions should be cautious.",
    },
    "Poor": {
        "headline": "Unhealthy air quality.",
        "recommendations": [
            "Children, elderly people, and people with respiratory or cardiac conditions should reduce prolonged outdoor exertion.",
            "Schools should consider moving intense outdoor activity indoors.",
            "General public should limit prolonged outdoor exercise.",
        ],
        "caution_note": "Avoid prolonged outdoor exertion, especially for sensitive groups.",
    },
    "Very Poor": {
        "headline": "Very poor air quality.",
        "recommendations": [
            "Avoid prolonged outdoor exertion for everyone.",
            "Sensitive groups should remain indoors where possible.",
            "Outdoor workers should use exposure-reduction measures and take breaks.",
            "Schools should shift outdoor sports indoors.",
        ],
        "caution_note": "Stay indoors with windows closed where possible.",
    },
    "Severe": {
        "headline": "Severe air quality emergency.",
        "recommendations": [
            "Avoid all outdoor exertion.",
            "Sensitive groups should remain indoors with air purification if available.",
            "Outdoor workers should minimize exposure and use protective measures.",
            "Schools should cancel outdoor activities entirely.",
        ],
        "caution_note": "Emergency-level air quality. Minimize all outdoor exposure.",
    },
}

_ADVISORY_HI: dict[str, dict[str, str | list[str]]] = {
    "Good": {
        "headline": "वायु गुणवत्ता संतोषजनक है।",
        "recommendations": [
            "सामान्य बाहरी गतिविधियाँ आमतौर पर उपयुक्त हैं।",
            "ताज़ी हवा और बाहरी व्यायाम का आनंद लें।",
        ],
        "caution_note": "अधिकांश लोगों के लिए कोई विशेष सावधानी आवश्यक नहीं।",
    },
    "Satisfactory": {
        "headline": "वायु गुणवत्ता स्वीकार्य है।",
        "recommendations": [
            "सामान्य बाहरी गतिविधियाँ आमतौर पर उपयुक्त हैं।",
            "संवेदनशील व्यक्तियों को हल्की असुविधा हो सकती है।",
        ],
        "caution_note": "संवेदनशील व्यक्तियों को लक्षणों पर ध्यान देना चाहिए।",
    },
    "Moderate": {
        "headline": "मध्यम वायु गुणवत्ता।",
        "recommendations": [
            "संवेदनशील समूह लंबे समय की कठिन बाहरी गतिविधि कम कर सकते हैं।",
            "छोटे बाहरी व्यायाम सत्रों पर विचार करें।",
        ],
        "caution_note": "बच्चे, वृद्ध और श्वसन संबंधी समस्या वाले लोगों को सावधान रहना चाहिए।",
    },
    "Poor": {
        "headline": "अस्वास्थ्यकर वायु गुणवत्ता।",
        "recommendations": [
            "बच्चे, वृद्ध तथा श्वसन या हृदय संबंधी समस्या वाले लोगों को लंबे बाहरी परिश्रम को कम करना चाहिए।",
            "स्कूल तीव्र बाहरी गतिविधियों को अंदर स्थानांतरित करने पर विचार करें।",
            "सामान्य जनता लंबे बाहरी व्यायाम को सीमित करे।",
        ],
        "caution_note": "लंबे बाहरी परिश्रम से बचें, विशेषकर संवेदनशील समूहों के लिए।",
    },
    "Very Poor": {
        "headline": "बहुत खराब वायु गुणवत्ता।",
        "recommendations": [
            "सभी के लिए लंबे बाहरी परिश्रम से बचें।",
            "संवेदनशील समूह जहाँ संभव हो घर के अंदर रहें।",
            "बाहरी कामगार जोखिम कम करने के उपाय अपनाएँ और विश्राम लें।",
            "स्कूल बाहरी खेलों को अंदर स्थानांतरित करें।",
        ],
        "caution_note": "जहाँ संभव हो खिड़कियाँ बंद रखकर घर के अंदर रहें।",
    },
    "Severe": {
        "headline": "गंभीर वायु गुणवत्ता आपात स्थिति।",
        "recommendations": [
            "सभी बाहरी परिश्रम से बचें।",
            "संवेदनशील समूह जहाँ उपलब्ध हो वायु शुद्धीकरण के साथ घर के अंदर रहें।",
            "बाहरी कामगार जोखिम कम करें और सुरक्षा उपाय अपनाएँ।",
            "स्कूल सभी बाहरी गतिविधियाँ रद्द करें।",
        ],
        "caution_note": "आपात-स्तर की वायु गुणवत्ता। बाहरी संपर्क न्यूनतम रखें।",
    },
}

_ADVISORY_KN: dict[str, dict[str, str | list[str]]] = {
    "Good": {
        "headline": "ಗಾಳಿ ಗುಣಮಟ್ಟ ತೃಪ್ತಿಕರವಾಗಿದೆ.",
        "recommendations": [
            "ಸಾಮಾನ್ಯ ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳು ಸಾಮಾನ್ಯವಾಗಿ ಸೂಕ್ತ.",
            "ತಾಜಾ ಗಾಳಿ ಮತ್ತು ಹೊರಾಂಗಣ ವ್ಯಾಯಾಮವನ್ನು ಆನಂದಿಸಿ.",
        ],
        "caution_note": "ಬಹುತೇಕ ಜನರಿಗೆ ವಿಶೇಷ ಮುನ್ನೆಚ್ಚರಿಕೆ ಅಗತ್ಯವಿಲ್ಲ.",
    },
    "Satisfactory": {
        "headline": "ಗಾಳಿ ಗುಣಮಟ್ಟ ಸ್ವೀಕಾರಾರ್ಹವಾಗಿದೆ.",
        "recommendations": [
            "ಸಾಮಾನ್ಯ ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳು ಸಾಮಾನ್ಯವಾಗಿ ಸೂಕ್ತ.",
            "ಸೂಕ್ಷ್ಮ ವ್ಯಕ್ತಿಗಳಿಗೆ ಸ್ವಲ್ಪ ಅಸ್ವಸ್ಥತೆ ಇರಬಹುದು.",
        ],
        "caution_note": "ಸೂಕ್ಷ್ಮ ವ್ಯಕ್ತಿಗಳು ಲಕ್ಷಣಗಳನ್ನು ಗಮನಿಸಬೇಕು.",
    },
    "Moderate": {
        "headline": "ಮಧ್ಯಮ ಗಾಳಿ ಗುಣಮಟ್ಟ.",
        "recommendations": [
            "ಸೂಕ್ಷ್ಮ ಗುಂಪುಗಳು ದೀರ್ಘ ಕಠಿಣ ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಬಹುದು.",
            "ಕಡಿಮೆ ಅವಧಿಯ ಹೊರಾಂಗಣ ವ್ಯಾಯಾಮವನ್ನು ಪರಿಗಣಿಸಿ.",
        ],
        "caution_note": "ಮಕ್ಕಳು, ವೃದ್ಧರು ಮತ್ತು ಉಸಿರಾಟದ ಸಮಸ್ಯೆ ಇರುವವರು ಎಚ್ಚರಿಕೆಯಿಂದಿರಬೇಕು.",
    },
    "Poor": {
        "headline": "ಆರೋಗ್ಯಕ್ಕೆ ಹಾನಿಕರ ಗಾಳಿ ಗುಣಮಟ್ಟ.",
        "recommendations": [
            "ಮಕ್ಕಳು, ವೃದ್ಧರು ಹಾಗೂ ಉಸಿರಾಟ/ಹೃದಯ ಸಂಬಂಧಿ ಸಮಸ್ಯೆ ಇರುವವರು ದೀರ್ಘ ಹೊರಾಂಗಣ ಶ್ರಮವನ್ನು ಕಡಿಮೆ ಮಾಡಬೇಕು.",
            "ಶಾಲೆಗಳು ತೀವ್ರ ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳನ್ನು ಒಳಗೆ ಸ್ಥಳಾಂತರಿಸುವುದನ್ನು ಪರಿಗಣಿಸಬೇಕು.",
            "ಸಾಮಾನ್ಯ ಜನರು ದೀರ್ಘ ಹೊರಾಂಗಣ ವ್ಯಾಯಾಮವನ್ನು ಮಿತಿಗೊಳಿಸಬೇಕು.",
        ],
        "caution_note": "ದೀರ್ಘ ಹೊರಾಂಗಣ ಶ್ರಮವನ್ನು ತಪ್ಪಿಸಿ, ವಿಶೇಷವಾಗಿ ಸೂಕ್ಷ್ಮ ಗುಂಪುಗಳಿಗೆ.",
    },
    "Very Poor": {
        "headline": "ತುಂಬಾ ಕಳಪೆ ಗಾಳಿ ಗುಣಮಟ್ಟ.",
        "recommendations": [
            "ಎಲ್ಲರಿಗೂ ದೀರ್ಘ ಹೊರಾಂಗಣ ಶ್ರಮವನ್ನು ತಪ್ಪಿಸಿ.",
            "ಸೂಕ್ಷ್ಮ ಗುಂಪುಗಳು ಸಾಧ್ಯವಾದಷ್ಟು ಒಳಾಂಗಣದಲ್ಲಿರಬೇಕು.",
            "ಹೊರಾಂಗಣ ಕಾರ್ಮಿಕರು ಒಡ್ಡುವಿಕೆ ಕಡಿಮೆ ಮಾಡುವ ಕ್ರಮಗಳನ್ನು ತೆಗೆದುಕೊಂಡು ವಿರಾಮ ತೆಗೆದುಕೊಳ್ಳಬೇಕು.",
            "ಶಾಲೆಗಳು ಹೊರಾಂಗಣ ಕ್ರೀಡೆಗಳನ್ನು ಒಳಗೆ ಸ್ಥಳಾಂತರಿಸಬೇಕು.",
        ],
        "caution_note": "ಸಾಧ್ಯವಾದರೆ ಕಿಟಕಿಗಳನ್ನು ಮುಚ್ಚಿ ಒಳಾಂಗಣದಲ್ಲಿರಿ.",
    },
    "Severe": {
        "headline": "ತೀವ್ರ ಗಾಳಿ ಗುಣಮಟ್ಟ ತುರ್ತು ಪರಿಸ್ಥಿತಿ.",
        "recommendations": [
            "ಎಲ್ಲಾ ಹೊರಾಂಗಣ ಶ್ರಮವನ್ನು ತಪ್ಪಿಸಿ.",
            "ಸೂಕ್ಷ್ಮ ಗುಂಪುಗಳು ಲಭ್ಯವಿದ್ದರೆ ಗಾಳಿ ಶುದ್ಧೀಕರಣದೊಂದಿಗೆ ಒಳಾಂಗಣದಲ್ಲಿರಬೇಕು.",
            "ಹೊರಾಂಗಣ ಕಾರ್ಮಿಕರು ಒಡ್ಡುವಿಕೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಿ ರಕ್ಷಣಾ ಕ್ರಮಗಳನ್ನು ಬಳಸಬೇಕು.",
            "ಶಾಲೆಗಳು ಎಲ್ಲಾ ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳನ್ನು ರದ್ದುಗೊಳಿಸಬೇಕು.",
        ],
        "caution_note": "ತುರ್ತು-ಮಟ್ಟದ ಗಾಳಿ ಗುಣಮಟ್ಟ. ಹೊರಾಂಗಣ ಒಡ್ಡುವಿಕೆಯನ್ನು ಕನಿಷ್ಠಕ್ಕೆ ಇರಿಸಿ.",
    },
}

_ADVISORY_BY_LANG: dict[str, dict[str, dict[str, str | list[str]]]] = {
    "en": _ADVISORY_EN,
    "hi": _ADVISORY_HI,
    "kn": _ADVISORY_KN,
}

# ---------------------------------------------------------------------------
# Profile modifiers
# ---------------------------------------------------------------------------
_PROFILE_MODIFIERS_EN: dict[str, list[str]] = {
    "child": [
        "Children should avoid outdoor play during poor or worse conditions.",
        "Schools should reschedule outdoor sports to indoor facilities.",
    ],
    "elderly": [
        "Older adults should remain indoors during moderate or worse conditions.",
        "Monitor for respiratory symptoms and seek medical attention if needed.",
    ],
    "respiratory": [
        "People with asthma or respiratory conditions should keep rescue medication accessible.",
        "Reduce outdoor exposure, especially during peak pollution hours.",
    ],
    "outdoor_worker": [
        "Use exposure-reduction measures: take breaks in clean-air areas.",
        "Consider wearing a well-fitted mask during poor or worse conditions.",
        "Schedule heavy exertion during lower-pollution periods if possible.",
    ],
    "school": [
        "Schools should move intense outdoor physical activities indoors during poor or worse conditions.",
        "Monitor student symptoms and provide clean-air break areas.",
    ],
}

_PROFILE_MODIFIERS_HI: dict[str, list[str]] = {
    "child": [
        "खराब या उससे बदतर स्थिति में बच्चों को बाहरी खेल से बचना चाहिए।",
        "स्कूल बाहरी खेलों को अंदर की सुविधाओं में स्थानांतरित करें।",
    ],
    "elderly": [
        "मध्यम या बदतर स्थिति में वृद्धजन घर के अंदर रहें।",
        "श्वसन लक्षणों पर नज़र रखें और आवश्यकता होने पर चिकित्सकीय सहायता लें।",
    ],
    "respiratory": [
        "अस्थमा या श्वसन समस्या वाले लोग बचाव दवा आसानी से उपलब्ध रखें।",
        "बाहरी संपर्क कम करें, विशेषकर प्रदूषण की चरम अवधि में।",
    ],
    "outdoor_worker": [
        "जोखिम कम करने के उपाय अपनाएँ: स्वच्छ-वायु क्षेत्रों में विश्राम लें।",
        "खराब या बदतर स्थिति में सही फिट वाला मास्क पहनने पर विचार करें।",
        "जहाँ संभव हो, भारी परिश्रम कम-प्रदूषण अवधि में निर्धारित करें।",
    ],
    "school": [
        "खराब या बदतर स्थिति में स्कूल तीव्र बाहरी शारीरिक गतिविधियों को अंदर ले जाएँ।",
        "छात्रों के लक्षणों पर नज़र रखें और स्वच्छ-वायु विश्राम क्षेत्र उपलब्ध कराएँ।",
    ],
}

_PROFILE_MODIFIERS_KN: dict[str, list[str]] = {
    "child": [
        "ಕಳಪೆ ಅಥವಾ ಅದಕ್ಕಿಂತ ಕೆಟ್ಟ ಪರಿಸ್ಥಿತಿಯಲ್ಲಿ ಮಕ್ಕಳು ಹೊರಾಂಗಣ ಆಟವನ್ನು ತಪ್ಪಿಸಬೇಕು.",
        "ಶಾಲೆಗಳು ಹೊರಾಂಗಣ ಕ್ರೀಡೆಗಳನ್ನು ಒಳಾಂಗಣ ಸೌಲಭ್ಯಗಳಿಗೆ ಬದಲಾಯಿಸಬೇಕು.",
    ],
    "elderly": [
        "ಮಧ್ಯಮ ಅಥವಾ ಕೆಟ್ಟ ಪರಿಸ್ಥಿತಿಯಲ್ಲಿ ವೃದ್ಧರು ಒಳಾಂಗಣದಲ್ಲಿರಬೇಕು.",
        "ಉಸಿರಾಟದ ಲಕ್ಷಣಗಳನ್ನು ಗಮನಿಸಿ, ಅಗತ್ಯವಿದ್ದರೆ ವೈದ್ಯಕೀಯ ಸಹಾಯ ಪಡೆಯಿರಿ.",
    ],
    "respiratory": [
        "ಆಸ್ತಮಾ ಅಥವಾ ಉಸಿರಾಟದ ಸಮಸ್ಯೆ ಇರುವವರು ರಕ್ಷಣಾ ಔಷಧ ಸುಲಭವಾಗಿ ಲಭ್ಯವಿರುವಂತೆ ಇಡಬೇಕು.",
        "ಹೊರಾಂಗಣ ಒಡ್ಡುವಿಕೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಿ, ವಿಶೇಷವಾಗಿ ಮಾಲಿನ್ಯದ ಉತ್ತುಂಗ ಸಮಯದಲ್ಲಿ.",
    ],
    "outdoor_worker": [
        "ಒಡ್ಡುವಿಕೆ ಕಡಿಮೆ ಮಾಡುವ ಕ್ರಮಗಳನ್ನು ಬಳಸಿ: ಸ್ವಚ್ಛ-ಗಾಳಿ ಪ್ರದೇಶಗಳಲ್ಲಿ ವಿರಾಮ ತೆಗೆದುಕೊಳ್ಳಿ.",
        "ಕಳಪೆ ಅಥವಾ ಕೆಟ್ಟ ಪರಿಸ್ಥಿತಿಯಲ್ಲಿ ಸರಿಯಾಗಿ ಹೊಂದುವ ಮುಖವಾಡವನ್ನು ಪರಿಗಣಿಸಿ.",
        "ಸಾಧ್ಯವಾದರೆ ಭಾರಿ ಶ್ರಮವನ್ನು ಕಡಿಮೆ-ಮಾಲಿನ್ಯ ಅವಧಿಗೆ ನಿಗದಿಪಡಿಸಿ.",
    ],
    "school": [
        "ಕಳಪೆ ಅಥವಾ ಕೆಟ್ಟ ಪರಿಸ್ಥಿತಿಯಲ್ಲಿ ಶಾಲೆಗಳು ತೀವ್ರ ಹೊರಾಂಗಣ ದೈಹಿಕ ಚಟುವಟಿಕೆಗಳನ್ನು ಒಳಗೆ ಸಾಗಿಸಬೇಕು.",
        "ವಿದ್ಯಾರ್ಥಿಗಳ ಲಕ್ಷಣಗಳನ್ನು ಗಮನಿಸಿ ಮತ್ತು ಸ್ವಚ್ಛ-ಗಾಳಿ ವಿರಾಮ ಪ್ರದೇಶಗಳನ್ನು ಒದಗಿಸಿ.",
    ],
}

_PROFILE_BY_LANG: dict[str, dict[str, list[str]]] = {
    "en": _PROFILE_MODIFIERS_EN,
    "hi": _PROFILE_MODIFIERS_HI,
    "kn": _PROFILE_MODIFIERS_KN,
}

# Helper notes (confidence / unavailable / quality)
_NOTES: dict[str, dict[str, str]] = {
    "en": {
        "confidence_low": " Note: forecast confidence is {level}.",
        "forecast_unavailable": "Forecast not available for this station.",
        "pm25_unavailable": "PM2.5 forecast unavailable: {status}",
        "data_quality": "Station data quality: {quality}.",
    },
    "hi": {
        "confidence_low": " ध्यान दें: पूर्वानुमान विश्वसनीयता {level} है।",
        "forecast_unavailable": "इस स्टेशन के लिए पूर्वानुमान उपलब्ध नहीं है।",
        "pm25_unavailable": "PM2.5 पूर्वानुमान उपलब्ध नहीं: {status}",
        "data_quality": "स्टेशन डेटा गुणवत्ता: {quality}.",
    },
    "kn": {
        "confidence_low": " ಗಮನಿಸಿ: ಮುನ್ಸೂಚನೆ ವಿಶ್ವಾಸಾರ್ಹತೆ {level}.",
        "forecast_unavailable": "ಈ ನಿಲ್ದಾಣಕ್ಕೆ ಮುನ್ಸೂಚನೆ ಲಭ್ಯವಿಲ್ಲ.",
        "pm25_unavailable": "PM2.5 ಮುನ್ಸೂಚನೆ ಲಭ್ಯವಿಲ್ಲ: {status}",
        "data_quality": "ನಿಲ್ದಾಣ ಡೇಟಾ ಗುಣಮಟ್ಟ: {quality}.",
    },
}


def _norm_lang(language: str) -> str:
    c = (language or "en").strip().lower()
    return c if c in SUPPORTED_LANGUAGES else "en"


def _risk_category(pm25: float) -> str:
    for name, threshold in PM25_RISK_THRESHOLDS.items():
        if pm25 <= threshold:
            return name
    return "Severe"


def _get_advisory(profile: str, risk_category: str, language: str = "en") -> dict[str, Any]:
    lang = _norm_lang(language)
    table = _ADVISORY_BY_LANG.get(lang) or _ADVISORY_EN
    base = table.get(risk_category) or table.get("Good") or _ADVISORY_EN["Good"]
    # If a band is missing in non-EN (shouldn't happen), fall back to EN band
    if risk_category not in table and lang != "en":
        base = _ADVISORY_EN.get(risk_category, _ADVISORY_EN["Good"])

    modifiers_table = _PROFILE_BY_LANG.get(lang) or _PROFILE_MODIFIERS_EN
    modifiers = list(modifiers_table.get(profile, []))
    # Profile modifiers: if missing in lang, use EN modifiers (partial)
    if profile not in modifiers_table and lang != "en":
        modifiers = list(_PROFILE_MODIFIERS_EN.get(profile, []))

    recommendations = list(base["recommendations"]) + modifiers
    return {
        "headline": str(base["headline"]),
        "recommendations": recommendations,
        "caution_note": str(base["caution_note"]),
    }


def get_citizen_advisory(
    station_id: str,
    profile: str = "general",
    language: str = "en",
    city: str = "bengaluru",
) -> dict:
    """Generate a deterministic citizen health advisory for a station."""
    language_requested = _norm_lang(language)
    notes = _NOTES.get(language_requested) or _NOTES["en"]
    disclaimer = MEDICAL_DISCLAIMER_BY_LANG.get(language_requested, MEDICAL_DISCLAIMER)

    try:
        snapshot = get_station_snapshot(station_id, city)
    except (UnsupportedCityError, UnknownStationError, MissingArtifactError, NoValidForecastError):
        raise

    if not snapshot.get("forecast_eligible", True):
        return {
            "station_id": station_id,
            "station_name": snapshot.get("station_name", station_id),
            "city": snapshot.get("city", city),
            "profile": profile,
            "language_requested": language_requested,
            "language_served": language_requested,
            "translation_fallback": False,
            "forecast_risk_category": "Unknown",
            "predicted_pm25": 0,
            "confidence_level": "Unavailable",
            "headline": notes["forecast_unavailable"],
            "recommendations": [],
            "caution_note": "",
            "data_quality_note": notes["pm25_unavailable"].format(
                status=snapshot.get("pm25_forecast_coverage_status", "")
            ),
            "medical_disclaimer": disclaimer,
            "forecast_eligible": False,
            "pm25_forecast_coverage_status": snapshot.get("pm25_forecast_coverage_status"),
            "available_pollutants": snapshot.get("available_pollutants", []),
        }

    predicted_pm25 = snapshot["predicted_pm25"]
    risk_category = snapshot["risk_category"]
    conf_data = get_forecast_confidence(station_id, city=city)
    confidence_level = conf_data["confidence_level"]

    # Serve translated content when table has the risk band
    advisory_table = _ADVISORY_BY_LANG.get(language_requested) or _ADVISORY_EN
    has_band = risk_category in advisory_table
    if language_requested == "en" or has_band:
        language_served = language_requested
        translation_fallback = False
        advisory = _get_advisory(profile, risk_category, language_requested)
    else:
        language_served = "en"
        translation_fallback = True
        advisory = _get_advisory(profile, risk_category, "en")

    confidence_note = ""
    if confidence_level in ("Low", "Unavailable"):
        conf_notes = _NOTES.get(language_served) or _NOTES["en"]
        confidence_note = conf_notes["confidence_low"].format(level=confidence_level)

    data_quality_note = ""
    quality_class = snapshot.get("quality_classification", "Unknown")
    if "Usable" in quality_class:
        dq_notes = _NOTES.get(language_served) or _NOTES["en"]
        data_quality_note = dq_notes["data_quality"].format(quality=quality_class)

    return {
        "station_id": station_id,
        "station_name": snapshot["station_name"],
        "city": snapshot["city"],
        "profile": profile,
        "language_requested": language_requested,
        "language_served": language_served,
        "translation_fallback": translation_fallback,
        "forecast_risk_category": risk_category,
        "predicted_pm25": predicted_pm25,
        "confidence_level": confidence_level,
        "headline": advisory["headline"] + confidence_note,
        "recommendations": advisory["recommendations"],
        "caution_note": advisory["caution_note"],
        "data_quality_note": data_quality_note,
        "medical_disclaimer": MEDICAL_DISCLAIMER_BY_LANG.get(language_served, MEDICAL_DISCLAIMER),
        "forecast_eligible": True,
        "pm25_forecast_coverage_status": None,
        "available_pollutants": [],
    }
