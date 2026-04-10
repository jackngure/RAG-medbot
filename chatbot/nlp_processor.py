import spacy
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re
import logging
from django.core.cache import cache

# Download NLTK data at import time (quietly); missing data falls back to
# simple splitting — never crashes the import.
try:
    nltk.download("punkt",     quiet=True)
    nltk.download("stopwords", quiet=True)
    nltk.download("wordnet",   quiet=True)
except Exception:
    pass

logger = logging.getLogger(__name__)


class MedicalNLPProcessor:
    """
    Medical NLP processor aligned with the Kenya-specific knowledge base
    defined in populate_kenya_data.py.

    Symptom variations and emergency keyword patterns exactly mirror
    SYMPTOM_CATALOGUE and EMERGENCY_CATALOGUE so the NLP layer never drifts
    from what the database contains.

    Key improvements over the original
    ------------------------------------
    * Symptom variations expanded from 10 to all 29 catalogue symptoms.
    * Emergency patterns cover all 14 catalogue keywords (including typo
      variants) and add an explicit severity map so callers can react
      differently to CRITICAL vs HIGH events.
    * ORM objects are no longer pickled into the cache — plain dicts are used
      instead, which are safe across schema migrations.
    * All debug output goes through logging (logger.debug) rather than print();
      control verbosity via Django's LOGGING settings.
    * Input validation guards against None / empty strings.
    * Empty alternative-name tokens (e.g. trailing commas) are silently skipped.
    * spaCy model loading never triggers a network download at request time;
      if the model is absent an informative error is raised immediately.
    """

    # ------------------------------------------------------------------
    # Cache configuration
    # ------------------------------------------------------------------
    SYMPTOMS_CACHE_TIMEOUT          = 3600   # 1 hour
    EMERGENCY_KEYWORDS_CACHE_TIMEOUT = 3600

    # ------------------------------------------------------------------
    # Symptom variations
    # Derived directly from SYMPTOM_CATALOGUE alternative_names fields.
    # Each list item is a substring we look for in the lowercased input.
    # ------------------------------------------------------------------
    SYMPTOM_VARIATIONS: dict = {
        "fever": [
            "fever", "high temperature", "hot body", "sweating", "chills",
            "feeling hot", "feverish", "temperature",
        ],
        "headache": [
            "headache", "head pain", "migraine", "throbbing head",
            "pressure in head", "head hurting",
        ],
        "cough": [
            "cough", "coughing", "dry cough", "wet cough",
            "chest cough", "barking cough",
        ],
        "diarrhea": [
            "diarrhea", "diarrhoea", "loose stools", "running stomach",
            "watery stool", "frequent bathroom", "stomach running",
        ],
        "vomiting": [
            "vomit", "vomiting", "throwing up", "nausea",
            "sick stomach", "can't keep food down",
        ],
        "fatigue": [
            "fatigue", "tired", "tiredness", "weakness", "exhausted",
            "exhaustion", "lethargy", "no energy", "body weak",
        ],
        "chest_pain": [
            "chest pain", "chest discomfort", "heart pain",
            "tight chest", "squeezing in chest",
        ],
        "difficulty_breathing": [
            "difficulty breathing", "shortness of breath", "breathlessness",
            "can't breathe", "breathing fast", "wheezing",
        ],
        "joint_pain": [
            "joint pain", "joint ache", "arthritis", "pain in joints",
            "knees hurt", "back pain",
        ],
        "muscle_pain": [
            "muscle pain", "myalgia", "body aches", "sore muscles",
            "whole body pain",
        ],
        "rash": [
            "rash", "skin rash", "red spots", "itching", "hives",
            "skin bumps", "scratching",
        ],
        "abdominal_pain": [
            "abdominal pain", "stomach ache", "belly pain", "cramping",
            "tummy hurts", "stomach problems", "stomach pain",
        ],
        "dehydration": [
            "dehydration", "dry mouth", "sunken eyes", "reduced urine",
            "thirsty", "no tears", "dark urine",
        ],
        "confusion": [
            "confusion", "disoriented", "altered mental state", "delirium",
            "not acting normal", "confused mind",
        ],
        "burning_urination": [
            "burning urination", "pain when passing urine",
            "painful urination", "burning sensation", "urine burns",
        ],
        "frequent_urination": [
            "frequent urination", "passing urine often",
            "many times bathroom", "can't hold urine",
        ],
        "blood_urine": [
            "blood in urine", "red urine", "bloody urine",
            "pink urine", "blood when passing urine",
        ],
        "lower_back_pain": [
            "lower back pain", "backache", "pain in lower back",
            "kidney pain", "spine hurts",
        ],
        "runny_nose": [
            "runny nose", "running nose", "nasal discharge",
            "blocked nose", "flu",
        ],
        "sneezing": [
            "sneezing", "sneezing constantly", "allergy sneezing",
        ],
        "sore_throat": [
            "sore throat", "painful throat", "throat pain",
            "difficulty swallowing", "swollen throat",
        ],
        "yellow_discharge": [
            "yellow discharge", "pus from wound", "infected wound",
            "yellow fluid", "wound oozing",
        ],
        "swelling": [
            "swelling", "swollen", "edema", "puffy", "inflamed",
        ],
        "redness": [
            "redness", "red skin", "inflamed skin", "hot skin",
        ],
        "wound": [
            "wound", "cut", "injury", "sore", "ulcer",
            "broken skin", "open wound",
        ],
        "high_bp_symptoms": [
            "severe headache", "blurred vision", "nose bleeding",
            "pounding heart", "nosebleed",
        ],
        "high_sugar_symptoms": [
            "excessive thirst", "hunger", "weight loss",
            "slow healing", "blurred vision",
        ],
        "numbness": [
            "numbness", "tingling", "pins and needles",
            "loss of feeling", "dead feeling",
        ],
        "dizziness": [
            "dizziness", "feeling faint", "lightheaded",
            "spinning sensation", "vertigo", "off balance",
        ],
    }

    # ------------------------------------------------------------------
    # Emergency keyword → severity map
    # Mirrors EMERGENCY_CATALOGUE exactly (including typo variants).
    # ------------------------------------------------------------------
    EMERGENCY_SEVERITY: dict = {
        # CRITICAL
        "unconscious":      "CRITICAL",
        "unconcious":       "CRITICAL",   # intentional typo variant
        "not breathing":    "CRITICAL",
        "severe bleeding":  "CRITICAL",
        "snake bite":       "CRITICAL",
        "choking":          "CRITICAL",
        "heart attack":     "CRITICAL",
        "drowning":         "CRITICAL",
        "poison":           "CRITICAL",
        # HIGH
        "seizure":          "HIGH",
        "convulsions":      "HIGH",
        "burn":             "HIGH",
        "fainting":         "HIGH",
        "bleeding":         "HIGH",
    }

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        # Fail fast if the spaCy model is missing rather than blocking a web
        # worker with a multi-second download.  Install the model via:
        #   python -m spacy download en_core_web_sm
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError as exc:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' is not installed. "
                "Run: python -m spacy download en_core_web_sm"
            ) from exc

        self.stop_words = set(stopwords.words("english"))

    # ------------------------------------------------------------------
    # Private: database helpers (cached, returns plain dicts)
    # ------------------------------------------------------------------

    def _get_all_symptoms(self) -> list:
        """
        Return all Symptom rows as plain dicts (safe to pickle in any cache
        backend).  Falls back to an empty list on error so extraction can
        still run using SYMPTOM_VARIATIONS.
        """
        cache_key = "medical_nlp_all_symptoms"
        symptoms = cache.get(cache_key)
        if symptoms is not None:
            return symptoms

        try:
            from .models import Symptom
            symptoms = list(
                Symptom.objects
                .only("id", "name", "alternative_names")
                .values("id", "name", "alternative_names")
            )
            cache.set(cache_key, symptoms, self.SYMPTOMS_CACHE_TIMEOUT)
        except Exception as exc:
            logger.error("Failed to load symptoms from DB: %s", exc)
            symptoms = []

        return symptoms

    def _get_emergency_keywords(self) -> list:
        """
        Return all EmergencyKeyword rows as plain dicts, cached.
        Falls back to an empty list on error.
        """
        cache_key = "medical_nlp_emergency_keywords"
        keywords = cache.get(cache_key)
        if keywords is not None:
            return keywords

        try:
            from .models import EmergencyKeyword
            keywords = list(
                EmergencyKeyword.objects
                .only("keyword", "severity", "response_message")
                .values("keyword", "severity", "response_message")
            )
            cache.set(cache_key, keywords, self.EMERGENCY_KEYWORDS_CACHE_TIMEOUT)
        except Exception as exc:
            logger.error("Failed to load emergency keywords from DB: %s", exc)
            keywords = []

        return keywords

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def preprocess(self, text: str) -> list:
        """
        Lowercase, strip special characters, tokenise, and remove stop-words.
        Returns a list of tokens.
        """
        if not text or not isinstance(text, str):
            return []

        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)

        try:
            tokens = word_tokenize(text)
        except Exception:
            tokens = text.split()

        return [t for t in tokens if t not in self.stop_words]

    def extract_symptoms(self, text: str) -> list:
        """
        Extract symptoms from free text using two complementary methods:

        1. DB matching — checks every Symptom row's name and
           alternative_names (cached as plain dicts).
        2. Pattern matching — checks SYMPTOM_VARIATIONS for any substring
           that appears in the lowercased input.

        Returns a deduplicated, order-preserving list of symptom name strings.
        """
        if not text or not isinstance(text, str):
            return []

        text_lower = text.lower()
        extracted: list = []
        seen: set = set()

        logger.debug("extract_symptoms | input: %r", text)

        # --- Method 1: database symptom matching ---
        all_symptoms = self._get_all_symptoms()
        logger.debug("extract_symptoms | DB symptoms loaded: %d", len(all_symptoms))

        for symptom in all_symptoms:
            name = symptom["name"]

            if name.lower() in text_lower:
                if name not in seen:
                    seen.add(name)
                    extracted.append(name)
                    logger.debug("extract_symptoms | DB match (name): %s", name)
                continue

            alt_names = symptom.get("alternative_names") or ""
            for alt in alt_names.split(","):
                alt = alt.strip().lower()
                if alt and alt in text_lower:
                    if name not in seen:
                        seen.add(name)
                        extracted.append(name)
                        logger.debug(
                            "extract_symptoms | DB match (alt '%s'): %s", alt, name
                        )
                    break

        # --- Method 2: SYMPTOM_VARIATIONS pattern matching ---
        for symptom_key, variations in self.SYMPTOM_VARIATIONS.items():
            for variation in variations:
                if variation in text_lower:
                    if symptom_key not in seen:
                        seen.add(symptom_key)
                        extracted.append(symptom_key)
                        logger.debug(
                            "extract_symptoms | pattern match '%s' → %s",
                            variation, symptom_key,
                        )
                    break   # one match per symptom_key is enough

        logger.debug("extract_symptoms | result: %s", extracted)
        return extracted

    def detect_emergency(self, text: str) -> list:
        """
        Detect emergency situations by scanning the text for known keywords.

        Checks the database first (cached plain dicts); falls back to
        EMERGENCY_SEVERITY for any keywords the DB does not cover.

        Returns a list of dicts:
            [{"keyword": str, "severity": str, "message": str}, ...]

        Sorted so CRITICAL entries appear before HIGH entries.
        """
        if not text or not isinstance(text, str):
            return []

        text_lower = text.lower()
        emergencies: list = []
        matched_keywords: set = set()

        logger.debug("detect_emergency | input: %r", text)

        # --- Primary: database emergency keywords ---
        db_keywords = self._get_emergency_keywords()
        logger.debug("detect_emergency | DB keywords loaded: %d", len(db_keywords))

        for kw in db_keywords:
            keyword = kw["keyword"].lower()
            if keyword in text_lower and keyword not in matched_keywords:
                matched_keywords.add(keyword)
                emergencies.append({
                    "keyword":  kw["keyword"],
                    "severity": kw["severity"],
                    "message":  kw["response_message"],
                })
                logger.debug(
                    "detect_emergency | DB match: '%s' (%s)",
                    kw["keyword"], kw["severity"],
                )

        # --- Fallback: EMERGENCY_SEVERITY pattern matching ---
        # Catches any keyword present in the severity map but absent from the
        # DB (e.g. during a fresh install before populate_kenya_data has run).
        for keyword, severity in self.EMERGENCY_SEVERITY.items():
            if keyword in text_lower and keyword not in matched_keywords:
                matched_keywords.add(keyword)
                emergencies.append({
                    "keyword":  keyword,
                    "severity": severity,
                    "message":  (
                        f"⚠️ Emergency keyword detected: '{keyword}'. "
                        "Please seek immediate medical assistance. "
                        "Kenya emergency: 999 / 112."
                    ),
                })
                logger.debug(
                    "detect_emergency | fallback match: '%s' (%s)",
                    keyword, severity,
                )

        # Sort: CRITICAL first, then HIGH
        severity_order = {"CRITICAL": 0, "HIGH": 1}
        emergencies.sort(key=lambda e: severity_order.get(e["severity"], 99))

        logger.debug("detect_emergency | result: %s", emergencies)
        return emergencies
