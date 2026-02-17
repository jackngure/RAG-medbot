from django.core.cache import cache
from django.db.models import Q
from .models import Disease, Symptom, FirstAidProcedure
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class RAGRetriever:
    """
    Simple working RAG retriever
    """
    
    def retrieve_relevant_first_aid(self, user_input, extracted_symptoms):
        """
        Simple keyword matching retrieval
        """
        print(f"\n=== RAG RETRIEVER ===")
        print(f"Extracted symptoms: {extracted_symptoms}")
        
        if not extracted_symptoms:
            print("No symptoms to match")
            return []
        
        try:
            # Import models here
            from .models import Disease, FirstAidProcedure
            
            results = []
            
            # Get all diseases
            diseases = Disease.objects.all()
            print(f"Total diseases in DB: {diseases.count()}")
            
            for disease in diseases:
                # Create a searchable text from disease name and symptoms
                disease_text = f"{disease.name.lower()} {disease.common_symptoms.lower()}"
                print(f"Checking disease: {disease.name}")
                print(f"  Disease text: {disease_text[:50]}...")
                
                match_count = 0
                matched_symptoms = []
                
                for symptom in extracted_symptoms:
                    if symptom.lower() in disease_text:
                        match_count += 1
                        matched_symptoms.append(symptom)
                        print(f"  ✓ Matched symptom: '{symptom}'")
                
                if match_count > 0:
                    confidence = match_count / len(extracted_symptoms)
                    print(f"  Match count: {match_count}, Confidence: {confidence}")
                    
                    # Get first aid for this disease
                    try:
                        first_aid = FirstAidProcedure.objects.filter(disease=disease).first()
                        
                        if first_aid:
                            print(f"  Found first aid for: {disease.name}")
                            results.append({
                                'disease': disease.name,
                                'confidence': confidence,
                                'first_aid': {
                                    'steps': first_aid.steps,
                                    'warning_notes': first_aid.warning_notes,
                                    'when_to_seek_help': first_aid.when_to_seek_help
                                }
                            })
                    except Exception as e:
                        print(f"  Error getting first aid: {e}")
            
            # Sort by confidence (highest first)
            results.sort(key=lambda x: x['confidence'], reverse=True)
            print(f"\nTotal matches found: {len(results)}")
            
            if results:
                print(f"Best match: {results[0]['disease']} with confidence {results[0]['confidence']}")
            
            return results[:3]  # Return top 3 matches
            
        except Exception as e:
            print(f"ERROR in RAG retriever: {e}")
            import traceback
            traceback.print_exc()
            return []


# Simple singleton
_rag_retriever_instance = None

def get_rag_retriever():
    """Get or create the RAGRetriever singleton"""
    global _rag_retriever_instance
    if _rag_retriever_instance is None:
        _rag_retriever_instance = RAGRetriever()
        print("✅ RAGRetriever instance created")
    return _rag_retriever_instance