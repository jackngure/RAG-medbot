# chatbot/admin.py
from django.contrib import admin
from .models import Disease, Symptom, FirstAidProcedure, EmergencyKeyword, ChatSession, ChatMessage, UserProfile, SymptomLog, EmergencyLog, FirstAidFeedback, ChatAnalytics

@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'symptom_count')
    search_fields = ('name', 'description', 'common_symptoms')
    list_filter = ('created_at',)
    
    def symptom_count(self, obj):
        try:
            return obj.symptoms.count()
        except Exception:
            # fallback if symptoms is a list/None
            symptoms = getattr(obj, 'symptoms', None)
            if symptoms is None:
                return 0
            try:
                return len(symptoms)
            except Exception:
                return 0
    symptom_count.short_description = 'Number of Symptoms'

@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_diseases')
    search_fields = ('name', 'alternative_names')
    filter_horizontal = ('diseases',)
    
    def get_diseases(self, obj):
        try:
            diseases_qs = obj.diseases.all()
            names = [d.name for d in diseases_qs[:3]]
        except Exception:
            # If diseases is a list/iterable or attribute not a manager
            diseases_attr = getattr(obj, 'diseases', None) or []
            try:
                names = [d.name if hasattr(d, 'name') else str(d) for d in list(diseases_attr)[:3]]
            except Exception:
                names = []
        return ", ".join(names)
    get_diseases.short_description = 'Associated Diseases'

@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display = ('title', 'disease', 'short_steps')
    search_fields = ('title', 'steps', 'disease__name')
    list_filter = ('disease',)
    
    def short_steps(self, obj):
        steps = getattr(obj, 'steps', '') or ''
        return steps[:50] + '...' if len(steps) > 50 else steps
    short_steps.short_description = 'Steps'

@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'severity', 'short_response')
    search_fields = ('keyword', 'description', 'response_message')
    list_filter = ('severity',)
    
    def short_response(self, obj):
        response = getattr(obj, 'response_message', '') or ''
        return response[:50] + '...' if len(response) > 50 else response
    short_response.short_description = 'Response'

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'created_at', 'last_activity', 'message_count')
    search_fields = ('session_id',)
    list_filter = ('created_at', 'last_activity')
    readonly_fields = ('session_id', 'created_at', 'last_activity')
    
    def message_count(self, obj):
        try:
            return obj.messages.count()
        except Exception:
            messages = getattr(obj, 'messages', None) or []
            try:
                return len(messages)
            except Exception:
                return 0
    message_count.short_description = 'Total Messages'

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'timestamp', 'emergency_detected', 'short_content')
    search_fields = ('content',)
    list_filter = ('role', 'emergency_detected', 'timestamp')
    readonly_fields = ('session', 'role', 'content', 'timestamp', 'emergency_detected')
    
    def short_content(self, obj):
        content = getattr(obj, 'content', '') or ''
        return content[:50] + '...' if len(content) > 50 else content
    short_content.short_description = 'Message'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('session_id_short', 'age_group', 'gender', 'location', 'first_seen', 'last_seen', 'total_sessions')
    list_filter = ('age_group', 'gender', 'first_seen')
    search_fields = ('session_id', 'location')
    readonly_fields = ('session_id', 'ip_address', 'user_agent', 'first_seen', 'last_seen')
    
    def session_id_short(self, obj):
        sid = getattr(obj, 'session_id', None)
        if sid is None:
            return ''
        s = str(sid)
        return s[:8] + '...' if len(s) > 8 else s
    session_id_short.short_description = 'Session ID'

@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'symptoms_summary', 'timestamp', 'disease_count')
    list_filter = ('timestamp',)
    search_fields = ('raw_input',)
    readonly_fields = ('user_profile', 'symptoms', 'raw_input', 'matched_diseases', 'timestamp')
    
    def symptoms_summary(self, obj):
        symptoms_attr = getattr(obj, 'symptoms', None) or []
        try:
            # If it's a manager/queryset
            items = list(symptoms_attr.all()[:3]) if hasattr(symptoms_attr, 'all') else list(symptoms_attr)[:3]
            # Try to get a readable representation
            names = [s.name if hasattr(s, 'name') else str(s) for s in items]
        except Exception:
            try:
                names = [str(s) for s in list(symptoms_attr)[:3]]
            except Exception:
                names = []
        return ', '.join(names)
    symptoms_summary.short_description = 'Symptoms'
    
    def disease_count(self, obj):
        matched = getattr(obj, 'matched_diseases', None) or []
        try:
            return len(matched)
        except Exception:
            try:
                return matched.count()
            except Exception:
                return 0
    disease_count.short_description = 'Matches'

@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'severity', 'keywords_summary', 'location_shared', 'timestamp')
    list_filter = ('severity', 'location_shared', 'timestamp')
    search_fields = ('raw_input',)
    
    def keywords_summary(self, obj):
        keywords_attr = getattr(obj, 'emergency_keywords', None) or []
        try:
            items = list(keywords_attr.all()[:3]) if hasattr(keywords_attr, 'all') else list(keywords_attr)[:3]
            names = [k.keyword if hasattr(k, 'keyword') else str(k) for k in items]
        except Exception:
            try:
                names = [str(k) for k in list(keywords_attr)[:3]]
            except Exception:
                names = []
        return ', '.join(names)
    keywords_summary.short_description = 'Keywords'

@admin.register(FirstAidFeedback)
class FirstAidFeedbackAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'disease_name', 'rating', 'timestamp')
    list_filter = ('rating', 'timestamp')
    search_fields = ('disease_name', 'feedback_text')

@admin.register(ChatAnalytics)
class ChatAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_users', 'new_users', 'returning_users', 'total_messages', 'emergency_detections', 'average_rating')
    list_filter = ('date',)
    readonly_fields = ('date', 'total_users', 'new_users', 'returning_users', 'total_messages', 'emergency_detections', 'location_shares', 'average_rating', 'top_diseases')
