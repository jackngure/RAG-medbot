# chatbot/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import traceback
import logging
from .models import ChatSession, ChatMessage, UserProfile, SymptomLog, EmergencyLog, FirstAidFeedback
from .nlp_processor import MedicalNLPProcessor
from .rag_retriever import get_rag_retriever
import uuid

logger = logging.getLogger(__name__)
nlp_processor = MedicalNLPProcessor()

def get_or_create_user_profile(request, session_id):
    """Get or create user profile from session"""
    # Try to get existing profile
    try:
        profile = UserProfile.objects.get(session_id=session_id)
        # Update last seen
        profile.last_seen = timezone.now()
        profile.save()
        return profile
    except UserProfile.DoesNotExist:
        # Create new profile
        profile = UserProfile.objects.create(
            session_id=session_id,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        return profile

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def chat_interface(request):
    """Render the chat interface"""
    # Generate or get session ID
    if not request.session.session_key:
        request.session.create()
    
    session_id = request.session.session_key
    profile = get_or_create_user_profile(request, session_id)
    
    return render(request, 'chatbot/chat.html', {
        'session_id': session_id,
        'user_profile': profile
    })

@csrf_exempt
@require_http_methods(["POST"])
def process_message(request):
    """Process user messages with RAG"""
    print("\n" + "="*50)
    print("PROCESSING NEW MESSAGE")
    print("="*50)
    
    try:
        # Parse request
        data = json.loads(request.body)
        user_message = data.get('message', '')
        session_id = data.get('session_id', request.session.session_key)
        
        print(f"User message: '{user_message}'")
        print(f"Session ID: {session_id}")
        
        # Get or create user profile
        profile = get_or_create_user_profile(request, session_id)
        
        # Get or create session
        session, created = ChatSession.objects.get_or_create(
            session_id=session_id,
            defaults={'user_profile': profile}
        )
        if not session.user_profile:
            session.user_profile = profile
            session.save()
        
        print(f"Session {'created' if created else 'retrieved'}")
        
        # Save user message
        user_msg = ChatMessage.objects.create(
            session=session,
            user_profile=profile,
            role='user',
            content=user_message
        )
        print(f"Saved user message ID: {user_msg.id}")
        
        # Step 1: NLP Processing
        print("\n--- NLP Processing ---")
        tokens = nlp_processor.preprocess(user_message)
        symptoms = nlp_processor.extract_symptoms(user_message)
        print(f"Tokens: {tokens}")
        print(f"Symptoms extracted: {symptoms}")
        
        # Step 2: Emergency Detection
        print("\n--- Emergency Detection ---")
        emergencies = nlp_processor.detect_emergency(user_message)
        print(f"Emergencies detected: {emergencies}")
        
        if emergencies:
            print("⚠️ EMERGENCY DETECTED")
            # Sort by severity
            emergencies.sort(key=lambda x: 
                {'CRITICAL': 3, 'URGENT': 2, 'CAUTION': 1}[x['severity']], 
                reverse=True
            )
            
            # Log emergency
            emergency_log = EmergencyLog.objects.create(
                user_profile=profile,
                emergency_keywords=[e['keyword'] for e in emergencies],
                severity=emergencies[0]['severity'],
                raw_input=user_message
            )
            
            # Mark message as emergency
            user_msg.emergency_detected = True
            user_msg.save()
            
            return JsonResponse({
                'type': 'emergency',
                'severity': emergencies[0]['severity'],
                'message': emergencies[0]['message'],
                'emergencies': emergencies,
                'action': 'request_location',
                'emergency_id': emergency_log.id
            })
        
        # Step 3: RAG Retrieval
        print("\n--- RAG Retrieval ---")
        first_aid_results = []
        matched_diseases = []
        
        if symptoms:
            try:
                rag_retriever = get_rag_retriever()
                print("RAG retriever obtained")
                first_aid_results = rag_retriever.retrieve_relevant_first_aid(
                    user_message, symptoms
                )
                print(f"RAG results: {len(first_aid_results)} matches")
                
                # Track matched diseases
                for result in first_aid_results:
                    matched_diseases.append({
                        'name': result['disease'],
                        'confidence': result['confidence']
                    })
            except Exception as e:
                print(f"❌ RAG retrieval error: {e}")
                traceback.print_exc()
        else:
            print("No symptoms to match")
        
        # Log symptoms
        if symptoms:
            symptom_log = SymptomLog.objects.create(
                user_profile=profile,
                symptoms=symptoms,
                raw_input=user_message,
                matched_diseases=matched_diseases
            )
        
        # Step 4: Generate Response
        print("\n--- Generating Response ---")
        if first_aid_results:
            best_match = first_aid_results[0]
            print(f"Best match: {best_match['disease']} (confidence: {best_match['confidence']})")
            
            response = f"**Based on your symptoms, you may have {best_match['disease']}**\n\n"
            response += f"**First Aid Steps:**\n{best_match['first_aid']['steps']}\n\n"
            
            if best_match['first_aid']['warning_notes']:
                response += f"**⚠️ WARNING:** {best_match['first_aid']['warning_notes']}\n\n"
            
            response += f"**When to Seek Help:**\n{best_match['first_aid']['when_to_seek_help']}"
            
            if best_match['confidence'] < 0.5:
                response += "\n\n*Note: This is a preliminary suggestion. Please consult a healthcare provider.*"
        else:
            if symptoms:
                response = f"I found these symptoms: {', '.join(symptoms)}. But I couldn't match them to a specific condition. Please provide more details or consult a healthcare provider."
                print("No disease matches found")
            else:
                response = "I couldn't identify any specific symptoms. Please describe how you're feeling. For example: 'I have fever, headache, and body aches'"
                print("No symptoms identified")
        
        print(f"Response: {response[:100]}...")
        
        # Save bot response
        bot_msg = ChatMessage.objects.create(
            session=session,
            user_profile=profile,
            role='bot',
            content=response
        )
        print(f"Saved bot message ID: {bot_msg.id}")
        
        return JsonResponse({
            'type': 'normal',
            'message': response,
            'symptoms_detected': symptoms,
            'session_id': session_id
        })
        
    except Exception as e:
        print(f"❌ UNHANDLED ERROR: {e}")
        traceback.print_exc()
        return JsonResponse({
            'type': 'error',
            'message': f'Sorry, an error occurred. Please try again.'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def get_nearby_hospitals(request):
    """Get nearby hospitals from OpenStreetMap"""
    try:
        data = json.loads(request.body)
        lat = data.get('latitude')
        lng = data.get('longitude')
        session_id = data.get('session_id')
        emergency_id = data.get('emergency_id')
        
        if not lat or not lng:
            return JsonResponse({'error': 'Location required'}, status=400)
        
        # Update emergency log with location
        if emergency_id:
            try:
                emergency_log = EmergencyLog.objects.get(id=emergency_id)
                emergency_log.location_shared = True
                emergency_log.latitude = lat
                emergency_log.longitude = lng
                emergency_log.save()
            except:
                pass
        
        # Query OpenStreetMap Overpass API
        import requests
        
        radius = 5000  # 5km
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:{radius},{lat},{lng});
          node["amenity"="clinic"](around:{radius},{lat},{lng});
          node["healthcare"](around:{radius},{lat},{lng});
        );
        out body;
        """
        
        response = requests.post(overpass_url, data=overpass_query)
        data = response.json()
        
        hospitals = []
        for element in data.get('elements', []):
            hospitals.append({
                'name': element.get('tags', {}).get('name', 'Medical Facility'),
                'lat': element.get('lat'),
                'lon': element.get('lon'),
                'address': element.get('tags', {}).get('addr:street', 'Address unavailable'),
                'phone': element.get('tags', {}).get('phone', ''),
                'distance': calculate_distance(lat, lng, element.get('lat'), element.get('lon'))
            })
        
        # Sort by distance
        hospitals.sort(key=lambda x: x['distance'])
        
        # Update emergency log with hospital count
        if emergency_id:
            try:
                emergency_log = EmergencyLog.objects.get(id=emergency_id)
                emergency_log.nearby_hospitals_shown = len(hospitals[:10])
                emergency_log.save()
            except:
                pass
        
        return JsonResponse({
            'hospitals': hospitals[:10],
            'user_location': {'lat': lat, 'lng': lng}
        })
        
    except Exception as e:
        print(f"Hospital API error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def submit_feedback(request):
    """Submit user feedback on first aid response"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        disease_name = data.get('disease')
        rating = data.get('rating')
        feedback_text = data.get('feedback', '')
        
        # Get user profile
        profile = UserProfile.objects.get(session_id=session_id)
        
        # Get latest symptom log for this user
        symptom_log = SymptomLog.objects.filter(
            user_profile=profile
        ).order_by('-timestamp').first()
        
        # Save feedback
        feedback = FirstAidFeedback.objects.create(
            user_profile=profile,
            symptom_log=symptom_log,
            disease_name=disease_name,
            response_given="",  # You can store the response here
            rating=rating,
            feedback_text=feedback_text
        )
        
        return JsonResponse({'status': 'success', 'feedback_id': feedback.id})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula for distance calculation"""
    from math import radians, sin, cos, sqrt, atan2
    
    if lat2 is None or lon2 is None:
        return 999999
    
    R = 6371
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return round(R * c, 2)
