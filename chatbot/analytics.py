# chatbot/analytics.py
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
from .models import UserProfile, SymptomLog, EmergencyLog, FirstAidFeedback, ChatAnalytics

def generate_daily_analytics():
    """Generate daily analytics report"""
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    
    # Get analytics for yesterday
    analytics, created = ChatAnalytics.objects.get_or_create(date=yesterday)
    
    # Calculate metrics
    analytics.total_users = UserProfile.objects.filter(first_seen__date=lte=yesterday).count()
    analytics.new_users = UserProfile.objects.filter(first_seen__date=yesterday).count()
    analytics.returning_users = UserProfile.objects.filter(
        first_seen__date__lt=yesterday,
        last_seen__date=yesterday
    ).count()
    
    analytics.total_messages = ChatMessage.objects.filter(timestamp__date=yesterday).count()
    analytics.emergency_detections = EmergencyLog.objects.filter(timestamp__date=yesterday).count()
    analytics.location_shares = EmergencyLog.objects.filter(
        timestamp__date=yesterday,
        location_shared=True
    ).count()
    
    # Average rating
    avg_rating = FirstAidFeedback.objects.filter(
        timestamp__date=yesterday,
        rating__isnull=False
    ).aggregate(Avg('rating'))['rating__avg']
    
    if avg_rating:
        analytics.average_rating = round(avg_rating, 2)
    
    # Top diseases
    top_diseases = SymptomLog.objects.filter(
        timestamp__date=yesterday
    ).values_list('matched_diseases', flat=True)
    
    disease_counts = {}
    for log in top_diseases:
        for disease in log:
            name = disease.get('name')
            if name:
                disease_counts[name] = disease_counts.get(name, 0) + 1
    
    analytics.top_diseases = dict(sorted(
        disease_counts.items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:10])
    
    analytics.save()
    return analytics