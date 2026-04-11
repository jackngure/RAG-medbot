
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count

from .models import (
    ChatAnalytics,
    ChatMessage,
    ChatSession,
    Disease,
    EmergencyKeyword,
    EmergencyLog,
    FirstAidFeedback,
    FirstAidProcedure,
    Symptom,
    SymptomLog,
    UserProfile,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Admin site branding
# ---------------------------------------------------------------------------

admin.site.site_header = "Self-Diagnosis MedChat Administration"
admin.site.site_title  = "Self-Diagnosis MedChat Admin"
admin.site.index_title = "Admin Dashboard"

@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display   = ("name", "symptom_count_badge", "description_preview", "created_at")
    search_fields  = ("name", "description", "common_symptoms")
    list_filter    = ("created_at",)
    ordering       = ("name",)
    date_hierarchy = "created_at"
    list_per_page  = 25

    fieldsets = (
        ("Identity", {
            "fields": ("name", "description"),
        }),
        ("Clinical Details", {
            "fields": ("common_symptoms",),
            "classes": ("wide",),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(symptom_count=Count("symptoms"))

    @admin.display(description="Symptoms", ordering="symptom_count")
    def symptom_count_badge(self, obj):
        count = getattr(obj, "symptom_count", 0)
        fg = "#3b82f6" if count else "#94a3b8"
        bg = "rgba(59,130,246,.12)" if count else "rgba(148,163,184,.12)"
        return _pill(str(count), fg, bg)

    @admin.display(description="Description")
    def description_preview(self, obj):
        return _truncate(obj.description, 80)


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display      = ("name", "disease_tags", "alternative_names_preview")
    search_fields     = ("name", "alternative_names")
    filter_horizontal = ("diseases",)
    ordering          = ("name",)
    list_per_page     = 30

    fieldsets = (
        ("Symptom Details", {
            "fields": ("name", "alternative_names"),
        }),
        ("Disease Mapping", {
            "fields": ("diseases",),
            "description": "Select all diseases this symptom is associated with.",
        }),
    )

    @admin.display(description="Associated Diseases")
    def disease_tags(self, obj):
        try:
            diseases = obj.diseases.all()[:5]
        except AttributeError:
            logger.warning("Could not access diseases for Symptom pk=%s", obj.pk)
            return "—"
        if not diseases:
            return "—"
        tags = "".join(
            format_html(
                '<span style="background:rgba(59,130,246,.15);color:#60a5fa;'
                'padding:2px 8px;border-radius:8px;font-size:11px;'
                'margin:2px;display:inline-block;">{}</span>',
                d.name,
            )
            for d in diseases
        )
        return format_html(tags)

    @admin.display(description="Also Known As")
    def alternative_names_preview(self, obj):
        return _truncate(obj.alternative_names, 60)


@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display        = ("title", "disease_link", "steps_preview")
    search_fields       = ("title", "steps", "disease__name")
    list_filter         = ("disease",)
    ordering            = ("disease__name", "title")
    list_per_page       = 25
    autocomplete_fields = ("disease",)

    fieldsets = (
        ("Procedure", {
            "fields": ("title", "disease"),
        }),
        ("Instructions", {
            "fields": ("steps",),
            "classes": ("wide",),
        }),
    )

    @admin.display(description="Disease", ordering="disease__name")
    def disease_link(self, obj):
        if obj.disease:
            return format_html(
                '<a style="color:#60a5fa;font-weight:600;" href="{url}">{name}</a>',
                url=f"../disease/{obj.disease.pk}/change/",
                name=obj.disease.name,
            )
        return "—"

    @admin.display(description="Steps (preview)")
    def steps_preview(self, obj):
        return _truncate(obj.steps, 90)


@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display  = ("keyword", "severity_badge", "response_preview")
    search_fields = ("keyword", "description", "response_message")
    list_filter   = ("severity",)
    ordering      = ("-severity", "keyword")
    list_per_page = 30

    fieldsets = (
        ("Keyword", {
            "fields": ("keyword", "severity", "description"),
        }),
        ("Response Configuration", {
            "fields": ("response_message",),
            "classes": ("wide",),
        }),
    )

    @admin.display(description="Severity", ordering="severity")
    def severity_badge(self, obj):
        return _severity_badge(obj.severity)

    @admin.display(description="Response Message")
    def response_preview(self, obj):
        return _truncate(obj.response_message, 80)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessageInline(admin.TabularInline):
    model               = ChatMessage
    extra               = 0
    max_num             = 20          # limit rows shown; no ORM-level slicing
    readonly_fields     = ("role", "content_preview", "timestamp", "emergency_detected")
    fields              = ("role", "content_preview", "emergency_detected", "timestamp")
    can_delete          = False
    show_change_link    = True
    verbose_name        = "Message"
    verbose_name_plural = "Messages (latest 20)"

    def get_queryset(self, request):
        # Order newest-first; max_num caps the display to 20 rows safely
        return super().get_queryset(request).order_by("-timestamp")

    @admin.display(description="Content")
    def content_preview(self, obj):
        return _truncate(obj.content, 100)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display   = ("session_id_short", "message_count_badge", "created_at", "last_activity", "duration")
    search_fields  = ("session_id",)
    list_filter    = ("created_at",)
    readonly_fields = ("session_id", "created_at", "last_activity")
    date_hierarchy = "created_at"
    ordering       = ("-last_activity",)
    list_per_page  = 30
    inlines        = [ChatMessageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(message_count=Count("messages"))

    @admin.display(description="Session ID")
    def session_id_short(self, obj):
        return _code_chip(str(obj.session_id or ""), length=12)

    @admin.display(description="Messages", ordering="message_count")
    def message_count_badge(self, obj):
        count = getattr(obj, "message_count", 0)
        return _pill(str(count), "#60a5fa", "rgba(59,130,246,.12)")

    @admin.display(description="Duration")
    def duration(self, obj):
        if not (obj.created_at and obj.last_activity):
            return "—"
        mins = int((obj.last_activity - obj.created_at).total_seconds() / 60)
        if mins < 1:
            return "< 1 min"
        if mins < 60:
            return f"{mins} min"
        return f"{mins // 60}h {mins % 60}m"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display   = ("session_link", "role_badge", "content_preview", "emergency_flag", "timestamp")
    search_fields  = ("content", "session__session_id")
    list_filter    = ("role", "emergency_detected", "timestamp")
    readonly_fields = ("session", "role", "content", "timestamp", "emergency_detected")
    date_hierarchy = "timestamp"
    ordering       = ("-timestamp",)
    list_per_page  = 40

    @admin.display(description="Session", ordering="session__session_id")
    def session_link(self, obj):
        sid = str(obj.session.session_id)[:8] if obj.session else "—"
        return _code_chip(sid + "…")

    @admin.display(description="Role", ordering="role")
    def role_badge(self, obj):
        palette = {
            "user":      ("#a78bfa", "rgba(167,139,250,.15)"),
            "assistant": ("#34d399", "rgba(52,211,153,.15)"),
            "system":    ("#38bdf8", "rgba(56,189,248,.15)"),
        }
        key = (obj.role or "").lower()
        fg, bg = palette.get(key, ("#94a3b8", "rgba(148,163,184,.12)"))
        return _pill((obj.role or "—").title(), fg, bg)

    @admin.display(description="Content")
    def content_preview(self, obj):
        return _truncate(obj.content, 90)

    @admin.display(description="🚨", ordering="emergency_detected")
    def emergency_flag(self, obj):
        if obj.emergency_detected:
            return format_html('<span style="color:#ef4444;font-size:15px;" title="Emergency">🚨</span>')
        return format_html('<span style="color:var(--mc-text-muted);">—</span>')


# ---------------------------------------------------------------------------
# Users & Profiles
# ---------------------------------------------------------------------------

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display   = ("session_id_short", "age_group", "gender", "location", "total_sessions", "first_seen", "last_seen")
    list_filter    = ("age_group", "gender", "first_seen")
    search_fields  = ("session_id", "location")
    readonly_fields = ("session_id", "ip_address", "user_agent", "first_seen", "last_seen")
    ordering       = ("-last_seen",)
    list_per_page  = 30
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
        return _code_chip(str(obj.session_id or ""), length=10)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display   = ("user_profile", "symptoms_tags", "disease_count_badge", "raw_input_preview", "timestamp")
    list_filter    = ("timestamp",)
    search_fields  = ("raw_input",)
    readonly_fields = ("user_profile", "raw_input", "matched_diseases", "timestamp")
    ordering       = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page  = 30

    @admin.display(description="Symptoms")
    def symptoms_tags(self, obj):
        symptoms = []
        try:
            symptoms = list(obj.symptoms.all()[:4])
        except AttributeError:
            # Fall back gracefully if symptoms is not a Manager
            raw = getattr(obj, "symptoms", None)
            if raw:
                try:
                    symptoms = list(raw)[:4]
                except TypeError:
                    pass

        if not symptoms:
            return "—"
        tags = "".join(
            format_html(
                '<span style="background:rgba(52,211,153,.15);color:#34d399;'
                'padding:2px 7px;border-radius:8px;font-size:11px;'
                'margin:2px;display:inline-block;">{}</span>',
                s.name if hasattr(s, "name") else str(s),
            )
            for s in symptoms
        )
        return format_html(tags)

    @admin.display(description="Matches")
    def disease_count_badge(self, obj):
        matched = getattr(obj, "matched_diseases", None)
        count = 0
        if matched is not None:
            if isinstance(matched, (list, tuple)):
                count = len(matched)
            else:
                try:
                    count = matched.count()
                except AttributeError:
                    try:
                        count = len(matched)
                    except TypeError:
                        count = 0
        fg = "#22c55e" if count else "#94a3b8"
        bg = "rgba(34,197,94,.12)" if count else "rgba(148,163,184,.12)"
        return _pill(str(count), fg, bg)

    @admin.display(description="Raw Input")
    def raw_input_preview(self, obj):
        return _truncate(obj.raw_input, 70)


@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display   = ("user_profile", "severity_badge", "keywords_tags", "location_shared_icon", "timestamp")
    list_filter    = ("severity", "location_shared", "timestamp")
    search_fields  = ("raw_input",)
    ordering       = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page  = 30

    @admin.display(description="Severity", ordering="severity")
    def severity_badge(self, obj):
        return _severity_badge(obj.severity)

    @admin.display(description="Keywords")
    def keywords_tags(self, obj):
        keywords = []
        try:
            keywords = list(obj.emergency_keywords.all()[:4])
        except AttributeError:
            raw = getattr(obj, "emergency_keywords", None)
            if raw:
                try:
                    keywords = list(raw)[:4]
                except TypeError:
                    pass

        if not keywords:
            return "—"
        tags = "".join(
            format_html(
                '<span style="background:rgba(239,68,68,.15);color:#f87171;'
                'padding:2px 7px;border-radius:8px;font-size:11px;'
                'margin:2px;display:inline-block;">{}</span>',
                k.keyword if hasattr(k, "keyword") else str(k),
            )
            for k in keywords
        )
        return format_html(tags)

    @admin.display(description="📍 Location", ordering="location_shared")
    def location_shared_icon(self, obj):
        if obj.location_shared:
            return format_html('<span style="color:#22c55e;" title="Shared">✔</span>')
        return format_html('<span style="color:var(--mc-text-muted);" title="Not shared">✘</span>')


# ---------------------------------------------------------------------------
# Feedback & Analytics
# ---------------------------------------------------------------------------

@admin.register(FirstAidFeedback)
class FirstAidFeedbackAdmin(admin.ModelAdmin):
    list_display   = ("user_profile", "disease_name", "star_rating", "feedback_preview", "timestamp")
    list_filter    = ("rating", "timestamp")
    search_fields  = ("disease_name", "feedback_text")
    ordering       = ("-timestamp",)
    date_hierarchy = "timestamp"
    list_per_page  = 30

    @admin.display(description="Rating", ordering="rating")
    def star_rating(self, obj):
        return _star_rating(obj.rating)

    @admin.display(description="Feedback")
    def feedback_preview(self, obj):
        return _truncate(obj.feedback_text, 80)


@admin.register(ChatAnalytics)
class ChatAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "total_users",
        "user_breakdown",
        "total_messages",
        "emergency_detections",
        "location_shares",
        "star_avg_rating",
    )
    list_filter    = ("date",)
    date_hierarchy = "date"
    ordering       = ("-date",)
    list_per_page  = 20
    readonly_fields = (
        "date",
        "total_users",
        "new_users",
        "returning_users",
        "total_messages",
        "emergency_detections",
        "location_shares",
        "average_rating",
        "top_diseases",
    )

    fieldsets = (
        ("Period", {
            "fields": ("date",),
        }),
        ("User Metrics", {
            "fields": ("total_users", "new_users", "returning_users"),
        }),
        ("Engagement", {
            "fields": ("total_messages", "emergency_detections", "location_shares"),
        }),
        ("Quality", {
            "fields": ("average_rating", "top_diseases"),
        }),
    )

    @admin.display(description="New / Returning")
    def user_breakdown(self, obj):
        return format_html(
            '<span style="color:#3b82f6;font-weight:700;">{new}</span>'
            '<span style="color:var(--mc-text-muted);"> / </span>'
            '<span style="color:#a78bfa;font-weight:700;">{ret}</span>',
            new=obj.new_users or 0,
            ret=obj.returning_users or 0,
        )

    @admin.display(description="Avg. Rating", ordering="average_rating")
    def star_avg_rating(self, obj):
        return _star_rating(obj.average_rating)
