# chatbot/admin.py
from django.contrib import admin
from .models import Disease, Symptom, FirstAidProcedure, EmergencyKeyword, ChatSession, ChatMessage, UserProfile, SymptomLog, EmergencyLog, FirstAidFeedback, ChatAnalytics

@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'symptom_count')
    search_fields = ('name', 'description', 'common_symptoms')
    list_filter = ('created_at',)
    
    def symptom_count(self, obj):
        return obj.symptoms.count()
    symptom_count.short_description = 'Number of Symptoms'

@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_diseases')
    search_fields = ('name', 'alternative_names')
    filter_horizontal = ('diseases',)
    
    def get_diseases(self, obj):
        return ", ".join([disease.name for disease in obj.diseases.all()[:3]])
    get_diseases.short_description = 'Associated Diseases'

@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display = ('title', 'disease', 'short_steps')
    search_fields = ('title', 'steps', 'disease__name')
    list_filter = ('disease',)
    
    def short_steps(self, obj):
        return obj.steps[:50] + '...' if len(obj.steps) > 50 else obj.steps
    short_steps.short_description = 'Steps'

@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'severity', 'short_response')
    search_fields = ('keyword', 'description', 'response_message')
    list_filter = ('severity',)
    
    def short_response(self, obj):
        return obj.response_message[:50] + '...' if len(obj.response_message) > 50 else obj.response_message
    short_response.short_description = 'Response'

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'created_at', 'last_activity', 'message_count')
    search_fields = ('session_id',)
    list_filter = ('created_at', 'last_activity')
    readonly_fields = ('session_id', 'created_at', 'last_activity')
    
    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Total Messages'

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'timestamp', 'emergency_detected', 'short_content')
    search_fields = ('content',)
    list_filter = ('role', 'emergency_detected', 'timestamp')
    readonly_fields = ('session', 'role', 'content', 'timestamp', 'emergency_detected')
    
    def short_content(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    short_content.short_description = 'Message'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('session_id_short', 'age_group', 'gender', 'location', 'first_seen', 'last_seen', 'total_sessions')
    list_filter = ('age_group', 'gender', 'first_seen')
    search_fields = ('session_id', 'location')
    readonly_fields = ('session_id', 'ip_address', 'user_agent', 'first_seen', 'last_seen')
    
    def session_id_short(self, obj):
        return str(obj.session_id)[:8] + '...'
    session_id_short.short_description = 'Session ID'

@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'symptoms_summary', 'timestamp', 'disease_count')
    list_filter = ('timestamp',)
    search_fields = ('raw_input',)
    readonly_fields = ('user_profile', 'symptoms', 'raw_input', 'matched_diseases', 'timestamp')
    
    def symptoms_summary(self, obj):
        return ', '.join(obj.symptoms[:3])
    symptoms_summary.short_description = 'Symptoms'
    
    def disease_count(self, obj):
        return len(obj.matched_diseases)
    disease_count.short_description = 'Matches'

@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display = ('user_profile', 'severity', 'keywords_summary', 'location_shared', 'timestamp')
    list_filter = ('severity', 'location_shared', 'timestamp')
    search_fields = ('raw_input',)
    
    def keywords_summary(self, obj):
        return ', '.join(obj.emergency_keywords[:3])
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