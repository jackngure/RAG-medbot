from django.core.cache import cache
from django.db.models import Q, Prefetch
from .models import Disease, Symptom, FirstAidProcedure
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import logging
import hashlib
import json

logger = logging.getLogger(__name__)

class RAGRetriever:
    """
    Enhanced RAG retriever with caching and optimized queries.
    Matching logic remains identical to the original version.
    """

    # Cache timeout for disease list (seconds) – adjust as needed
    DISEASE_CACHE_TIMEOUT = 3600  # 1 hour
    # Enable/disable debug prints (kept for backward compatibility)
    DEBUG = True

    def _get_diseases_with_text(self):
        """
        Retrieve all diseases with their name and common symptoms,
        returning a list of dicts with precomputed lowercased search text.
        Results are cached to reduce database load.
        """
        cache_key = "rag_diseases_text"
        diseases_data = cache.get(cache_key)
        if diseases_data is not None:
            return diseases_data

        # Fetch only needed fields, prefetch first aid procedures to avoid N+1 later
        diseases = Disease.objects.only('id', 'name', 'common_symptoms').prefetch_related(
            Prefetch('firstaidprocedure_set', queryset=FirstAidProcedure.objects.only(
                'disease_id', 'steps', 'warning_notes', 'when_to_seek_help'
            ), to_attr='prefetched_first_aid')
        ).all()

        diseases_data = []
        for disease in diseases:
            # Safely handle None values in common_symptoms
            common_symptoms = disease.common_symptoms or ""
            disease_text = f"{disease.name.lower()} {common_symptoms.lower()}"
            # Store first aid if exists (will be used later)
            first_aid = disease.prefetched_first_aid[0] if disease.prefetched_first_aid else None
            diseases_data.append({
                'id': disease.id,
                'name': disease.name,
                'search_text': disease_text,
                'first_aid': first_aid
            })

        cache.set(cache_key, diseases_data, self.DISEASE_CACHE_TIMEOUT)
        return diseases_data

    def _match_disease(self, disease, extracted_symptoms):
        """
        Perform substring matching between disease search text and extracted symptoms.
        Returns match count and list of matched symptoms.
        """
        match_count = 0
        matched_symptoms = []
        for symptom in extracted_symptoms:
            if symptom in disease['search_text']:
                match_count += 1
                matched_symptoms.append(symptom)
        return match_count, matched_symptoms

    def retrieve_relevant_first_aid(self, user_input, extracted_symptoms):
        """
        Retrieve first aid procedures relevant to the extracted symptoms.
        Uses exact keyword matching (substring) to preserve original behaviour.
        Returns top 3 matches sorted by confidence.
        """
        if self.DEBUG:
            print(f"\n=== RAG RETRIEVER ===")
            print(f"Extracted symptoms: {extracted_symptoms}")

        if not extracted_symptoms:
            if self.DEBUG:
                print("No symptoms to match")
            return []

        # Normalise and deduplicate symptoms
        extracted_symptoms = list({symptom.lower().strip() for symptom in extracted_symptoms if symptom})
        if not extracted_symptoms:
            return []

        # Try to get cached result for this exact symptom set
        cache_key = f"rag_result_{hashlib.md5(json.dumps(sorted(extracted_symptoms)).encode()).hexdigest()}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            if self.DEBUG:
                print("Returning cached result")
            return cached_result

        try:
            # Get diseases data (cached)
            diseases_data = self._get_diseases_with_text()
            if self.DEBUG:
                print(f"Total diseases in DB: {len(diseases_data)}")

            results = []

            for disease in diseases_data:
                if self.DEBUG:
                    print(f"Checking disease: {disease['name']}")
                    print(f"  Disease text: {disease['search_text'][:50]}...")

                match_count, matched_symptoms = self._match_disease(disease, extracted_symptoms)

                if match_count > 0:
                    confidence = match_count / len(extracted_symptoms)
                    if self.DEBUG:
                        print(f"  Matched symptoms: {matched_symptoms}")
                        print(f"  Match count: {match_count}, Confidence: {confidence}")

                    if disease['first_aid']:
                        if self.DEBUG:
                            print(f"  Found first aid for: {disease['name']}")
                        results.append({
                            'disease': disease['name'],
                            'confidence': confidence,
                            'first_aid': {
                                'steps': disease['first_aid'].steps,
                                'warning_notes': disease['first_aid'].warning_notes,
                                'when_to_seek_help': disease['first_aid'].when_to_seek_help
                            }
                        })
                    elif self.DEBUG:
                        print(f"  No first aid for: {disease['name']}")

            # Sort by confidence descending
            results.sort(key=lambda x: x['confidence'], reverse=True)
            if self.DEBUG:
                print(f"\nTotal matches found: {len(results)}")
                if results:
                    print(f"Best match: {results[0]['disease']} with confidence {results[0]['confidence']}")

            # Return top 3
            top_results = results[:3]
            # Cache the result for a short time (e.g., 5 minutes) to handle repeated identical queries
            cache.set(cache_key, top_results, 300)
            return top_results

        except Exception as e:
            logger.error(f"ERROR in RAG retriever: {e}", exc_info=True)
            if self.DEBUG:
                import traceback
                traceback.print_exc()
            return []


# Simple singleton (unchanged)
_rag_retriever_instance = None

def get_rag_retriever():
    """Get or create the RAGRetriever singleton"""
    global _rag_retriever_instance
    if _rag_retriever_instance is None:
        _rag_retriever_instance = RAGRetriever()
        print("✅ RAGRetriever instance created")
    return _rag_retriever_instance
