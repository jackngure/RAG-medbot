# chatbot/models.py
from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
import uuid
from django.utils import timezone

class Disease(models.Model):
    """Kenyan diseases with search optimization for RAG"""
    name = models.CharField(max_length=200)
    description = models.TextField()
    common_symptoms = models.TextField(help_text="Comma-separated list of symptoms")
    search_vector = SearchVectorField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        indexes = [
            models.Index(fields=['name']),
            GinIndex(fields=['search_vector']),
        ]

class Symptom(models.Model):
    """Individual symptoms for precise matching"""
    name = models.CharField(max_length=100, unique=True)
    alternative_names = models.TextField(blank=True, help_text="Common variations")
    diseases = models.ManyToManyField(Disease, related_name='symptoms', blank=True)
    
    def __str__(self):
        return self.name

class FirstAidProcedure(models.Model):
    """First aid instructions"""
    disease = models.ForeignKey(Disease, on_delete=models.CASCADE, related_name='first_aid_procedures')
    title = models.CharField(max_length=200)
    steps = models.TextField(help_text="Step-by-step instructions")
    warning_notes = models.TextField(blank=True)
    when_to_seek_help = models.TextField()
    
    def __str__(self):
        return f"{self.disease.name}: {self.title}"

class EmergencyKeyword(models.Model):
    """Emergency detection keywords"""
    SEVERITY_CHOICES = [
        ('CRITICAL', 'Immediate Emergency'),
        ('URGENT', 'Seek Care Within Hours'),
        ('CAUTION', 'Monitor Carefully'),
    ]
    
    keyword = models.CharField(max_length=100, unique=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    response_message = models.TextField(help_text="What to tell the user")
    
    def __str__(self):
        return f"{self.keyword} ({self.severity})"

class UserProfile(models.Model):
    """Extended user profile for chatbot users"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    
    # Demographics (optional)
    age_group = models.CharField(max_length=20, choices=[
        ('0-12', 'Child (0-12)'),
        ('13-17', 'Teen (13-17)'),
        ('18-35', 'Young Adult (18-35)'),
        ('36-50', 'Adult (36-50)'),
        ('51+', 'Senior (51+)'),
        ('unknown', 'Prefer not to say'),
    ], default='unknown')
    
    gender = models.CharField(max_length=20, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('unknown', 'Prefer not to say'),
    ], default='unknown')
    
    location = models.CharField(max_length=200, blank=True, help_text="City/Region in Kenya")
    
    # Device info
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Timestamps
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    total_sessions = models.IntegerField(default=1)
    
    def __str__(self):
        return f"{self.session_id[:8]}... ({self.first_seen.date()})"

class ChatSession(models.Model):
    """Track conversations"""
    session_id = models.CharField(max_length=100, unique=True)
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_sessions')
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.session_id[:8]}... ({self.created_at.date()})"

class ChatMessage(models.Model):
    """Store chat history for context"""
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_messages')
    role = models.CharField(max_length=10, choices=[('user', 'User'), ('bot', 'Bot')])
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    emergency_detected = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."

class SymptomLog(models.Model):
    """Track all symptoms reported by users"""
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='symptom_logs')
    symptoms = models.JSONField()
    raw_input = models.TextField()
    matched_diseases = models.JSONField(default=list)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user_profile} - {', '.join(self.symptoms[:3])}..."

class EmergencyLog(models.Model):
    """Track all emergency detections"""
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='emergency_logs')
    emergency_keywords = models.JSONField()
    severity = models.CharField(max_length=20)
    raw_input = models.TextField()
    location_shared = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    nearby_hospitals_shown = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user_profile} - {self.severity}: {self.emergency_keywords}"

class FirstAidFeedback(models.Model):
    """Track user feedback on first aid responses"""
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='feedback')
    symptom_log = models.ForeignKey(SymptomLog, on_delete=models.CASCADE, null=True, blank=True)
    disease_name = models.CharField(max_length=200)
    response_given = models.TextField()
    
    RATING_CHOICES = [
        (1, '1 - Not Helpful'),
        (2, '2 - Somewhat Helpful'),
        (3, '3 - Helpful'),
        (4, '4 - Very Helpful'),
        (5, '5 - Extremely Helpful'),
    ]
    
    rating = models.IntegerField(choices=RATING_CHOICES, null=True, blank=True)
    feedback_text = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user_profile} - {self.disease_name}: {self.rating if self.rating else 'No rating'}"

class ChatAnalytics(models.Model):
    """Aggregated analytics for reporting"""
    date = models.DateField(unique=True)
    total_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    returning_users = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)
    emergency_detections = models.IntegerField(default=0)
    location_shares = models.IntegerField(default=0)
    average_rating = models.FloatField(default=0.0)
    top_diseases = models.JSONField(default=dict)
    
    class Meta:
        indexes = [
            models.Index(fields=['date']),
        ]