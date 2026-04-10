"""
rag_retriever.py
================
Retrieval-Augmented Generation (RAG) retriever for the Kenya Medical Chatbot.

Architecture
------------
The retriever operates in two stages:

1. **Keyword matching** (primary)
   Fast, exact substring matching against each disease's ``common_symptoms``
   text (which is derived directly from linked Symptom objects by the
   populate_kenya_data command, so it never drifts from the M2M links).

2. **TF-IDF semantic similarity** (secondary / tiebreaker)
   When multiple diseases share the same keyword match count, cosine similarity
   on TF-IDF vectors is used to rank them more accurately, and to surface
   diseases that are conceptually relevant even when no exact keyword matches.

Caching
-------
* Disease list (DB + computed vectors): cached for ``DISEASE_CACHE_TTL`` seconds.
* Per-query results: cached for ``QUERY_CACHE_TTL`` seconds.
* Both caches are invalidated by the ``post_save`` signals registered in
  ``populate_kenya_data.py`` (Disease and FirstAidProcedure changes).
* The disease-list cache TTL is intentionally longer than the query cache TTL,
  so the two do not drift (query results are always rebuilt when disease data
  is refreshed).

Thread safety
-------------
The module-level singleton is instantiated once at import time, removing the
race condition that existed in the previous double-checked locking pattern.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Dict, List, Optional

import numpy as np
from django.core.cache import cache
from django.db.models import Prefetch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import Disease, FirstAidProcedure

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISEASE_CACHE_KEY = "rag_diseases_text"
DISEASE_CACHE_TTL = 3_600       # 1 hour
QUERY_CACHE_TTL = 300           # 5 minutes – must be <= DISEASE_CACHE_TTL
TOP_K_RESULTS = 3
MIN_TFIDF_SIMILARITY = 0.05     # Floor below which TF-IDF matches are ignored


# ---------------------------------------------------------------------------
# Internal type aliases
# ---------------------------------------------------------------------------

DiseaseRecord = Dict


# ---------------------------------------------------------------------------
# RAGRetriever
# ---------------------------------------------------------------------------

class RAGRetriever:
    """
    Retrieves first-aid procedures relevant to a set of extracted symptoms.

    Matching pipeline
    -----------------
    1. Exact keyword (substring) match against ``common_symptoms`` text.
    2. TF-IDF cosine similarity as a secondary score for ranking.
    3. Combined score = ``keyword_score`` + ``TFIDF_WEIGHT * tfidf_score``.
    4. Return the top ``TOP_K_RESULTS`` results by combined score.
    """

    TFIDF_WEIGHT = 0.3   # Relative importance of semantic similarity vs exact match

    # ------------------------------------------------------------------
    # Disease data loading (cached)
    # ------------------------------------------------------------------

    def _load_diseases(self) -> List[DiseaseRecord]:
        """
        Return disease data from cache or fetch from the database.

        Each record contains:
            id, name, search_text, first_aid (FirstAidProcedure | None)
        """
        cached = cache.get(DISEASE_CACHE_KEY)
        if cached is not None:
            logger.debug("RAG: serving disease list from cache.")
            return cached

        logger.debug("RAG: disease list cache miss – querying database.")

        diseases = Disease.objects.only("id", "name", "common_symptoms").prefetch_related(
            Prefetch(
                "first_aid_procedures",
                queryset=FirstAidProcedure.objects.only(
                    "disease_id", "steps", "warning_notes", "when_to_seek_help"
                ),
                to_attr="_prefetched_first_aid",
            )
        )

        records: List[DiseaseRecord] = []
        for disease in diseases:
            common = disease.common_symptoms or ""
            search_text = f"{disease.name.lower()} {common.lower()}"
            first_aid_list: list = getattr(disease, "_prefetched_first_aid", [])
            first_aid: Optional[FirstAidProcedure] = first_aid_list[0] if first_aid_list else None

            records.append({
                "id": disease.id,
                "name": disease.name,
                "search_text": search_text,
                "first_aid": first_aid,
            })

        cache.set(DISEASE_CACHE_KEY, records, DISEASE_CACHE_TTL)
        logger.debug("RAG: %d diseases loaded and cached.", len(records))
        return records

    # ------------------------------------------------------------------
    # TF-IDF vectoriser (built on first use, then reused within process)
    # ------------------------------------------------------------------

    def _build_tfidf_matrix(self, records: List[DiseaseRecord]):
        """
        Build a TF-IDF matrix from the disease search texts.
        The vectoriser and matrix are stored as instance attributes so they
        are reused across calls within the same process lifetime.
        Returns (vectorizer, matrix).
        """
        if not hasattr(self, "_vectorizer") or self._vectorizer is None:
            logger.debug("RAG: building TF-IDF matrix for %d diseases.", len(records))
            self._vectorizer = TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                min_df=1,
                sublinear_tf=True,
            )
            corpus = [r["search_text"] for r in records]
            self._tfidf_matrix = self._vectorizer.fit_transform(corpus)
        return self._vectorizer, self._tfidf_matrix

    def _invalidate_tfidf(self) -> None:
        """Drop the cached TF-IDF vectoriser so it is rebuilt on next use."""
        self._vectorizer = None
        self._tfidf_matrix = None

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_score(search_text: str, symptoms: List[str]) -> tuple[float, List[str]]:
        """
        Compute an F1-style keyword score that balances:
        - precision  = matched / disease_symptom_tokens  (avoid over-broad diseases)
        - recall     = matched / user_symptoms            (avoid missing relevant diseases)

        Returns (f1_score, matched_symptoms_list).
        """
        matched = [s for s in symptoms if s in search_text]
        if not matched:
            return 0.0, []

        recall = len(matched) / len(symptoms)
        # Approximate precision: count non-overlapping symptom tokens in search_text
        disease_token_count = max(len(search_text.split()), 1)
        precision = len(matched) / disease_token_count

        if precision + recall == 0:
            return 0.0, matched

        f1 = 2 * precision * recall / (precision + recall)
        return f1, matched

    def _tfidf_scores(
        self,
        query: str,
        records: List[DiseaseRecord],
    ) -> np.ndarray:
        """
        Return a 1-D array of cosine similarities between the query and each
        disease document.
        """
        vectorizer, matrix = self._build_tfidf_matrix(records)
        query_vec = vectorizer.transform([query])
        scores: np.ndarray = cosine_similarity(query_vec, matrix).flatten()
        return scores

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve_relevant_first_aid(
        self,
        user_input: str,
        extracted_symptoms: List[str],
    ) -> List[Dict]:
        """
        Retrieve first-aid procedures relevant to the extracted symptoms.

        Parameters
        ----------
        user_input:
            The raw user message (used as the TF-IDF query string).
        extracted_symptoms:
            A list of symptom strings extracted from the user's message.

        Returns
        -------
        A list of up to ``TOP_K_RESULTS`` dicts, each containing:
            ``disease``, ``confidence``, ``matched_symptoms``, ``first_aid``
        Sorted by descending combined confidence score.
        """
        logger.debug("RAG retrieve called. user_input=%r symptoms=%r", user_input, extracted_symptoms)

        if not extracted_symptoms:
            logger.debug("RAG: no symptoms provided, returning empty result.")
            return []

        # Normalise and deduplicate
        normalised: List[str] = sorted({s.lower().strip() for s in extracted_symptoms if s.strip()})
        if not normalised:
            return []

        # Per-query cache (keyed on the normalised, sorted symptom list)
        query_cache_key = (
            f"rag_result_{hashlib.md5(json.dumps(normalised).encode()).hexdigest()}"
        )
        cached_result = cache.get(query_cache_key)
        if cached_result is not None:
            logger.debug("RAG: serving query result from cache.")
            return cached_result

        try:
            records = self._load_diseases()
            if not records:
                logger.warning("RAG: disease database is empty.")
                return []

            # Build query string for TF-IDF
            tfidf_query = f"{user_input.lower()} {' '.join(normalised)}"
            semantic_scores = self._tfidf_scores(tfidf_query, records)

            results = []
            for idx, record in enumerate(records):
                kw_score, matched = self._keyword_score(record["search_text"], normalised)
                sem_score = float(semantic_scores[idx])

                if kw_score == 0.0 and sem_score < MIN_TFIDF_SIMILARITY:
                    continue  # not relevant enough

                combined = kw_score + self.TFIDF_WEIGHT * sem_score

                logger.debug(
                    "RAG: %s | kw=%.3f sem=%.3f combined=%.3f matched=%s",
                    record["name"], kw_score, sem_score, combined, matched,
                )

                if record["first_aid"] is None:
                    logger.debug("RAG: no first-aid record for %s, skipping.", record["name"])
                    continue

                results.append({
                    "disease": record["name"],
                    "confidence": round(combined, 4),
                    "matched_symptoms": matched,
                    "first_aid": {
                        "steps": record["first_aid"].steps,
                        "warning_notes": record["first_aid"].warning_notes,
                        "when_to_seek_help": record["first_aid"].when_to_seek_help,
                    },
                })

            results.sort(key=lambda r: r["confidence"], reverse=True)
            top_results = results[:TOP_K_RESULTS]

            logger.debug(
                "RAG: %d total matches. Top result: %s (confidence=%.4f)",
                len(results),
                top_results[0]["disease"] if top_results else "none",
                top_results[0]["confidence"] if top_results else 0.0,
            )

            cache.set(query_cache_key, top_results, QUERY_CACHE_TTL)
            return top_results

        except Exception:
            logger.exception("RAG retriever encountered an unexpected error.")
            return []

    def invalidate_caches(self) -> None:
        """
        Clear both the disease-list cache and the in-process TF-IDF state.
        Call this after bulk data changes (e.g. after running populate_kenya_data)
        when the post_save signals have not fired.
        """
        cache.delete(DISEASE_CACHE_KEY)
        self._invalidate_tfidf()
        logger.info("RAG: all caches invalidated.")


# ---------------------------------------------------------------------------
# Module-level singleton  (instantiated once at import time – thread-safe)
# ---------------------------------------------------------------------------

_retriever: RAGRetriever = RAGRetriever()


def get_rag_retriever() -> RAGRetriever:
    """Return the shared RAGRetriever singleton."""
    return _retriever
