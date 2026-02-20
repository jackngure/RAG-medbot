# chatbot/views.py
"""
Medical Chatbot Views

Handles chat processing, emergency detection, symptom extraction,
RAG retrieval, and user feedback management.
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
import json
import traceback
import logging
import requests
from math import radians, sin, cos, sqrt, atan2

from .models import (
    ChatSession, ChatMessage, UserProfile, 
    SymptomLog, EmergencyLog, FirstAidFeedback
)
from .nlp_processor import MedicalNLPProcessor
from .rag_retriever import get_rag_retriever

logger = logging.getLogger(__name__)
nlp_processor = MedicalNLPProcessor()

# Constants
SEVERITY_LEVELS = {
    'CRITICAL': 3,
    'URGENT': 2,
    'CAUTION': 1
}
MAX_MESSAGE_LENGTH = 5000
MIN_MESSAGE_LENGTH = 1
CONFIDENCE_THRESHOLD = 0.5
RATE_LIMIT_SECONDS = 1
NEARBY_HOSPITALS_LIMIT = 10
HOSPITAL_SEARCH_RADIUS = 5000  # meters
HAVERSINE_RADIUS = 6371  # km
API_REQUEST_TIMEOUT = 10  # seconds
CONFIDENCE_LOW_THRESHOLD = 0.5


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_client_ip(request) -> str:
    """
    Extract client IP address from request.
    
    Handles X-Forwarded-For header for proxied requests.
    
    Args:
        request: Django request object
        
    Returns:
        str: Client IP address
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def get_or_create_user_profile(request, session_id: str) -> 'UserProfile':
    """
    Get or create user profile from session.
    
    Creates new profile if not exists, updates last_seen timestamp.
    
    Args:
        request: Django request object
        session_id: User session identifier
        
    Returns:
        UserProfile: User profile instance
        
    Raises:
        ValidationError: If session_id is invalid
    """
    if not session_id:
        raise ValidationError("Session ID is required")
    
    try:
        profile = UserProfile.objects.get(session_id=session_id)
        # Update last seen
        profile.last_seen = timezone.now()
        profile.save(update_fields=['last_seen'])
        logger.debug(f"Retrieved existing profile for session {session_id}")
        return profile
    except UserProfile.DoesNotExist:
        # Create new profile
        profile = UserProfile.objects.create(
            session_id=session_id,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        logger.info(f"Created new profile for session {session_id}")
        return profile


def calculate_distance(
    lat1: float, 
    lon1: float, 
    lat2: Optional[float], 
    lon2: Optional[float]
) -> float:
    """
    Calculate distance between two geographic points using Haversine formula.
    
    Args:
        lat1, lon1: Starting coordinates
        lat2, lon2: Ending coordinates
        
    Returns:
        float: Distance in kilometers (999999 if coordinates invalid)
    """
    if lat2 is None or lon2 is None:
        logger.warning("Invalid destination coordinates for distance calculation")
        return 999999
    
    try:
        lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(
            radians, [lat1, lon1, lat2, lon2]
        )
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return round(HAVERSINE_RADIUS * c, 2)
    except (TypeError, ValueError) as e:
        logger.error(f"Error calculating distance: {e}")
        return 999999


def format_medical_response(
    disease: str,
    first_aid: Dict[str, Any],
    confidence: float
) -> str:
    """
    Format first aid response with structured information.
    
    Args:
        disease: Disease name
        first_aid: Dictionary containing 'steps', 'warning_notes', 'when_to_seek_help'
        confidence: Confidence score (0-1)
        
    Returns:
        str: Formatted markdown response
    """
    response = f"**Based on your symptoms, you may have {disease}**\n\n"
    response += f"**First Aid Steps:**\n{first_aid.get('steps', 'N/A')}\n\n"
    
    if first_aid.get('warning_notes'):
        response += f"**⚠️ WARNING:** {first_aid['warning_notes']}\n\n"
    
    response += f"**When to Seek Help:**\n{first_aid.get('when_to_seek_help', 'Consult a healthcare provider')}"
    
    if confidence < CONFIDENCE_LOW_THRESHOLD:
        response += "\n\n*Note: This is a preliminary suggestion with low confidence. Please consult a healthcare provider.*"
    
    return response


def validate_message(message: str) -> Tuple[bool, Optional[str]]:
    """
    Validate user message format and length.
    
    Args:
        message: User input message
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if not message or not message.strip():
        return False, "Message cannot be empty"
    
    if len(message) < MIN_MESSAGE_LENGTH:
        return False, f"Message must be at least {MIN_MESSAGE_LENGTH} characters"
    
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message must not exceed {MAX_MESSAGE_LENGTH} characters"
    
    return True, None


def check_rate_limit(session_id: str) -> Tuple[bool, Optional[str]]:
    """
    Check if user has exceeded rate limit.
    
    Args:
        session_id: User session identifier
        
    Returns:
        Tuple[bool, str]: (allowed, error_message)
    """
    cache_key = f"msg_rate_{session_id}"
    
    if cache.get(cache_key):
        logger.warning(f"Rate limit exceeded for session {session_id}")
        return False, "Too many requests. Please wait a moment."
    
    cache.set(cache_key, True, RATE_LIMIT_SECONDS)
    return True, None


# ============================================================================
# VIEW FUNCTIONS
# ============================================================================

def chat_interface(request):
    """
    Render the chat interface template.
    
    Creates a new session if not exists and generates session ID.
    
    Args:
        request: Django request object
        
    Returns:
        HttpResponse: Rendered chat template
    """
    try:
        # Generate or get session ID
        if not request.session.session_key:
            request.session.create()
        
        session_id = request.session.session_key
        profile = get_or_create_user_profile(request, session_id)
        
        logger.info(f"User accessed chat interface with session {session_id}")
        
        return render(request, 'chatbot/chat.html', {
            'session_id': session_id,
            'user_profile': profile
        })
    except Exception as e:
        logger.error(f"Error rendering chat interface: {e}", exc_info=True)
        return render(request, 'chatbot/error.html', {
            'error': 'Unable to load chat interface'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def process_message(request):
    """
    Process user messages with emergency detection and RAG retrieval.
    
    Request JSON:
        {
            'message': str (required) - User's medical question (1-5000 chars)
            'session_id': str (optional) - Session identifier
        }
    
    Response JSON:
        Normal response:
            {
                'type': 'normal',
                'message': str,
                'symptoms_detected': List[str],
                'session_id': str
            }
        Emergency response:
            {
                'type': 'emergency',
                'severity': str,
                'message': str,
                'emergencies': List[Dict],
                'action': str,
                'emergency_id': int
            }
        Error response:
            {
                'type': 'error',
                'message': str
            }
    
    Args:
        request: Django POST request
        
    Returns:
        JsonResponse: Response with message type and content
    """
    logger.info("Processing new message request")
    
    try:
        # Parse and validate request
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id') or request.session.session_key
        
        # Validate message format
        is_valid, error_msg = validate_message(user_message)
        if not is_valid:
            logger.warning(f"Invalid message: {error_msg}")
            return JsonResponse({
                'type': 'error',
                'message': error_msg
            }, status=400)
        
        # Check rate limiting
        allowed, rate_limit_msg = check_rate_limit(session_id)
        if not allowed:
            return JsonResponse({
                'type': 'error',
                'message': rate_limit_msg
            }, status=429)
        
        logger.debug(f"User message: {user_message[:100]}...")
        logger.debug(f"Session ID: {session_id}")
        
        # Get or create user profile
        profile = get_or_create_user_profile(request, session_id)
        
        # Get or create session
        with transaction.atomic():
            session, created = ChatSession.objects.get_or_create(
                session_id=session_id,
                defaults={'user_profile': profile}
            )
            if not session.user_profile:
                session.user_profile = profile
                session.save(update_fields=['user_profile'])
            
            logger.debug(f"Session {'created' if created else 'retrieved'}")
            
            # Save user message
            user_msg = ChatMessage.objects.create(
                session=session,
                user_profile=profile,
                role='user',
                content=user_message
            )
            logger.debug(f"Saved user message ID: {user_msg.id}")
        
        # Step 1: NLP Processing
        logger.info("Starting NLP processing")
        try:
            tokens = nlp_processor.preprocess(user_message)
            symptoms = nlp_processor.extract_symptoms(user_message)
            logger.debug(f"Tokens count: {len(tokens)}")
            logger.debug(f"Symptoms extracted: {symptoms}")
        except Exception as e:
            logger.error(f"NLP processing error: {e}", exc_info=True)
            symptoms = []
            tokens = []
        
        # Step 2: Emergency Detection
        logger.info("Checking for emergency indicators")
        emergencies = []
        try:
            emergencies = nlp_processor.detect_emergency(user_message)
            logger.debug(f"Emergencies detected: {emergencies}")
        except Exception as e:
            logger.error(f"Emergency detection error: {e}", exc_info=True)
        
        if emergencies:
            logger.warning(f"⚠️  EMERGENCY DETECTED: {emergencies[0]['severity']}")
            
            # Sort by severity
            emergencies.sort(
                key=lambda x: SEVERITY_LEVELS.get(x['severity'], 0),
                reverse=True
            )
            
            # Log emergency
            try:
                emergency_log = EmergencyLog.objects.create(
                    user_profile=profile,
                    emergency_keywords=[e['keyword'] for e in emergencies],
                    severity=emergencies[0]['severity'],
                    raw_input=user_message
                )
                logger.info(f"Emergency logged with ID: {emergency_log.id}")
            except Exception as e:
                logger.error(f"Failed to log emergency: {e}", exc_info=True)
                emergency_log = None
            
            # Mark message as emergency
            user_msg.emergency_detected = True
            user_msg.save(update_fields=['emergency_detected'])
            
            return JsonResponse({
                'type': 'emergency',
                'severity': emergencies[0]['severity'],
                'message': emergencies[0]['message'],
                'emergencies': emergencies,
                'action': 'request_location',
                'emergency_id': emergency_log.id if emergency_log else None
            })
        
        # Step 3: RAG Retrieval
        logger.info("Starting RAG retrieval")
        first_aid_results = []
        matched_diseases = []
        
        if symptoms:
            try:
                rag_retriever = get_rag_retriever()
                logger.debug("RAG retriever obtained")
                
                first_aid_results = rag_retriever.retrieve_relevant_first_aid(
                    user_message, symptoms
                )
                logger.info(f"RAG returned {len(first_aid_results)} matches")
                
                # Track matched diseases
                matched_diseases = [
                    {
                        'name': result['disease'],
                        'confidence': result['confidence']
                    }
                    for result in first_aid_results
                ]
            except (ConnectionError, TimeoutError) as e:
                logger.error(f"RAG service unavailable: {e}")
                first_aid_results = []
            except Exception as e:
                logger.error(f"RAG retrieval error: {e}", exc_info=True)
                first_aid_results = []
        else:
            logger.debug("No symptoms extracted for RAG matching")
        
        # Log symptoms
        if symptoms:
            try:
                symptom_log = SymptomLog.objects.create(
                    user_profile=profile,
                    symptoms=symptoms,
                    raw_input=user_message,
                    matched_diseases=matched_diseases
                )
                logger.debug(f"Symptom log created: {symptom_log.id}")
            except Exception as e:
                logger.error(f"Failed to log symptoms: {e}", exc_info=True)
        
        # Step 4: Generate Response
        logger.info("Generating response")
        if first_aid_results:
            best_match = first_aid_results[0]
            logger.debug(f"Best match: {best_match['disease']} (confidence: {best_match['confidence']})")
            
            response = format_medical_response(
                best_match['disease'],
                best_match['first_aid'],
                best_match['confidence']
            )
        else:
            if symptoms:
                response = (
                    f"I found these symptoms: {', '.join(symptoms)}. "
                    f"However, I couldn't match them to a specific condition in my database. "
                    f"Please provide more details or consult a healthcare provider for a proper diagnosis."
                )
                logger.debug("No disease matches found for extracted symptoms")
            else:
                response = (
                    "I couldn't identify any specific symptoms. "
                    "Please describe how you're feeling. For example: "
                    "'I have fever, headache, and body aches'"
                )
                logger.debug("No symptoms identified in user message")
        
        logger.debug(f"Response generated: {len(response)} characters")
        
        # Save bot response
        try:
            bot_msg = ChatMessage.objects.create(
                session=session,
                user_profile=profile,
                role='bot',
                content=response
            )
            logger.debug(f"Saved bot message ID: {bot_msg.id}")
        except Exception as e:
            logger.error(f"Failed to save bot message: {e}", exc_info=True)
        
        return JsonResponse({
            'type': 'normal',
            'message': response,
            'symptoms_detected': symptoms,
            'session_id': session_id
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({
            'type': 'error',
            'message': 'Invalid request format'
        }, status=400)
    except ValidationError as e:
        logger.warning(f"Validation error: {e}")
        return JsonResponse({
            'type': 'error',
            'message': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Unhandled error in process_message: {e}", exc_info=True)
        return JsonResponse({
            'type': 'error',
            'message': 'An error occurred while processing your message. Please try again.'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def get_nearby_hospitals(request):
    """
    Get nearby hospitals from OpenStreetMap Overpass API.
    
    Request JSON:
        {
            'latitude': float (required),
            'longitude': float (required),
            'session_id': str (optional),
            'emergency_id': int (optional)
        }
    
    Response JSON:
        {
            'hospitals': List[Dict],
            'user_location': {'lat': float, 'lng': float}
        }
    
    Hospital Dict:
        {
            'name': str,
            'lat': float,
            'lon': float,
            'address': str,
            'phone': str,
            'distance': float (km)
        }
    
    Args:
        request: Django POST request
        
    Returns:
        JsonResponse: List of nearby hospitals or error
    """
    logger.info("Processing hospital search request")
    
    try:
        data = json.loads(request.body)
        lat = data.get('latitude')
        lng = data.get('longitude')
        session_id = data.get('session_id')
        emergency_id = data.get('emergency_id')
        
        # Validate coordinates
        if lat is None or lng is None:
            logger.warning("Location not provided in hospital search")
            return JsonResponse(
                {'error': 'Latitude and longitude are required'},
                status=400
            )
        
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            logger.warning("Invalid coordinate types")
            return JsonResponse(
                {'error': 'Latitude and longitude must be numbers'},
                status=400
            )
        
        logger.debug(f"Hospital search for coordinates: {lat}, {lng}")
        
        # Update emergency log with location
        if emergency_id:
            try:
                emergency_log = EmergencyLog.objects.get(id=emergency_id)
                emergency_log.location_shared = True
                emergency_log.latitude = lat
                emergency_log.longitude = lng
                emergency_log.save(update_fields=['location_shared', 'latitude', 'longitude'])
                logger.info(f"Updated emergency log {emergency_id} with location")
            except EmergencyLog.DoesNotExist:
                logger.warning(f"Emergency log {emergency_id} not found")
            except Exception as e:
                logger.error(f"Failed to update emergency log: {e}")
        
        # Query OpenStreetMap Overpass API
        logger.debug("Querying Overpass API for hospitals")
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
            response = requests.post(
                overpass_url,
                data=overpass_query,
                timeout=API_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout:
            logger.error("Overpass API request timeout")
            return JsonResponse(
                {'error': 'Hospital search service is temporarily unavailable'},
                status=503
            )
        except requests.RequestException as e:
            logger.error(f"Overpass API request error: {e}")
            return JsonResponse(
                {'error': 'Unable to fetch hospital data'},
                status=503
            )
        
        # Process hospital results
        hospitals = []
        for element in data.get('elements', []):
            try:
                hospital_data = {
                    'name': element.get('tags', {}).get('name', 'Medical Facility'),
                    'lat': element.get('lat'),
                    'lon': element.get('lon'),
                    'address': element.get('tags', {}).get('addr:street', 'Address unavailable'),
                    'phone': element.get('tags', {}).get('phone', ''),
                    'distance': calculate_distance(lat, lng, element.get('lat'), element.get('lon'))
                }
                hospitals.append(hospital_data)
            except (KeyError, TypeError) as e:
                logger.debug(f"Skipping malformed hospital data: {e}")
                continue
        
        # Sort by distance and limit results
        hospitals.sort(key=lambda x: x['distance'])
        hospitals = hospitals[:NEARBY_HOSPITALS_LIMIT]
        
        logger.info(f"Found {len(hospitals)} nearby hospitals")
        
        # Update emergency log with hospital count
        if emergency_id:
            try:
                emergency_log = EmergencyLog.objects.get(id=emergency_id)
                emergency_log.nearby_hospitals_shown = len(hospitals)
                emergency_log.save(update_fields=['nearby_hospitals_shown'])
            except EmergencyLog.DoesNotExist:
                logger.debug(f"Emergency log {emergency_id} not found for update")
            except Exception as e:
                logger.error(f"Failed to update hospital count: {e}")
        
        return JsonResponse({
            'hospitals': hospitals,
            'user_location': {'lat': lat, 'lng': lng}
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in hospital request")
        return JsonResponse(
            {'error': 'Invalid request format'},
            status=400
        )
    except Exception as e:
        logger.error(f"Unhandled error in get_nearby_hospitals: {e}", exc_info=True)
        return JsonResponse(
            {'error': 'An error occurred while searching for hospitals'},
            status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def submit_feedback(request):
    """
    Submit user feedback on first aid response.
    
    Request JSON:
        {
            'session_id': str (required),
            'disease': str (optional),
            'rating': int (required) - 1-5,
            'feedback': str (optional)
        }
    
    Response JSON:
        {
            'status': 'success',
            'feedback_id': int
        }
    
    Args:
        request: Django POST request
        
    Returns:
        JsonResponse: Success status with feedback ID
    """
    logger.info("Processing feedback submission")
    
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        disease_name = data.get('disease', '')
        rating = data.get('rating')
        feedback_text = data.get('feedback', '')
        
        # Validate required fields
        if not session_id:
            logger.warning("No session_id in feedback")
            return JsonResponse(
                {'error': 'Session ID is required'},
                status=400
            )
        
        if rating is None or not isinstance(rating, int) or rating < 1 or rating > 5:
            logger.warning(f"Invalid rating: {rating}")
            return JsonResponse(
                {'error': 'Rating must be an integer between 1 and 5'},
                status=400
            )
        
        # Validate feedback text length
        if len(feedback_text) > 5000:
            logger.warning("Feedback text too long")
            return JsonResponse(
                {'error': 'Feedback must not exceed 5000 characters'},
                status=400
            )
        
        # Get user profile
        try:
            profile = UserProfile.objects.get(session_id=session_id)
        except UserProfile.DoesNotExist:
            logger.warning(f"User profile not found for session {session_id}")
            return JsonResponse(
                {'error': 'User profile not found'},
                status=404
            )
        
        # Get latest symptom log for this user
        symptom_log = SymptomLog.objects.filter(
            user_profile=profile
        ).order_by('-timestamp').first()
        
        # Save feedback
        try:
            feedback = FirstAidFeedback.objects.create(
                user_profile=profile,
                symptom_log=symptom_log,
                disease_name=disease_name,
                response_given="",
                rating=rating,
                feedback_text=feedback_text
            )
            logger.info(f"Feedback created with ID: {feedback.id}, rating: {rating}")
            
            return JsonResponse({
                'status': 'success',
                'feedback_id': feedback.id
            })
        except Exception as e:
            logger.error(f"Failed to create feedback: {e}", exc_info=True)
            return JsonResponse(
                {'error': 'Failed to save feedback'},
                status=500
            )
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in feedback request")
        return JsonResponse(
            {'error': 'Invalid request format'},
            status=400
        )
    except Exception as e:
        logger.error(f"Unhandled error in submit_feedback: {e}", exc_info=True)
        return JsonResponse(
            {'error': 'An error occurred while submitting feedback'},
            status=500
        )
