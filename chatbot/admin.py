# chatbot/admin.py - Clean version with default Django admin
import logging
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import (
    Disease, Symptom, FirstAidProcedure, EmergencyKeyword,
    ChatSession, ChatMessage, UserProfile, SymptomLog,
    EmergencyLog, FirstAidFeedback, ChatAnalytics,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Shared helpers
# ─────────────────────────────────────────────

def _truncate(text, length=60):
    """Return text truncated to `length` chars with ellipsis if needed."""
    text = text or ""
    return text[:length] + "…" if len(text) > length else text


def _severity_badge(severity):
    """Return a coloured HTML badge for a severity string."""
    colours = {
        "critical": ("#dc2626", "#fee2e2"),
        "high":     ("#ea580c", "#ffedd5"),
        "medium":   ("#d97706", "#fef3c7"),
        "low":      ("#16a34a", "#dcfce7"),
    }
    key = (severity or "").lower()
    fg, bg = colours.get(key, ("#6b7280", "#f3f4f6"))
    label = severity.title() if severity else "—"
    return format_html(
        '<span style="background:{bg};color:{fg};padding:2px 10px;'
        'border-radius:12px;font-size:11px;font-weight:600;">{label}</span>',
        bg=bg, fg=fg, label=label,
    )


def _star_rating(rating, max_stars=5):
    """Return filled/empty star HTML for a numeric rating."""
    if rating is None:
        return "—"
    filled = "★" * round(rating)
    empty  = "☆" * (max_stars - round(rating))
    return format_html(
        '<span style="color:#f59e0b;font-size:14px;">{filled}</span>'
        '<span style="color:#d1d5db;font-size:14px;">{empty}</span>',
        filled=filled, empty=empty,
    )


# ─────────────────────────────────────────────
#  Admin site - Default Django styling
# ─────────────────────────────────────────────

admin.site.site_header = "MedChat Administration"
admin.site.site_title = "MedChat Admin"
admin.site.index_title = "Dashboard"


# ─────────────────────────────────────────────
#  Knowledge Base
# ─────────────────────────────────────────────

@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display = ("name", "symptom_count_badge", "description_preview", "created_at")
    search_fields = ("name", "description", "common_symptoms")
    list_filter = ("created_at",)
    ordering = ("name",)
    date_hierarchy = "created_at"
    list_per_page = 25

    fieldsets = (
        ("Identity", {
            "fields": ("name", "description"),
        }),
        ("Clinical Details", {
            "fields": ("common_symptoms",),
        }),
    )

    @admin.display(description="Symptoms", ordering="symptom_count")
    def symptom_count_badge(self, obj):
        try:
            count = obj.symptoms.count()
        except AttributeError:
            count = 0
        return format_html('<strong>{}</strong>', count)

    @admin.display(description="Description")
    def description_preview(self, obj):
        return _truncate(obj.description, 80)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(symptom_count=Count("symptoms"))


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display = ("name", "disease_tags", "alternative_names_preview")
    search_fields = ("name", "alternative_names")
    filter_horizontal = ("diseases",)
    ordering = ("name",)
    list_per_page = 30

    fieldsets = (
        ("Symptom Details", {
            "fields": ("name", "alternative_names"),
        }),
        ("Disease Mapping", {
            "fields": ("diseases",),
        }),
    )

    @admin.display(description="Associated Diseases")
    def disease_tags(self, obj):
        try:
            diseases = obj.diseases.all()[:5]
        except AttributeError:
            diseases = []
        return ", ".join(d.name for d in diseases) if diseases else "—"

    @admin.display(description="Also Known As")
    def alternative_names_preview(self, obj):
        return _truncate(obj.alternative_names, 60)


@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display = ("title", "disease_link", "steps_preview")
    search_fields = ("title", "steps", "disease__name")
    list_filter = ("disease",)
    ordering = ("disease__name", "title")
    list_per_page = 25
    autocomplete_fields = ("disease",)

    fieldsets = (
        ("Procedure", {
            "fields": ("title", "disease"),
        }),
        ("Instructions", {
            "fields": ("steps", "warning_notes", "when_to_seek_help"),
        }),
    )

    @admin.display(description="Disease", ordering="disease__name")
    def disease_link(self, obj):
        return obj.disease.name if obj.disease else "—"

    @admin.display(description="Steps (preview)")
    def steps_preview(self, obj):
        return _truncate(obj.steps, 90)


@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display = ("keyword", "severity", "response_preview")
    search_fields = ("keyword", "response_message")
    list_filter = ("severity",)
    ordering = ("-severity", "keyword")
    list_per_page = 30

    fieldsets = (
        ("Keyword", {
            "fields": ("keyword", "severity", "response_message"),
        }),
    )

    @admin.display(description="Response Message")
    def response_preview(self, obj):
        return _truncate(obj.response_message, 80)


# ─────────────────────────────────────────────
#  Chat
# ─────────────────────────────────────────────

class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    max_num = 20
    readonly_fields = ("role", "content_preview", "timestamp", "emergency_detected")
    fields = ("role", "content_preview", "emergency_detected", "timestamp")
    can_delete = False
    verbose_name = "Message"
    verbose_name_plural = "Recent Messages (latest 20)"

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-timestamp")[:20]

    @admin.display(description="Content")
    def content_preview(self, obj):
        return _truncate(obj.content, 100)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("session_id_short", "message_count", "created_at", "last_activity", "duration")
    search_fields = ("session_id",)
    list_filter = ("created_at",)
    readonly_fields = ("session_id", "created_at", "last_activity")
    date_hierarchy = "created_at"
    ordering = ("-last_activity",)
    list_per_page = 30
    inlines = [ChatMessageInline]

    @admin.display(description="Session ID")
    def session_id_short(self, obj):
        sid = str(obj.session_id) if obj.session_id else ""
        return sid[:12] + "…" if len(sid) > 12 else sid

    @admin.display(description="Messages", ordering="message_count")
    def message_count(self, obj):
        try:
            return obj.messages.count()
        except AttributeError:
            return 0

    @admin.display(description="Duration")
    def duration(self, obj):
        if obj.created_at and obj.last_activity:
            delta = obj.last_activity - obj.created_at
            minutes = int(delta.total_seconds() / 60)
            if minutes < 1:
                return "< 1 min"
            if minutes < 60:
                return f"{minutes} min"
            return f"{minutes // 60}h {minutes % 60}m"
        return "—"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(message_count=Count("messages"))


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("session_link", "role", "content_preview", "emergency_flag", "timestamp")
    search_fields = ("content", "session__session_id")
    list_filter = ("role", "emergency_detected", "timestamp")
    readonly_fields = ("session", "role", "content", "timestamp", "emergency_detected")
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)
    list_per_page = 40

    @admin.display(description="Session", ordering="session__session_id")
    def session_link(self, obj):
        sid = str(obj.session.session_id)[:8] if obj.session else "—"
        return sid + "…"

    @admin.display(description="Content")
    def content_preview(self, obj):
        return _truncate(obj.content, 90)

    @admin.display(description="Emergency", boolean=True)
    def emergency_flag(self, obj):
        return obj.emergency_detected


