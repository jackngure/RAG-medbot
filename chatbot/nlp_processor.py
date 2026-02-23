import spacy
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re
import logging
from django.core.cache import cache

# Download NLTK data (quietly)
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
except Exception as e:
    # Log or ignore; will fallback to simple splitting if needed
    pass

logger = logging.getLogger(__name__)

class MedicalNLPProcessor:
    """
    Enhanced medical NLP processor with caching and robust error handling.
    All extraction logic is identical to the original version.
    """

    # Cache timeouts (seconds)
    SYMPTOMS_CACHE_TIMEOUT = 3600       # 1 hour
    EMERGENCY_KEYWORDS_CACHE_TIMEOUT = 3600

    # Keep print statements for backward compatibility; set to False to silence
    DEBUG = True

    def __init__(self):
        # Load spaCy model (with download fallback)
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            if self.DEBUG:
                print("Downloading spaCy model...")
            spacy.cli.download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")

        self.stop_words = set(stopwords.words('english'))

        # Kenyan-specific symptom variations (unchanged)
        self.symptom_variations = {
            'fever': ['fever', 'hot', 'temperature', 'sweating', 'chills', 'feverish'],
            'headache': ['headache', 'head pain', 'head hurting', 'migraine'],
            'cough': ['cough', 'coughing', 'dry cough', 'wet cough'],
            'fatigue': ['fatigue', 'tired', 'weakness', 'exhausted', 'lethargy'],
            'vomiting': ['vomit', 'vomiting', 'throwing up', 'nausea', 'sick stomach'],
            'diarrhea': ['diarrhea', 'diarrhoea', 'loose stools', 'running stomach'],
            'chest_pain': ['chest pain', 'chest discomfort', 'heart pain'],
            'difficulty_breathing': ['difficulty breathing', 'shortness of breath', 'can\'t breathe'],
            'joint_pain': ['joint pain', 'joint ache', 'arthritis', 'pain in joints'],
            'stomach_ache': ['stomach ache', 'stomach pain', 'abdominal pain', 'belly pain']
        }

    def _get_all_symptoms(self):
        """
        Retrieve all symptoms from database, cached.
        Returns a list of symptom objects (or dicts) with necessary fields.
        """
        cache_key = "medical_nlp_all_symptoms"
        symptoms = cache.get(cache_key)
        if symptoms is not None:
            return symptoms

        from .models import Symptom
        # Fetch only needed fields to reduce memory
        symptoms = list(Symptom.objects.only('id', 'name', 'alternative_names').all())
        cache.set(cache_key, symptoms, self.SYMPTOMS_CACHE_TIMEOUT)
        return symptoms

    def _get_emergency_keywords(self):
        """
        Retrieve all emergency keywords from database, cached.
        """
        cache_key = "medical_nlp_emergency_keywords"
        keywords = cache.get(cache_key)
        if keywords is not None:
            return keywords

        from .models import EmergencyKeyword
        keywords = list(EmergencyKeyword.objects.only('keyword', 'severity', 'response_message').all())
        cache.set(cache_key, keywords, self.EMERGENCY_KEYWORDS_CACHE_TIMEOUT)
        return keywords

    def preprocess(self, text):
        """Clean and normalize text (unchanged logic)"""
        # Convert to lowercase
        text = text.lower()

        # Remove special characters
        text = re.sub(r'[^\w\s]', ' ', text)

        # Tokenize with NLTK, fallback to simple split
        try:
            tokens = word_tokenize(text)
        except Exception:
            tokens = text.split()

        # Remove stopwords
        tokens = [t for t in tokens if t not in self.stop_words]

        return tokens

    def extract_symptoms(self, text):
        """Extract symptoms using pattern matching (identical logic)"""
        text_lower = text.lower()
        extracted = []

        if self.DEBUG:
            print(f"\n=== NLP EXTRACTOR ===")
            print(f"Input text: {text}")

        # Method 1: Direct symptom database matching (cached)
        try:
            all_symptoms = self._get_all_symptoms()
            if self.DEBUG:
                print(f"Total symptoms in DB: {len(all_symptoms)}")

            for symptom in all_symptoms:
                # Check symptom name
                if symptom.name.lower() in text_lower:
                    extracted.append(symptom.name)
                    if self.DEBUG:
                        print(f"✓ Found DB symptom: {symptom.name}")
                    continue

                # Check alternative names (safely handle None)
                if symptom.alternative_names:
                    for alt in symptom.alternative_names.split(','):
                        if alt.strip().lower() in text_lower:
                            extracted.append(symptom.name)
                            if self.DEBUG:
                                print(f"✓ Found DB symptom via alt: {symptom.name} (from '{alt}')")
                            break
        except Exception as e:
            if self.DEBUG:
                print(f"DB symptom check error: {e}")
            logger.error(f"Symptom extraction DB error: {e}")

        # Method 2: Pattern matching with variations (unchanged)
        for symptom, variations in self.symptom_variations.items():
            for var in variations:
                if var in text_lower:
                    extracted.append(symptom)
                    if self.DEBUG:
                        print(f"✓ Found pattern: {symptom} (via '{var}')")
                    break

        # Remove duplicates while preserving order
        seen = set()
        unique_extracted = []
        for symptom in extracted:
            if symptom not in seen:
                seen.add(symptom)
                unique_extracted.append(symptom)

        if self.DEBUG:
            print(f"Final extracted symptoms: {unique_extracted}")
        return unique_extracted

    def detect_emergency(self, text):
        """Check for emergency keywords (identical logic)"""
        text_lower = text.lower()
        emergencies = []

        if self.DEBUG:
            print(f"\n=== EMERGENCY DETECTION ===")

        try:
            keywords = self._get_emergency_keywords()
            if self.DEBUG:
                print(f"Total emergency keywords in DB: {len(keywords)}")

            for keyword in keywords:
                if keyword.keyword.lower() in text_lower:
                    emergencies.append({
                        'keyword': keyword.keyword,
                        'severity': keyword.severity,
                        'message': keyword.response_message
                    })
                    if self.DEBUG:
                        print(f"⚠️ EMERGENCY MATCH: {keyword.keyword} ({keyword.severity})")
        except Exception as e:
            if self.DEBUG:
                print(f"Emergency check error: {e}")
            logger.error(f"Emergency detection error: {e}")

        return emergencies
