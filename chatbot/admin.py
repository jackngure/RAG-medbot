from django.contrib import admin
from .models import Disease, Symptom, FirstAidProcedure, EmergencyKeyword, ChatSession, ChatMessage

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
    list_display = ('name', 'display_diseases')
    search_fields = ('name', 'alternative_names')
    filter_horizontal = ('diseases',)  # Makes selecting diseases easier
    
    def display_diseases(self, obj):
        return ", ".join([disease.name for disease in obj.diseases.all()[:3]])
    display_diseases.short_description = 'Associated Diseases'

@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display = ('title', 'disease', 'truncated_steps')
    search_fields = ('title', 'steps', 'disease__name')
    list_filter = ('disease',)
    
    def truncated_steps(self, obj):
        return obj.steps[:50] + '...' if len(obj.steps) > 50 else obj.steps
    truncated_steps.short_description = 'Steps'

@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display = ('keyword', 'severity', 'truncated_message')
    search_fields = ('keyword', 'description', 'response_message')
    list_filter = ('severity',)
    
    def truncated_message(self, obj):
        return obj.response_message[:50] + '...' if len(obj.response_message) > 50 else obj.response_message
    truncated_message.short_description = 'Response'

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'user', 'started_at', 'last_activity', 'message_count')
    search_fields = ('session_id', 'user__username')
    list_filter = ('started_at', 'last_activity')
    
    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Total Messages'

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'timestamp', 'emergency_detected', 'truncated_content')
    search_fields = ('content',)
    list_filter = ('role', 'emergency_detected', 'timestamp')
    
    def truncated_content(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    truncated_content.short_description = 'Message'