# ─────────────────────────────────────────────
#  Users & Profiles
# ─────────────────────────────────────────────

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("session_id_short", "age_group", "gender", "location", "total_sessions", "first_seen", "last_seen")
    list_filter = ("age_group", "gender", "first_seen")
    search_fields = ("session_id", "location")
    readonly_fields = ("session_id", "ip_address", "user_agent", "first_seen", "last_seen")
    ordering = ("-last_seen",)
    list_per_page = 30
    date_hierarchy = "first_seen"

    fieldsets = (
        ("Identity", {
            "fields": ("session_id", "age_group", "gender", "location"),
        }),
        ("Technical", {
            "fields": ("ip_address", "user_agent"),
            "classes": ("collapse",),
        }),
        ("Activity", {
            "fields": ("first_seen", "last_seen", "total_sessions"),
        }),
    )

    @admin.display(description="Session ID", ordering="session_id")
    def session_id_short(self, obj):
        sid = str(obj.session_id) if obj.session_id else ""
        return sid[:10] + "…" if len(sid) > 10 else sid


# ─────────────────────────────────────────────
#  Logs
# ─────────────────────────────────────────────

@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display = ("user_profile", "symptoms_preview", "disease_count", "raw_input_preview", "timestamp")
    list_filter = ("timestamp",)
    search_fields = ("raw_input",)
    readonly_fields = ("user_profile", "raw_input", "matched_diseases", "timestamp")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 30

    @admin.display(description="Symptoms")
    def symptoms_preview(self, obj):
        symptoms_list = obj.symptoms if isinstance(obj.symptoms, list) else []
        return ", ".join(symptoms_list[:3]) + ("..." if len(symptoms_list) > 3 else "") if symptoms_list else "—"

    @admin.display(description="Matches")
    def disease_count(self, obj):
        matched = obj.matched_diseases if isinstance(obj.matched_diseases, list) else []
        return len(matched)

    @admin.display(description="Raw Input")
    def raw_input_preview(self, obj):
        return _truncate(obj.raw_input, 70)


