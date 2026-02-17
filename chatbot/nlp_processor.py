import spacy
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re

# Download NLTK data
try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
except:
    pass

class MedicalNLPProcessor:
    def __init__(self):
        # Load spaCy model
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            print("Downloading spaCy model...")
            spacy.cli.download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
            
        self.stop_words = set(stopwords.words('english'))
        
        # Kenyan-specific symptom variations
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
    
    def preprocess(self, text):
        """Clean and normalize text"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Tokenize with NLTK
        try:
            tokens = word_tokenize(text)
        except:
            # Fallback to simple split
            tokens = text.split()
        
        # Remove stopwords
        tokens = [t for t in tokens if t not in self.stop_words]
        
        return tokens
    
    def extract_symptoms(self, text):
        """Extract symptoms using pattern matching"""
        text_lower = text.lower()
        extracted = []
        
        print(f"\n=== NLP EXTRACTOR ===")
        print(f"Input text: {text}")
        
        # Method 1: Direct symptom database matching
        from .models import Symptom
        try:
            all_symptoms = Symptom.objects.all()
            print(f"Total symptoms in DB: {all_symptoms.count()}")
            
            for symptom in all_symptoms:
                # Check symptom name
                if symptom.name.lower() in text_lower:
                    extracted.append(symptom.name)
                    print(f"✓ Found DB symptom: {symptom.name}")
                    continue
                
                # Check alternative names
                if symptom.alternative_names:
                    for alt in symptom.alternative_names.split(','):
                        if alt.strip().lower() in text_lower:
                            extracted.append(symptom.name)
                            print(f"✓ Found DB symptom via alt: {symptom.name} (from '{alt}')")
                            break
        except Exception as e:
            print(f"DB symptom check error: {e}")
        
        # Method 2: Pattern matching with variations
        for symptom, variations in self.symptom_variations.items():
            for var in variations:
                if var in text_lower:
                    extracted.append(symptom)
                    print(f"✓ Found pattern: {symptom} (via '{var}')")
                    break
        
        # Remove duplicates while preserving order
        seen = set()
        unique_extracted = []
        for symptom in extracted:
            if symptom not in seen:
                seen.add(symptom)
                unique_extracted.append(symptom)
        
        print(f"Final extracted symptoms: {unique_extracted}")
        return unique_extracted
    
    def detect_emergency(self, text):
        """Check for emergency keywords"""
        from .models import EmergencyKeyword
        
        text_lower = text.lower()
        emergencies = []
        
        print(f"\n=== EMERGENCY DETECTION ===")
        
        try:
            keywords = EmergencyKeyword.objects.all()
            print(f"Total emergency keywords in DB: {keywords.count()}")
            
            for keyword in keywords:
                if keyword.keyword.lower() in text_lower:
                    emergencies.append({
                        'keyword': keyword.keyword,
                        'severity': keyword.severity,
                        'message': keyword.response_message
                    })
                    print(f"⚠️ EMERGENCY MATCH: {keyword.keyword} ({keyword.severity})")
        except Exception as e:
            print(f"Emergency check error: {e}")
        
        return emergencies