# chatbot/admin.py
import logging
from django.contrib import admin
from .models import (
    Disease, Symptom, FirstAidProcedure, EmergencyKeyword,
    ChatSession, ChatMessage, UserProfile, SymptomLog,
    EmergencyLog, FirstAidFeedback, ChatAnalytics,
)

logger = logging.getLogger(__name__)


@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'symptom_count')
    search_fields = ('name', 'description', 'common_symptoms')
    list_filter = ('created_at',)

    @admin.display(description='Number of Symptoms')
    def symptom_count(self, obj):
        try:
            return obj.symptoms.count()
        except AttributeError:
            symptoms = getattr(obj, 'symptoms', None)
            if symptoms is None:
                return 0
            try:
                return len(symptoms)
            except TypeError:
                return 0


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_diseases')
    search_fields = ('name', 'alternative_names')
    filter_horizontal = ('diseases',)

    @admin.display(description='Associated Diseases')
    def get_diseases(self, obj):
        try:
            names = [d.name for d in obj.diseases.all()[:3]]
        except AttributeError:
            logger.warning("Could not access diseases for Symptom pk=%s", obj.pk)
            names = []
        return ", ".join(names)


@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display = ('title', 'disease', 'short_steps')
    search_fields = ('title', 'steps', 'disease__name')
    list_filter = ('disease',)

    @admin.display(description='Steps')
    def short_steps(self, obj):
        steps = obj.steps or ''
        return steps[:50] + '...' if len(steps) > 50 else steps


@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'severity', 'short_response')
    search_fields = ('keyword', 'description', 'response_message')
    list_filter = ('severity',)

    @admin.display(description='Response')
    def short_response(self, obj):
        response = obj.response_message or ''
        return response[:50] + '...' if len(response) > 50 else response


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'created_at', 'last_activity', 'message_count')
    search_fields = ('session_id',)
    list_filter = ('created_at', 'last_activity')
    readonly_fields = ('session_id', 'created_at', 'last_activity')

    @admin.display(description='Total Messages')
    def message_count(self, obj):
        try:
            return obj.messages.count()
        except AttributeError:
            return 0


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'timestamp', 'emergency_detected', 'short_content')
    search_fields = ('content',)
    list_filter = ('role', 'emergency_detected', 'timestamp')
    readonly_fields = ('session', 'role', 'content', 'timestamp', 'emergency_detected')

    @admin.display(description='Message')
    def short_content(self, obj):
        content = obj.content or ''
        return content[:50] + '...' if len(content) > 50 else content


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'session_id_short', 'age_group', 'gender', 'location',
        'first_seen', 'last_seen', 'total_sessions',
    )
    list_filter = ('age_group', 'gender', 'first_seen')
    search_fields = ('session_id', 'location')
    readonly_fields = ('session_id', 'ip_address', 'user_agent', 'first_seen', 'last_seen')

    @admin.display(description='Session ID')
    def session_id_short(self, obj):
        sid = str(obj.session_id) if obj.session_id else ''
        return sid[:8] + '...' if len(sid) > 8 else sid


@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'symptoms_summary', 'timestamp', 'disease_count')
    list_filter = ('timestamp',)
    search_fields = ('raw_input',)
    # 'symptoms' removed from readonly_fields — M2M fields don't render in readonly;
    # use the custom display method 'symptoms_summary' instead.
    readonly_fields = ('user_profile', 'raw_input', 'matched_diseases', 'timestamp')

    @admin.display(description='Symptoms')
    def symptoms_summary(self, obj):
        try:
            symptoms = obj.symptoms.all()[:3]
            return ', '.join(s.name for s in symptoms)
        except AttributeError:
            # symptoms may be a plain list or JSON field
            symptoms = getattr(obj, 'symptoms', None) or []
            try:
                items = list(symptoms)[:3]
                return ', '.join(s.name if hasattr(s, 'name') else str(s) for s in items)
            except (TypeError, ValueError):
                logger.warning("Could not render symptoms for SymptomLog pk=%s", obj.pk)
                return ''

    @admin.display(description='Matches')
    def disease_count(self, obj):
        matched = getattr(obj, 'matched_diseases', None)
        if matched is None:
            return 0
        # matched_diseases is most likely a JSON list field
        if isinstance(matched, (list, tuple)):
            return len(matched)
        # fallback for queryset/manager
        try:
            return matched.count()
        except AttributeError:
            try:
                return len(matched)
            except TypeError:
                return 0


@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'severity', 'keywords_summary', 'location_shared', 'timestamp')
    list_filter = ('severity', 'location_shared', 'timestamp')
    search_fields = ('raw_input',)

    @admin.display(description='Keywords')
    def keywords_summary(self, obj):
        try:
            keywords = obj.emergency_keywords.all()[:3]
            return ', '.join(k.keyword for k in keywords)
        except AttributeError:
            keywords = getattr(obj, 'emergency_keywords', None) or []
            try:
                items = list(keywords)[:3]
                return ', '.join(k.keyword if hasattr(k, 'keyword') else str(k) for k in items)
            except (TypeError, ValueError):
                logger.warning("Could not render keywords for EmergencyLog pk=%s", obj.pk)
                return ''


@admin.register(FirstAidFeedback)
class FirstAidFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'disease_name', 'rating', 'timestamp')
    list_filter = ('rating', 'timestamp')
    search_fields = ('disease_name', 'feedback_text')


@admin.register(ChatAnalytics)
class ChatAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        'date', 'total_users', 'new_users', 'returning_users',
        'total_messages', 'emergency_detections', 'average_rating_display',
    )
    list_filter = ('date',)
    readonly_fields = (
        'date', 'total_users', 'new_users', 'returning_users',
        'total_messages', 'emergency_detections', 'location_shares',
        'average_rating', 'top_diseases',
    )

    @admin.display(description='Avg. Rating')
    def average_rating_display(self, obj):
        # average_rating may be None if no ratings exist yet
        rating = obj.average_rating
        return f"{rating:.2f}" if rating is not None else '—'
