# chatbot/views.py
"""
Medical Chatbot Views

Handles chat processing, emergency detection, symptom extraction,
RAG retrieval, user feedback management, and analytics.

Fully aligned with models:
    Disease, Symptom, FirstAidProcedure, EmergencyKeyword,
    UserProfile, ChatSession, ChatMessage, SymptomLog,
    EmergencyLog, FirstAidFeedback, ChatAnalytics
"""

from typing import Dict, List, Optional, Tuple, Any
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from django.db.models import Avg, Count
import json
import logging
import requests
from math import radians, sin, cos, sqrt, atan2
from datetime import date

from .models import (
    ChatSession, ChatMessage, UserProfile,
    SymptomLog, EmergencyLog, FirstAidFeedback,
    ChatAnalytics, Disease, Symptom, FirstAidProcedure, EmergencyKeyword
)
from .nlp_processor import MedicalNLPProcessor
from .rag_retriever import get_rag_retriever

logger = logging.getLogger(__name__)
nlp_processor = MedicalNLPProcessor()

# ============================================================================
# CONSTANTS
# ============================================================================

SEVERITY_LEVELS = {
    'CRITICAL': 3,
    'URGENT': 2,
    'CAUTION': 1
}
MAX_MESSAGE_LENGTH = 5000
MIN_MESSAGE_LENGTH = 1
CONFIDENCE_THRESHOLD = 0.5
CONFIDENCE_LOW_THRESHOLD = 0.5
RATE_LIMIT_SECONDS = 1
NEARBY_HOSPITALS_LIMIT = 10
HOSPITAL_SEARCH_RADIUS = 5000       # metres
HAVERSINE_RADIUS = 6371             # km
API_REQUEST_TIMEOUT = 10            # seconds
MAX_FEEDBACK_LENGTH = 5000
VALID_AGE_GROUPS = {'0-12', '13-17', '18-35', '36-50', '51+', 'unknown'}
VALID_GENDERS = {'male', 'female', 'other', 'unknown'}


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_client_ip(request) -> str:
    """
    Extract client IP address from request.

    Handles X-Forwarded-For header for proxied requests.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_or_create_user_profile(request, session_id: str) -> 'UserProfile':
    """
    Get or create a UserProfile from session_id.

    Updates last_seen on every call and increments total_sessions only
    for genuinely new sessions (first_seen == last_seen within the same
    second is a reasonable proxy, but we use a cache flag instead so we
    don't bump the counter on every page reload within the same session).

    Raises:
        ValidationError: when session_id is empty / None.
    """
    if not session_id:
        raise ValidationError("Session ID is required")

    try:
        profile = UserProfile.objects.get(session_id=session_id)
        profile.last_seen = timezone.now()
        profile.save(update_fields=['last_seen'])
        logger.debug(f"Retrieved existing profile for session {session_id[:8]}")
        return profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(
            session_id=session_id,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        logger.info(f"Created new profile for session {session_id[:8]}")
        return profile


def get_or_create_session(session_id: str, profile: 'UserProfile') -> Tuple['ChatSession', bool]:
    """
    Atomically get or create a ChatSession, ensuring the profile is linked.

    Returns:
        (ChatSession, created: bool)
    """
    with transaction.atomic():
        session, created = ChatSession.objects.get_or_create(
            session_id=session_id,
            defaults={'user_profile': profile}
        )
        if not session.user_profile:
            session.user_profile = profile
            session.save(update_fields=['user_profile'])
    return session, created


def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: Optional[float],
    lon2: Optional[float]
) -> float:
    """
    Haversine distance between two points (km).

    Returns 999_999 when either destination coordinate is None/invalid.
    """
    if lat2 is None or lon2 is None:
        return 999_999

    try:
        lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r
        a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
        return round(HAVERSINE_RADIUS * 2 * atan2(sqrt(a), sqrt(1 - a)), 2)
    except (TypeError, ValueError) as exc:
        logger.error(f"Distance calculation failed: {exc}")
        return 999_999


def format_medical_response(
    disease: str,
    first_aid: Dict[str, Any],
    confidence: float
) -> str:
    """
    Build a structured markdown first-aid response.

    Args:
        disease:    Disease name.
        first_aid:  Dict with keys 'steps', 'warning_notes', 'when_to_seek_help'.
        confidence: RAG confidence score (0–1).

    Returns:
        Formatted string ready for the front-end.
    """
    lines = [
        f"**Based on your symptoms, you may have {disease}**\n",
        f"**First Aid Steps:**\n{first_aid.get('steps', 'N/A')}\n",
    ]

    if first_aid.get('warning_notes'):
        lines.append(f"**⚠️ WARNING:** {first_aid['warning_notes']}\n")

    lines.append(
        f"**When to Seek Help:**\n"
        f"{first_aid.get('when_to_seek_help', 'Consult a healthcare provider')}"
    )

    if confidence < CONFIDENCE_LOW_THRESHOLD:
        lines.append(
            "\n\n*Note: This is a preliminary suggestion with low confidence. "
            "Please consult a healthcare provider.*"
        )

    return "\n".join(lines)


def validate_message(message: str) -> Tuple[bool, Optional[str]]:
    """Return (is_valid, error_message)."""
    if not message or not message.strip():
        return False, "Message cannot be empty"
    if len(message) < MIN_MESSAGE_LENGTH:
        return False, f"Message must be at least {MIN_MESSAGE_LENGTH} character(s)"
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message must not exceed {MAX_MESSAGE_LENGTH} characters"
    return True, None


def check_rate_limit(session_id: str) -> Tuple[bool, Optional[str]]:
    """Simple per-session rate limiter backed by Django cache."""
    cache_key = f"msg_rate_{session_id}"
    if cache.get(cache_key):
        logger.warning(f"Rate limit hit for session {session_id[:8]}")
        return False, "Too many requests. Please wait a moment."
    cache.set(cache_key, True, RATE_LIMIT_SECONDS)
    return True, None


def validate_coordinates(lat: Any, lng: Any) -> Tuple[bool, Optional[str]]:
    """Validate lat/lng values are present and numeric."""
    if lat is None or lng is None:
        return False, "Latitude and longitude are required"
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False, "Latitude and longitude must be numbers"
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return False, "Coordinates are out of valid range"
    return True, None


def _update_daily_analytics(profile: 'UserProfile') -> None:
    """
    Increment or create today's ChatAnalytics row.

    Tracks new vs returning users via a daily cache flag per session.
    Does NOT raise — analytics failures must never break the main flow.
    """
    try:
        today = date.today()
        cache_flag = f"seen_today_{profile.session_id}_{today}"
        is_new_today = not cache.get(cache_flag)

        analytics, _ = ChatAnalytics.objects.get_or_create(date=today)
        analytics.total_users += 1
        if is_new_today:
            if profile.total_sessions <= 1:
                analytics.new_users += 1
            else:
                analytics.returning_users += 1
        analytics.total_messages += 1
        analytics.save()

        if is_new_today:
            cache.set(cache_flag, True, 86400)  # 24 h
    except Exception as exc:
        logger.error(f"Analytics update failed: {exc}", exc_info=True)


def _resolve_session_id(request, data: dict) -> str:
    """
    Resolve session_id from POST body or Django session (creating one if needed).
    """
    session_id = data.get('session_id')
    if not session_id:
        if not request.session.session_key:
            request.session.create()
        session_id = request.session.session_key
    return session_id


# ============================================================================
# VIEWS
# ============================================================================

def chat_interface(request):
    """
    Render the chat interface.

    Creates a new Django session if one doesn't exist, then ensures
    a UserProfile exists for this visitor.
    """
    try:
        if not request.session.session_key:
            request.session.create()

        session_id = request.session.session_key
        profile = get_or_create_user_profile(request, session_id)

        logger.info(f"Chat interface accessed – session {session_id[:8]}")

        return render(request, 'chatbot/chat.html', {
            'session_id': session_id,
            'user_profile': profile,
        })
    except Exception as exc:
        logger.error(f"Error rendering chat interface: {exc}", exc_info=True)
        return render(request, 'chatbot/error.html', {
            'error': 'Unable to load the chat interface. Please try again.'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_message(request):
    """
    Core message-processing endpoint.

    Pipeline:
        1. Parse & validate request
        2. Rate-limit check
        3. Resolve / create UserProfile + ChatSession
        4. Persist user ChatMessage
        5. NLP – tokenise & extract symptoms
        6. Emergency detection (EmergencyKeyword table + NLP)
        7. RAG retrieval → FirstAidProcedure
        8. Persist SymptomLog (with matched_diseases as JSON)
        9. Build & persist bot ChatMessage
       10. Update ChatAnalytics

    Request JSON
    ───────────
    {
        "message":    str  (1–5000 chars, required),
        "session_id": str  (optional – falls back to Django session)
    }

    Response JSON (normal)
    ──────────────────────
    {
        "type": "normal",
        "message": str,
        "symptoms_detected": [str, ...],
        "session_id": str
    }

    Response JSON (emergency)
    ─────────────────────────
    {
        "type": "emergency",
        "severity": str,
        "message": str,
        "emergencies": [{...}, ...],
        "action": "request_location",
        "emergency_id": int | null
    }

    Response JSON (error)
    ─────────────────────
    { "type": "error", "message": str }
    """
    logger.info("process_message called")

    try:
        # ── 1. Parse ──────────────────────────────────────────────────────────
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'type': 'error', 'message': 'Invalid JSON body'}, status=400)

        user_message = body.get('message', '').strip()
        session_id = _resolve_session_id(request, body)

        # ── 2. Validate ───────────────────────────────────────────────────────
        is_valid, err = validate_message(user_message)
        if not is_valid:
            return JsonResponse({'type': 'error', 'message': err}, status=400)

        # ── 3. Rate limit ─────────────────────────────────────────────────────
        allowed, rate_err = check_rate_limit(session_id)
        if not allowed:
            return JsonResponse({'type': 'error', 'message': rate_err}, status=429)

        # ── 4. Profile + Session ──────────────────────────────────────────────
        profile = get_or_create_user_profile(request, session_id)
        session, session_created = get_or_create_session(session_id, profile)
        logger.debug(f"Session {'created' if session_created else 'retrieved'}: {session_id[:8]}")

        # ── 5. Persist user message ───────────────────────────────────────────
        user_msg = ChatMessage.objects.create(
            session=session,
            user_profile=profile,
            role='user',
            content=user_message
        )

        # ── 6. NLP ────────────────────────────────────────────────────────────
        symptoms: List[str] = []
        try:
            nlp_processor.preprocess(user_message)        # side-effects / warm-up
            symptoms = nlp_processor.extract_symptoms(user_message)
            logger.debug(f"Symptoms extracted: {symptoms}")
        except Exception as exc:
            logger.error(f"NLP error: {exc}", exc_info=True)

        # ── 7. Emergency detection ────────────────────────────────────────────
        emergencies: List[Dict] = []
        try:
            emergencies = nlp_processor.detect_emergency(user_message)
        except Exception as exc:
            logger.error(f"Emergency detection error: {exc}", exc_info=True)

        # Also cross-check against EmergencyKeyword table (models.py source of truth)
        if not emergencies:
            lower_msg = user_message.lower()
            db_keywords = EmergencyKeyword.objects.all()
            for ek in db_keywords:
                if ek.keyword.lower() in lower_msg:
                    emergencies.append({
                        'keyword': ek.keyword,
                        'severity': ek.severity,
                        'message': ek.response_message,
                    })

        if emergencies:
            emergencies.sort(
                key=lambda x: SEVERITY_LEVELS.get(x.get('severity', ''), 0),
                reverse=True
            )
            top = emergencies[0]
            logger.warning(f"EMERGENCY DETECTED – severity={top['severity']}")

            # Mark message
            user_msg.emergency_detected = True
            user_msg.save(update_fields=['emergency_detected'])

            # Persist EmergencyLog
            emergency_log = None
            try:
                emergency_log = EmergencyLog.objects.create(
                    user_profile=profile,
                    emergency_keywords=[e.get('keyword') for e in emergencies],
                    severity=top['severity'],
                    raw_input=user_message,
                    # location fields remain null until the client responds
                )
            except Exception as exc:
                logger.error(f"EmergencyLog creation failed: {exc}", exc_info=True)

            _update_daily_analytics(profile)

            return JsonResponse({
                'type': 'emergency',
                'severity': top['severity'],
                'message': top.get('message', ''),
                'emergencies': emergencies,
                'action': 'request_location',
                'emergency_id': emergency_log.id if emergency_log else None,
            })

        # ── 8. RAG retrieval ──────────────────────────────────────────────────
        first_aid_results: List[Dict] = []
        matched_diseases: List[Dict] = []

        if symptoms:
            try:
                rag = get_rag_retriever()
                first_aid_results = rag.retrieve_relevant_first_aid(user_message, symptoms)
                matched_diseases = [
                    {'name': r['disease'], 'confidence': r['confidence']}
                    for r in first_aid_results
                ]
                logger.info(f"RAG returned {len(first_aid_results)} match(es)")
            except (ConnectionError, TimeoutError) as exc:
                logger.error(f"RAG service unavailable: {exc}")
            except Exception as exc:
                logger.error(f"RAG error: {exc}", exc_info=True)

            # Persist SymptomLog (matched_diseases stored as JSON list)
            try:
                SymptomLog.objects.create(
                    user_profile=profile,
                    symptoms=symptoms,
                    raw_input=user_message,
                    matched_diseases=matched_diseases,   # JSONField – list[dict]
                )
            except Exception as exc:
                logger.error(f"SymptomLog creation failed: {exc}", exc_info=True)
        else:
            logger.debug("No symptoms extracted – skipping RAG")

        # ── 9. Build response text ────────────────────────────────────────────
        if first_aid_results:
            best = first_aid_results[0]
            response_text = format_medical_response(
                best['disease'],
                best['first_aid'],
                best['confidence']
            )
        elif symptoms:
            response_text = (
                f"I identified these symptoms: {', '.join(symptoms)}. "
                "However, I couldn't match them to a specific condition in my database. "
                "Please provide more detail or consult a healthcare provider."
            )
        else:
            response_text = (
                "I couldn't identify any specific symptoms from your message. "
                "Please describe how you're feeling – for example: "
                "'I have a fever, headache, and body aches'."
            )

        # ── 10. Persist bot message ───────────────────────────────────────────
        try:
            ChatMessage.objects.create(
                session=session,
                user_profile=profile,
                role='bot',
                content=response_text
            )
        except Exception as exc:
            logger.error(f"Bot ChatMessage save failed: {exc}", exc_info=True)

        _update_daily_analytics(profile)

        return JsonResponse({
            'type': 'normal',
            'message': response_text,
            'symptoms_detected': symptoms,
            'session_id': session_id,
        })

    except ValidationError as exc:
        logger.warning(f"Validation error: {exc}")
        return JsonResponse({'type': 'error', 'message': str(exc)}, status=400)
    except Exception as exc:
        logger.error(f"Unhandled error in process_message: {exc}", exc_info=True)
        return JsonResponse({
            'type': 'error',
            'message': 'An error occurred while processing your message. Please try again.',
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def get_nearby_hospitals(request):
    """
    Fetch nearby hospitals / clinics via OpenStreetMap Overpass API.

    Updates EmergencyLog with location and hospital count when
    emergency_id is supplied.

    Request JSON
    ───────────
    {
        "latitude":     float  (required),
        "longitude":    float  (required),
        "session_id":   str    (optional),
        "emergency_id": int    (optional)
    }

    Response JSON
    ─────────────
    {
        "hospitals": [
            {
                "name": str,
                "lat": float,
                "lon": float,
                "address": str,
                "phone": str,
                "distance": float   // km
            },
            ...
        ],
        "user_location": {"lat": float, "lng": float}
    }
    """
    logger.info("get_nearby_hospitals called")

    try:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body'}, status=400)

        lat = body.get('latitude')
        lng = body.get('longitude')
        emergency_id = body.get('emergency_id')

        # Validate coordinates
        coords_ok, coord_err = validate_coordinates(lat, lng)
        if not coords_ok:
            return JsonResponse({'error': coord_err}, status=400)

        logger.debug(f"Hospital search – lat={lat}, lng={lng}")

        # ── Update EmergencyLog with location ─────────────────────────────────
        if emergency_id:
            try:
                em_log = EmergencyLog.objects.get(id=emergency_id)
                em_log.location_shared = True
                em_log.latitude = lat
                em_log.longitude = lng
                em_log.save(update_fields=['location_shared', 'latitude', 'longitude'])
                logger.info(f"EmergencyLog {emergency_id} updated with location")

                # Also bump ChatAnalytics.location_shares
                try:
                    analytics, _ = ChatAnalytics.objects.get_or_create(date=date.today())
                    analytics.location_shares += 1
                    analytics.save(update_fields=['location_shares'])
                except Exception as exc:
                    logger.error(f"Analytics location_shares update failed: {exc}")

            except EmergencyLog.DoesNotExist:
                logger.warning(f"EmergencyLog id={emergency_id} not found")
            except Exception as exc:
                logger.error(f"EmergencyLog location update failed: {exc}", exc_info=True)

        # ── Overpass API query ─────────────────────────────────────────────────
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:{HOSPITAL_SEARCH_RADIUS},{lat},{lng});
          node["amenity"="clinic"](around:{HOSPITAL_SEARCH_RADIUS},{lat},{lng});
          node["healthcare"](around:{HOSPITAL_SEARCH_RADIUS},{lat},{lng});
        );
        out body;
        """

        try:
            resp = requests.post(
                overpass_url,
                data={'data': overpass_query},   # Overpass expects form data
                timeout=API_REQUEST_TIMEOUT
            )
            resp.raise_for_status()
            osm_data = resp.json()
        except requests.Timeout:
            logger.error("Overpass API timed out")
            return JsonResponse(
                {'error': 'Hospital search is temporarily unavailable (timeout)'},
                status=503
            )
        except requests.RequestException as exc:
            logger.error(f"Overpass API error: {exc}")
            return JsonResponse(
                {'error': 'Unable to fetch hospital data'},
                status=503
            )

        # ── Process results ───────────────────────────────────────────────────
        hospitals = []
        for element in osm_data.get('elements', []):
            try:
                tags = element.get('tags', {})
                hospitals.append({
                    'name': tags.get('name', 'Medical Facility'),
                    'lat': element.get('lat'),
                    'lon': element.get('lon'),
                    'address': tags.get('addr:street', 'Address unavailable'),
                    'phone': tags.get('phone') or tags.get('contact:phone', ''),
                    'distance': calculate_distance(
                        lat, lng,
                        element.get('lat'),
                        element.get('lon')
                    ),
                })
            except (KeyError, TypeError) as exc:
                logger.debug(f"Skipping malformed element: {exc}")

        hospitals.sort(key=lambda h: h['distance'])
        hospitals = hospitals[:NEARBY_HOSPITALS_LIMIT]
        logger.info(f"{len(hospitals)} hospital(s) found")

        # ── Update EmergencyLog with count ────────────────────────────────────
        if emergency_id:
            try:
                em_log = EmergencyLog.objects.get(id=emergency_id)
                em_log.nearby_hospitals_shown = len(hospitals)
                em_log.save(update_fields=['nearby_hospitals_shown'])
            except EmergencyLog.DoesNotExist:
                pass
            except Exception as exc:
                logger.error(f"EmergencyLog hospital-count update failed: {exc}")

        return JsonResponse({
            'hospitals': hospitals,
            'user_location': {'lat': lat, 'lng': lng},
        })

    except Exception as exc:
        logger.error(f"Unhandled error in get_nearby_hospitals: {exc}", exc_info=True)
        return JsonResponse(
            {'error': 'An error occurred while searching for hospitals'},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def submit_feedback(request):
    """
    Save a FirstAidFeedback record.

    Validates rating (1–5), links to the most recent SymptomLog for the
    session, and updates ChatAnalytics.average_rating.

    Request JSON
    ───────────
    {
        "session_id": str  (required),
        "disease":    str  (optional),
        "rating":     int  (required, 1–5),
        "feedback":   str  (optional, ≤5000 chars)
    }

    Response JSON
    ─────────────
    { "status": "success", "feedback_id": int }
    """
    logger.info("submit_feedback called")

    try:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body'}, status=400)

        session_id = body.get('session_id', '').strip()
        disease_name = body.get('disease', '').strip()
        rating = body.get('rating')
        feedback_text = body.get('feedback', '').strip()

        # ── Validate ───────────────────────────────────────────────────────────
        if not session_id:
            return JsonResponse({'error': 'session_id is required'}, status=400)

        if rating is None or not isinstance(rating, int) or not (1 <= rating <= 5):
            return JsonResponse(
                {'error': 'rating must be an integer between 1 and 5'},
                status=400
            )

        if len(feedback_text) > MAX_FEEDBACK_LENGTH:
            return JsonResponse(
                {'error': f'Feedback must not exceed {MAX_FEEDBACK_LENGTH} characters'},
                status=400
            )

        # ── Resolve UserProfile ────────────────────────────────────────────────
        try:
            profile = UserProfile.objects.get(session_id=session_id)
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': 'User profile not found'}, status=404)

        # ── Link most recent SymptomLog ────────────────────────────────────────
        symptom_log = (
            SymptomLog.objects
            .filter(user_profile=profile)
            .order_by('-timestamp')
            .first()
        )

        # ── Persist feedback ───────────────────────────────────────────────────
        feedback = FirstAidFeedback.objects.create(
            user_profile=profile,
            symptom_log=symptom_log,
            disease_name=disease_name,
            response_given='',          # populated if caller supplies it in future
            rating=rating,
            feedback_text=feedback_text,
        )
        logger.info(f"Feedback id={feedback.id} saved – rating={rating}")

        # ── Update analytics average_rating ───────────────────────────────────
        try:
            analytics, _ = ChatAnalytics.objects.get_or_create(date=date.today())
            agg = FirstAidFeedback.objects.filter(
                timestamp__date=date.today()
            ).aggregate(avg=Avg('rating'))
            analytics.average_rating = agg.get('avg') or 0.0
            analytics.save(update_fields=['average_rating'])
        except Exception as exc:
            logger.error(f"Analytics rating update failed: {exc}", exc_info=True)

        return JsonResponse({'status': 'success', 'feedback_id': feedback.id})

    except Exception as exc:
        logger.error(f"Unhandled error in submit_feedback: {exc}", exc_info=True)
        return JsonResponse(
            {'error': 'An error occurred while submitting feedback'},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def update_user_profile(request):
    """
    Allow users to optionally update their demographic profile.

    Request JSON
    ───────────
    {
        "session_id": str  (required),
        "age_group":  str  (optional) – one of UserProfile.age_group choices,
        "gender":     str  (optional) – one of UserProfile.gender choices,
        "location":   str  (optional) – city/region in Kenya, ≤200 chars
    }

    Response JSON
    ─────────────
    { "status": "updated", "profile_id": str }
    """
    try:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body'}, status=400)

        session_id = body.get('session_id', '').strip()
        if not session_id:
            return JsonResponse({'error': 'session_id is required'}, status=400)

        try:
            profile = UserProfile.objects.get(session_id=session_id)
        except UserProfile.DoesNotExist:
            return JsonResponse({'error': 'User profile not found'}, status=404)

        update_fields = []

        age_group = body.get('age_group')
        if age_group is not None:
            if age_group not in VALID_AGE_GROUPS:
                return JsonResponse(
                    {'error': f'Invalid age_group. Choose from: {sorted(VALID_AGE_GROUPS)}'},
                    status=400
                )
            profile.age_group = age_group
            update_fields.append('age_group')

        gender = body.get('gender')
        if gender is not None:
            if gender not in VALID_GENDERS:
                return JsonResponse(
                    {'error': f'Invalid gender. Choose from: {sorted(VALID_GENDERS)}'},
                    status=400
                )
            profile.gender = gender
            update_fields.append('gender')

        location = body.get('location')
        if location is not None:
            location = location.strip()
            if len(location) > 200:
                return JsonResponse(
                    {'error': 'Location must not exceed 200 characters'},
                    status=400
                )
            profile.location = location
            update_fields.append('location')

        if update_fields:
            profile.save(update_fields=update_fields)
            logger.info(f"Profile {session_id[:8]} updated: {update_fields}")

        return JsonResponse({'status': 'updated', 'profile_id': str(profile.session_id)})

    except Exception as exc:
        logger.error(f"Error in update_user_profile: {exc}", exc_info=True)
        return JsonResponse({'error': 'Unable to update profile'}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def get_chat_history(request):
    """
    Return the last N ChatMessages for a session.

    Query params:
        session_id  (required)
        limit       (optional, default=20, max=100)

    Response JSON
    ─────────────
    {
        "messages": [
            {
                "role": "user"|"bot",
                "content": str,
                "timestamp": str (ISO 8601),
                "emergency_detected": bool
            },
            ...
        ]
    }
    """
    session_id = request.GET.get('session_id', '').strip()
    if not session_id:
        return JsonResponse({'error': 'session_id is required'}, status=400)

    try:
        limit = min(int(request.GET.get('limit', 20)), 100)
    except (ValueError, TypeError):
        limit = 20

    try:
        session = ChatSession.objects.get(session_id=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({'messages': []})

    messages = (
        session.messages
        .order_by('-timestamp')[:limit]
    )

    return JsonResponse({
        'messages': [
            {
                'role': m.role,
                'content': m.content,
                'timestamp': m.timestamp.isoformat(),
                'emergency_detected': m.emergency_detected,
            }
            for m in reversed(list(messages))
        ]
    })


@csrf_exempt
@require_http_methods(["GET"])
def get_analytics_summary(request):
    """
    Return aggregated analytics for a date range (staff-only endpoint).

    Query params:
        start_date  YYYY-MM-DD (optional, defaults to today)
        end_date    YYYY-MM-DD (optional, defaults to today)

    Response JSON
    ─────────────
    {
        "summary": {
            "total_users": int,
            "new_users": int,
            "returning_users": int,
            "total_messages": int,
            "emergency_detections": int,
            "location_shares": int,
            "average_rating": float,
            "top_diseases": {}
        }
    }
    """
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    today_str = date.today().isoformat()
    start_str = request.GET.get('start_date', today_str)
    end_str = request.GET.get('end_date', today_str)

    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

    rows = ChatAnalytics.objects.filter(date__range=(start, end))

    summary = {
        'total_users': sum(r.total_users for r in rows),
        'new_users': sum(r.new_users for r in rows),
        'returning_users': sum(r.returning_users for r in rows),
        'total_messages': sum(r.total_messages for r in rows),
        'emergency_detections': sum(r.emergency_detections for r in rows),
        'location_shares': sum(r.location_shares for r in rows),
        'average_rating': (
            round(sum(r.average_rating for r in rows) / len(rows), 2)
            if rows else 0.0
        ),
        'top_diseases': {},
    }

    # Merge top_diseases dicts from each day
    for row in rows:
        for disease, count in (row.top_diseases or {}).items():
            summary['top_diseases'][disease] = (
                summary['top_diseases'].get(disease, 0) + count
            )

    return JsonResponse({'summary': summary})
