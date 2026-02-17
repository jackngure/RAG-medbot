from django.db import models
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex

class Disease(models.Model):
    """Kenyan diseases with search optimization for RAG"""
    name = models.CharField(max_length=200)
    description = models.TextField()
    common_symptoms = models.TextField(help_text="Comma-separated list of symptoms")
    search_vector = SearchVectorField(null=True)  # For PostgreSQL full-text search
    
    # Metadata
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
    
    # Embedding for semantic search (will store as JSON)
    embedding = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return self.name

class FirstAidProcedure(models.Model):
    """First aid instructions - the core of your RAG system"""
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

class ChatSession(models.Model):
    """Track conversations"""
    session_id = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

class ChatMessage(models.Model):
    """Store chat history for context"""
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=[('user', 'User'), ('bot', 'Bot')])
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    emergency_detected = models.BooleanField(default=False)