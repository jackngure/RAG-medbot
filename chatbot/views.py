# chatbot/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import ChatSession, ChatMessage
from .nlp_processor import MedicalNLPProcessor
from .rag_retriever import RAGRetriever

# Initialize processors (but make RAGRetriever lazy)
nlp_processor = MedicalNLPProcessor()
rag_retriever = None  # Initialize as None, will create when needed

def get_rag_retriever():
    """Lazy initialization of RAGRetriever"""
    global rag_retriever
    if rag_retriever is None:
        rag_retriever = RAGRetriever()
    return rag_retriever

def chat_interface(request):
    """Render the chat interface"""
    return render(request, 'chatbot/chat.html')

@csrf_exempt
@require_http_methods(["POST"])
def process_message(request):
    """Process user messages with RAG"""
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        session_id = data.get('session_id', request.session.session_key)
        
        # Get or create session
        session, _ = ChatSession.objects.get_or_create(session_id=session_id)
        
        # Save user message
        ChatMessage.objects.create(
            session=session,
            role='user',
            content=user_message
        )
        
        # Step 1: NLP Processing
        tokens = nlp_processor.preprocess(user_message)
        symptoms = nlp_processor.extract_symptoms(user_message)
        
        # Step 2: Emergency Detection (Highest Priority)
        emergencies = nlp_processor.detect_emergency(user_message)
        
        if emergencies:
            # Sort by severity
            emergencies.sort(key=lambda x: 
                {'CRITICAL': 3, 'URGENT': 2, 'CAUTION': 1}[x['severity']], 
                reverse=True
            )
            
            # Save emergency detection
            msg = ChatMessage.objects.filter(
                session=session, role='user'
            ).latest('timestamp')
            msg.emergency_detected = True
            msg.save()
            
            return JsonResponse({
                'type': 'emergency',
                'severity': emergencies[0]['severity'],
                'message': emergencies[0]['message'],
                'emergencies': emergencies,
                'action': 'request_location'
            })
        
        # Step 3: RAG Retrieval (Non-emergency) - only if symptoms exist
        first_aid_results = []
        if symptoms:
            retriever = get_rag_retriever()
            first_aid_results = retriever.retrieve_relevant_first_aid(
                user_message, symptoms
            )
        
        # Step 4: Generate Response
        if first_aid_results:
            best_match = first_aid_results[0]
            response = f"**Based on your symptoms, you may have {best_match['disease']}**\n\n"
            response += f"**First Aid Steps:**\n{best_match['first_aid']['steps']}\n\n"
            
            if best_match['first_aid']['warning_notes']:
                response += f"**⚠️ WARNING:** {best_match['first_aid']['warning_notes']}\n\n"
            
            response += f"**When to Seek Help:**\n{best_match['first_aid']['when_to_seek_help']}"
            
            if best_match['confidence'] < 0.5:
                response += "\n\n*Note: This is a preliminary suggestion. Please consult a healthcare provider.*"
        else:
            if symptoms:
                response = "I found some symptoms but couldn't match them to a specific condition. Please provide more details."
            else:
                response = "I couldn't identify any specific symptoms. Please describe how you're feeling. For example: 'I have fever, headache, and body aches'"
        
        # Save bot response
        ChatMessage.objects.create(
            session=session,
            role='bot',
            content=response
        )
        
        return JsonResponse({
            'type': 'normal',
            'message': response,
            'symptoms_detected': symptoms,
            'confidence': first_aid_results[0]['confidence'] if first_aid_results else 0
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'type': 'error',
            'message': f'Sorry, an error occurred: {str(e)}'
        }, status=500)

def get_nearby_hospitals(request):
    """Get nearby hospitals from OpenStreetMap"""
    try:
        data = json.loads(request.body)
        lat = data.get('latitude')
        lng = data.get('longitude')
        
        if not lat or not lng:
            return JsonResponse({'error': 'Location required'}, status=400)
        
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
        
        return JsonResponse({
            'hospitals': hospitals[:10],  # Top 10 nearest
            'user_location': {'lat': lat, 'lng': lng}
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula for distance calculation"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in km
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return round(R * c, 2)  # Distance in km
