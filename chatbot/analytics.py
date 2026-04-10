# chatbot/analytics.py
"""
Daily analytics generation for the medical chatbot.
Generates metrics about user activity, emergencies, feedback, and diseases.
"""

import logging
from datetime import timedelta
from collections import Counter

from django.db.models import Count, Avg, Q
from django.utils import timezone

from .models import UserProfile, SymptomLog, EmergencyLog, FirstAidFeedback, ChatAnalytics, ChatMessage

logger = logging.getLogger(__name__)


def generate_daily_analytics():
    """
    Generate analytics report for the previous day.
    
    Calculates:
    - User activity (active, new, returning users)
    - Message statistics
    - Emergency detection metrics
    - User feedback ratings
    - Most common diseases
    
    Returns:
        ChatAnalytics object or None if error occurs
    """
    
    # Define yesterday's date range (timezone-aware)
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today - timedelta(days=1)
    yesterday_end = today
    
    try:
        # Get or create analytics record for yesterday
        analytics, created = ChatAnalytics.objects.get_or_create(date=yesterday_start.date())
        
        # ============================================================
        # USER METRICS
        # ============================================================
        
        # Active users: anyone who used the system yesterday
        analytics.active_users = UserProfile.objects.filter(
            last_seen__gte=yesterday_start,
            last_seen__lt=yesterday_end
        ).count()
        
        # New users: first time ever using the system yesterday
        analytics.new_users = UserProfile.objects.filter(
            first_seen__gte=yesterday_start,
            first_seen__lt=yesterday_end
        ).count()
        
        # Returning users: used before yesterday AND used yesterday
        analytics.returning_users = UserProfile.objects.filter(
            first_seen__lt=yesterday_start,  # Joined before yesterday
            last_seen__gte=yesterday_start,   # Active yesterday
            last_seen__lt=yesterday_end
        ).count()
        
        # Cumulative total: all users who ever used the system
        analytics.total_users_cumulative = UserProfile.objects.filter(
            first_seen__lt=yesterday_end
        ).count()
        
        # ============================================================
        # MESSAGE METRICS
        # ============================================================
        
        # Total messages sent yesterday
        analytics.total_messages = ChatMessage.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end
        ).count()
        
        # Average messages per active user
        user_message_counts = ChatMessage.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end
        ).values('user_session').annotate(
            msg_count=Count('id')
        )
        
        if user_message_counts:
            total_msgs = sum(u['msg_count'] for u in user_message_counts)
            analytics.avg_messages_per_user = round(total_msgs / len(user_message_counts), 2)
        else:
            analytics.avg_messages_per_user = 0
        
        # ============================================================
        # EMERGENCY METRICS
        # ============================================================
        
        # Total emergency detections
        analytics.emergency_detections = EmergencyLog.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end
        ).count()
        
        # How many emergencies had location sharing enabled
        analytics.location_shares = EmergencyLog.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end,
            location_shared=True
        ).count()
        
        # Emergency rate: percentage of sessions that triggered emergency
        total_sessions = ChatMessage.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end
        ).values('user_session').distinct().count()
        
        if total_sessions > 0:
            analytics.emergency_rate = round(
                (analytics.emergency_detections / total_sessions) * 100, 2
            )
        else:
            analytics.emergency_rate = 0
        
        # ============================================================
        # FEEDBACK METRICS
        # ============================================================
        
        # Average rating from user feedback (1-5 scale)
        rating_result = FirstAidFeedback.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end,
            rating__isnull=False
        ).aggregate(
            avg_rating=Avg('rating'),
            total_feedback=Count('id')
        )
        
        analytics.average_rating = round(rating_result['avg_rating'], 2) if rating_result['avg_rating'] else None
        analytics.total_feedback = rating_result['total_feedback'] or 0
        
        # Distribution of ratings (how many 1-star, 2-star, etc.)
        rating_distribution = FirstAidFeedback.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end
        ).values('rating').annotate(count=Count('id'))
        
        analytics.rating_distribution = {
            r['rating']: r['count'] for r in rating_distribution if r['rating']
        }
        
        # ============================================================
        # DISEASE METRICS
        # ============================================================
        
        # Count how many times each disease was matched
        disease_counter = Counter()
        
        # Iterate through symptom logs to extract disease names
        for symptom_log in SymptomLog.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end,
            matched_diseases__isnull=False
        ).only('matched_diseases').iterator():
            
            try:
                matched = symptom_log.matched_diseases
                
                # Handle different data formats
                if isinstance(matched, dict):
                    # Single disease as dict
                    disease_name = matched.get('name')
                    if disease_name:
                        disease_counter[disease_name] += 1
                        
                elif isinstance(matched, (list, tuple)):
                    # Multiple diseases as list
                    for disease in matched:
                        if isinstance(disease, dict):
                            name = disease.get('name')
                        elif isinstance(disease, str):
                            name = disease
                        else:
                            continue
                        
                        if name:
                            disease_counter[name] += 1
                            
                elif isinstance(matched, str):
                    # Single disease as string
                    disease_counter[matched] += 1
                    
            except (TypeError, AttributeError) as e:
                logger.warning(f"Could not parse matched_diseases: {e}")
                continue
        
        # Store top 10 most common diseases
        analytics.top_diseases = dict(disease_counter.most_common(10))
        
        # ============================================================
        # PEAK USAGE HOURS
        # ============================================================
        
        # Find which hours of the day had the most messages
        from django.db.models.functions import ExtractHour
        
        peak_hours = ChatMessage.objects.filter(
            timestamp__gte=yesterday_start,
            timestamp__lt=yesterday_end
        ).annotate(
            hour=ExtractHour('timestamp')
        ).values('hour').annotate(
            message_count=Count('id')
        ).order_by('-message_count')[:5]
        
        analytics.peak_hours = list(peak_hours)
        
        # ============================================================
        # COMPLETION
        # ============================================================
        
        analytics.is_complete = True
        analytics.error_occurred = False
        analytics.error_message = ""
        analytics.save()
        
        logger.info(
            f"Analytics generated for {yesterday_start.date()}: "
            f"{analytics.active_users} active users, "
            f"{analytics.emergency_detections} emergencies, "
            f"avg rating {analytics.average_rating}"
        )
        
        return analytics
        
    except Exception as e:
        # Log error but don't crash - save partial record
        logger.error(f"Error generating analytics for {yesterday_start.date()}: {e}", exc_info=True)
        
        try:
            analytics, _ = ChatAnalytics.objects.get_or_create(date=yesterday_start.date())
            analytics.is_complete = False
            analytics.error_occurred = True
            analytics.error_message = str(e)[:500]
            analytics.save()
        except Exception as save_error:
            logger.error(f"Could not save error state: {save_error}")
        
        return None


def generate_weekly_summary():
    """
    Generate a weekly summary report from daily analytics.
    
    Returns:
        Dictionary with aggregated metrics for the past 7 days
    """
    
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    
    # Get all complete analytics records from the past 7 days
    analytics_records = ChatAnalytics.objects.filter(
        date__gte=week_ago.date(),
        date__lt=today.date(),
        is_complete=True
    )
    
    if not analytics_records:
        return None
    
    # Aggregate all disease counts across the week
    all_diseases = Counter()
    for record in analytics_records:
        if record.top_diseases:
            all_diseases.update(record.top_diseases)
    
    return {
        'period_start': week_ago.date(),
        'period_end': today.date() - timedelta(days=1),
        'total_days': analytics_records.count(),
        'total_active_users': sum(r.active_users for r in analytics_records),
        'total_new_users': sum(r.new_users for r in analytics_records),
        'total_emergencies': sum(r.emergency_detections for r in analytics_records),
        'total_messages': sum(r.total_messages for r in analytics_records),
        'avg_daily_rating': round(
            sum(r.average_rating or 0 for r in analytics_records) / analytics_records.count(), 2
        ),
        'top_diseases_week': dict(all_diseases.most_common(10)),
    }