@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display = ("user_profile", "severity", "keywords_preview", "location_shared", "timestamp")
    list_filter = ("severity", "location_shared", "timestamp")
    search_fields = ("raw_input",)
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 30

    @admin.display(description="Keywords")
    def keywords_preview(self, obj):
        keywords_list = obj.emergency_keywords if isinstance(obj.emergency_keywords, list) else []
        return ", ".join(keywords_list[:3]) + ("..." if len(keywords_list) > 3 else "") if keywords_list else "—"

    @admin.display(description="Location", boolean=True)
    def location_shared(self, obj):
        return obj.location_shared


# ─────────────────────────────────────────────
#  Feedback & Analytics
# ─────────────────────────────────────────────

@admin.register(FirstAidFeedback)
class FirstAidFeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "user_profile", 
        "disease_name", 
        "rating_badge", 
        "rating_icon",
        "feedback_preview", 
        "has_comments",
        "timestamp"
    )
    list_filter = ("rating", "timestamp", "disease_name")
    search_fields = ("disease_name", "feedback_text", "user_profile__session_id")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page = 30
    readonly_fields = ("user_profile", "disease_name", "rating", "feedback_text", "timestamp", "symptom_log")
    
    fieldsets = (
        ("Feedback Information", {
            "fields": ("user_profile", "disease_name", "rating", "feedback_text")
        }),
        ("Related Data", {
            "fields": ("symptom_log", "response_given"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("timestamp",),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Rating", ordering="rating")
    def rating_badge(self, obj):
        """Display rating as a colored badge matching chat.html labels"""
        if not obj.rating:
            return "—"
        
        # Map ratings to labels from chat.html
        rating_labels = {
            5: {"label": "Very Helpful", "color": "#4CAF50", "bg": "#E8F5E9", "icon": "👍"},
            3: {"label": "Okay", "color": "#FF9800", "bg": "#FFF3E0", "icon": "😐"},
            1: {"label": "Not Helpful", "color": "#F44336", "bg": "#FFEBEE", "icon": "👎"},
        }
        
        info = rating_labels.get(obj.rating, {"label": "Unknown", "color": "#9E9E9E", "bg": "#F5F5F5", "icon": "❓"})
        
        return format_html(
            '<span style="background:{bg};color:{color};padding:4px 12px;'
            'border-radius:20px;font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:6px;">'
            '<span style="font-size:14px;">{icon}</span> {label}</span>',
            bg=info["bg"],
            color=info["color"],
            icon=info["icon"],
            label=info["label"]
        )

    @admin.display(description="", ordering="rating")
    def rating_icon(self, obj):
        """Display just the icon for quick visual scanning"""
        if not obj.rating:
            return "—"
        
        icons = {
            5: "👍",
            3: "😐", 
            1: "👎",
        }
        
        icon = icons.get(obj.rating, "❓")
        return format_html(
            '<span style="font-size:20px;cursor:help;" title="{}">{}</span>',
            self._get_rating_label(obj.rating),
            icon
        )

    @admin.display(description="Feedback", ordering="feedback_text")
    def feedback_preview(self, obj):
        """Show truncated feedback text"""
        if not obj.feedback_text:
            return format_html('<span style="color:#999;font-style:italic;">— No comments —</span>')
        return _truncate(obj.feedback_text, 80)

    @admin.display(description="💬", boolean=True)
    def has_comments(self, obj):
        """Show if feedback has comments"""
        return bool(obj.feedback_text and obj.feedback_text.strip())

    def _get_rating_label(self, rating):
        """Helper to get rating label"""
        labels = {
            5: "Very Helpful",
            3: "Okay",
            1: "Not Helpful"
        }
        return labels.get(rating, "Unknown")

    def get_queryset(self, request):
        """Optimize queryset with select_related for better performance"""
        return super().get_queryset(request).select_related('user_profile', 'symptom_log')

    # Add custom actions for bulk operations
    actions = ['export_feedback_data', 'export_summary_report']

    @admin.action(description="📊 Export selected feedback to CSV")
    def export_feedback_data(self, request, queryset):
        """Export feedback data as CSV for analysis"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="feedback_data.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Date', 
            'Disease', 
            'Rating', 
            'Rating Label',
            'Feedback', 
            'Session ID', 
            'Has Comments'
        ])
        
        for feedback in queryset:
            rating_label = self._get_rating_label(feedback.rating) if feedback.rating else "No rating"
            writer.writerow([
                feedback.timestamp.strftime('%Y-%m-%d %H:%M'),
                feedback.disease_name,
                feedback.rating or '',
                rating_label,
                feedback.feedback_text[:200] if feedback.feedback_text else '',
                feedback.user_profile.session_id[:20] if feedback.user_profile else '',
                'Yes' if feedback.feedback_text else 'No'
            ])
        
        self.message_user(request, f"✅ Exported {queryset.count()} feedback records")
        return response

    @admin.action(description="📈 Export summary report")
    def export_summary_report(self, request, queryset):
        """Export summary statistics for selected feedback"""
        import csv
        from django.http import HttpResponse
        from django.db.models import Count
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="feedback_summary.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Metric', 'Value'])
        
        # Calculate statistics
        total = queryset.count()
        
        # Rating distribution
        rating_dist = {}
        for rating in [5, 3, 1]:
            count = queryset.filter(rating=rating).count()
            rating_dist[rating] = count
        
        writer.writerow(['Total Feedback', total])
        writer.writerow(['Very Helpful (5)', f"{rating_dist[5]} ({round(rating_dist[5]/total*100, 1) if total > 0 else 0}%)"])
        writer.writerow(['Okay (3)', f"{rating_dist[3]} ({round(rating_dist[3]/total*100, 1) if total > 0 else 0}%)"])
        writer.writerow(['Not Helpful (1)', f"{rating_dist[1]} ({round(rating_dist[1]/total*100, 1) if total > 0 else 0}%)"])
        writer.writerow(['With Comments', queryset.exclude(feedback_text='').exclude(feedback_text__isnull=True).count()])
        
        # Top diseases by rating
        writer.writerow([])
        writer.writerow(['Top Diseases by Feedback Count'])
        writer.writerow(['Disease', 'Count', 'Avg Rating'])
        
        top_diseases = queryset.values('disease_name').annotate(
            count=Count('id'),
            avg_rating=Count('rating')  # This needs to be Avg, let me fix
        ).order_by('-count')[:10]
        
        # Recalculate with proper Avg
        from django.db.models import Avg
        top_diseases = queryset.values('disease_name').annotate(
            count=Count('id'),
            avg_rating=Avg('rating')
        ).order_by('-count')[:10]
        
        for disease in top_diseases:
            avg_rating_val = disease['avg_rating'] if disease['avg_rating'] else 0
            writer.writerow([
                disease['disease_name'],
                disease['count'],
                f"{avg_rating_val:.1f}/5.0" if avg_rating_val else "N/A"
            ])
        
        self.message_user(request, f"✅ Exported summary report for {total} feedback records")
        return response

    # Add statistics to changelist view
    def changelist_view(self, request, extra_context=None):
        """Add summary statistics to the changelist view"""
        from django.db.models import Avg, Count
        
        extra_context = extra_context or {}
        
        # Calculate summary statistics
        total_feedback = FirstAidFeedback.objects.count()
        
        # Rating distribution for 3-rating system
        rating_distribution = {
            'very_helpful': FirstAidFeedback.objects.filter(rating=5).count(),
            'okay': FirstAidFeedback.objects.filter(rating=3).count(),
            'not_helpful': FirstAidFeedback.objects.filter(rating=1).count(),
        }
        
        avg_rating = FirstAidFeedback.objects.filter(rating__isnull=False).aggregate(Avg('rating'))['rating__avg']
        
        # Calculate percentages
        if total_feedback > 0:
            rating_distribution['very_helpful_pct'] = round(rating_distribution['very_helpful'] / total_feedback * 100, 1)
            rating_distribution['okay_pct'] = round(rating_distribution['okay'] / total_feedback * 100, 1)
            rating_distribution['not_helpful_pct'] = round(rating_distribution['not_helpful'] / total_feedback * 100, 1)
        else:
            rating_distribution['very_helpful_pct'] = 0
            rating_distribution['okay_pct'] = 0
            rating_distribution['not_helpful_pct'] = 0
        
        # Get top diseases by feedback count
        top_diseases = FirstAidFeedback.objects.values('disease_name').annotate(
            count=Count('id'),
            avg_rating=Avg('rating')
        ).order_by('-count')[:5]
        
        extra_context['feedback_stats'] = {
            'total': total_feedback,
            'avg_rating': round(avg_rating, 2) if avg_rating else 0,
            'distribution': rating_distribution,
            'top_diseases': top_diseases,
        }
        
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(ChatAnalytics)
class ChatAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "total_users",
        "new_users",
        "returning_users",
        "total_messages",
        "emergency_detections",
        "average_rating",
    )
    list_filter = ("date",)
    date_hierarchy = "date"
    ordering = ("-date",)
    list_per_page = 20

    fieldsets = (
        ("Period", {
            "fields": ("date",),
        }),
        ("User Metrics", {
            "fields": ("total_users", "new_users", "returning_users", "avg_messages_per_user"),
        }),
        ("Engagement", {
            "fields": ("total_messages", "emergency_detections", "location_shares", "emergency_rate"),
        }),
        ("Feedback", {
            "fields": ("average_rating", "total_feedback", "rating_distribution"),
        }),
        ("Disease Metrics", {
            "fields": ("top_diseases",),
        }),
    )
