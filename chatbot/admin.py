# chatbot/admin.py
import logging
from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import now
from django.db.models import Count, Avg
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
        '<span style="'
        "background:{bg};color:{fg};padding:2px 10px;"
        "border-radius:12px;font-size:11px;font-weight:600;"
        'letter-spacing:.5px;">{label}</span>',
        bg=bg, fg=fg, label=label,
    )


def _star_rating(rating, max_stars=5):
    """Return filled/empty star HTML for a numeric rating."""
    if rating is None:
        return "—"
    filled = "★" * round(rating)
    empty  = "☆" * (max_stars - round(rating))
    return format_html(
        '<span style="color:#f59e0b;font-size:14px;" title="{rating:.2f}">{filled}</span>'
        '<span style="color:#d1d5db;font-size:14px;">{empty}</span>',
        rating=rating, filled=filled, empty=empty,
    )


# ─────────────────────────────────────────────
#  Admin site customisation
# ─────────────────────────────────────────────

admin.site.site_header  = "🩺 MedChat Administration"
admin.site.site_title   = "MedChat Admin"
admin.site.index_title  = "Dashboard"


# ─────────────────────────────────────────────
#  Knowledge Base
# ─────────────────────────────────────────────

@admin.register(Disease)
class DiseaseAdmin(admin.ModelAdmin):
    list_display    = ("name", "symptom_count_badge", "description_preview", "created_at")
    search_fields   = ("name", "description", "common_symptoms")
    list_filter     = ("created_at",)
    ordering        = ("name",)
    date_hierarchy  = "created_at"
    list_per_page   = 25

    fieldsets = (
        ("Identity", {
            "fields": ("name", "description"),
        }),
        ("Clinical Details", {
            "fields": ("common_symptoms",),
            "classes": ("wide",),
        }),
    )

    @admin.display(description="Symptoms", ordering="symptom_count")
    def symptom_count_badge(self, obj):
        try:
            count = obj.symptoms.count()
        except AttributeError:
            count = 0
        colour = "#2563eb" if count else "#9ca3af"
        return format_html(
            '<span style="background:{c};color:#fff;padding:2px 9px;'
            'border-radius:10px;font-size:12px;font-weight:700;">{n}</span>',
            c=colour, n=count,
        )

    @admin.display(description="Description")
    def description_preview(self, obj):
        return _truncate(obj.description, 80)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(symptom_count=Count("symptoms"))


@admin.register(Symptom)
class SymptomAdmin(admin.ModelAdmin):
    list_display        = ("name", "disease_tags", "alternative_names_preview")
    search_fields       = ("name", "alternative_names")
    filter_horizontal   = ("diseases",)
    ordering            = ("name",)
    list_per_page       = 30

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
            diseases = []
        tags = "".join(
            format_html(
                '<span style="background:#eff6ff;color:#1d4ed8;padding:2px 8px;'
                'border-radius:8px;font-size:11px;margin:2px;display:inline-block;">{}</span>',
                d.name,
            )
            for d in diseases
        )
        return format_html(tags) if tags else "—"

    @admin.display(description="Also Known As")
    def alternative_names_preview(self, obj):
        return _truncate(obj.alternative_names, 60)


@admin.register(FirstAidProcedure)
class FirstAidProcedureAdmin(admin.ModelAdmin):
    list_display    = ("title", "disease_link", "steps_preview")
    search_fields   = ("title", "steps", "disease__name")
    list_filter     = ("disease",)
    ordering        = ("disease__name", "title")
    list_per_page   = 25
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
                '<a style="color:#2563eb;font-weight:600;" href="{}">{}</a>',
                f"../disease/{obj.disease.pk}/change/",
                obj.disease.name,
            )
        return "—"

    @admin.display(description="Steps (preview)")
    def steps_preview(self, obj):
        return _truncate(obj.steps, 90)


@admin.register(EmergencyKeyword)
class EmergencyKeywordAdmin(admin.ModelAdmin):
    list_display    = ("keyword", "severity_badge", "response_preview")
    search_fields   = ("keyword", "description", "response_message")
    list_filter     = ("severity",)
    ordering        = ("-severity", "keyword")
    list_per_page   = 30

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


# ─────────────────────────────────────────────
#  Chat
# ─────────────────────────────────────────────

class ChatMessageInline(admin.TabularInline):
    model           = ChatMessage
    extra           = 0
    max_num         = 20
    readonly_fields = ("role", "content_preview", "timestamp", "emergency_detected")
    fields          = ("role", "content_preview", "emergency_detected", "timestamp")
    can_delete      = False
    show_change_link = False
    verbose_name    = "Message"
    verbose_name_plural = "Recent Messages (latest 20)"

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-timestamp")[:20]

    @admin.display(description="Content")
    def content_preview(self, obj):
        return _truncate(obj.content, 100)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display    = ("session_id_short", "message_count_badge", "created_at", "last_activity", "duration")
    search_fields   = ("session_id",)
    list_filter     = ("created_at",)
    readonly_fields = ("session_id", "created_at", "last_activity")
    date_hierarchy  = "created_at"
    ordering        = ("-last_activity",)
    list_per_page   = 30
    inlines         = [ChatMessageInline]

    @admin.display(description="Session ID")
    def session_id_short(self, obj):
        sid = str(obj.session_id) if obj.session_id else ""
        return format_html(
            '<code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px;">{}</code>',
            sid[:12] + "…" if len(sid) > 12 else sid,
        )

    @admin.display(description="Messages", ordering="message_count")
    def message_count_badge(self, obj):
        try:
            count = obj.messages.count()
        except AttributeError:
            count = 0
        return format_html(
            '<strong style="color:#374151;">{}</strong>', count
        )

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
    list_display    = ("session_link", "role_badge", "content_preview", "emergency_flag", "timestamp")
    search_fields   = ("content", "session__session_id")
    list_filter     = ("role", "emergency_detected", "timestamp")
    readonly_fields = ("session", "role", "content", "timestamp", "emergency_detected")
    date_hierarchy  = "timestamp"
    ordering        = ("-timestamp",)
    list_per_page   = 40

    @admin.display(description="Session", ordering="session__session_id")
    def session_link(self, obj):
        sid = str(obj.session.session_id)[:8] if obj.session else "—"
        return format_html(
            '<code style="font-size:11px;background:#f1f5f9;padding:2px 6px;border-radius:4px;">{}</code>',
            sid + "…",
        )

    @admin.display(description="Role", ordering="role")
    def role_badge(self, obj):
        colours = {
            "user":      ("#7c3aed", "#f5f3ff"),
            "assistant": ("#059669", "#ecfdf5"),
            "system":    ("#0284c7", "#e0f2fe"),
        }
        key = (obj.role or "").lower()
        fg, bg = colours.get(key, ("#374151", "#f3f4f6"))
        return format_html(
            '<span style="background:{bg};color:{fg};padding:2px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{role}</span>',
            bg=bg, fg=fg, role=(obj.role or "—").title(),
        )

    @admin.display(description="Content")
    def content_preview(self, obj):
        return _truncate(obj.content, 90)

    @admin.display(description="🚨", boolean=False, ordering="emergency_detected")
    def emergency_flag(self, obj):
        if obj.emergency_detected:
            return format_html(
                '<span style="color:#dc2626;font-size:16px;" title="Emergency detected">🚨</span>'
            )
        return format_html('<span style="color:#d1d5db;">—</span>')


# ─────────────────────────────────────────────
#  Users & Profiles
# ─────────────────────────────────────────────

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display    = ("session_id_short", "age_group", "gender", "location", "total_sessions", "first_seen", "last_seen")
    list_filter     = ("age_group", "gender", "first_seen")
    search_fields   = ("session_id", "location")
    readonly_fields = ("session_id", "ip_address", "user_agent", "first_seen", "last_seen")
    ordering        = ("-last_seen",)
    list_per_page   = 30
    date_hierarchy  = "first_seen"

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
        return format_html(
            '<code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px;">{}</code>',
            sid[:10] + "…" if len(sid) > 10 else sid,
        )


# ─────────────────────────────────────────────
#  Logs
# ─────────────────────────────────────────────

@admin.register(SymptomLog)
class SymptomLogAdmin(admin.ModelAdmin):
    list_display    = ("user_profile", "symptoms_tags", "disease_count_badge", "raw_input_preview", "timestamp")
    list_filter     = ("timestamp",)
    search_fields   = ("raw_input",)
    readonly_fields = ("user_profile", "raw_input", "matched_diseases", "timestamp")
    ordering        = ("-timestamp",)
    date_hierarchy  = "timestamp"
    list_per_page   = 30

    @admin.display(description="Symptoms")
    def symptoms_tags(self, obj):
        try:
            symptoms = obj.symptoms.all()[:4]
        except AttributeError:
            raw = getattr(obj, "symptoms", None) or []
            symptoms = list(raw)[:4]

        tags = "".join(
            format_html(
                '<span style="background:#f0fdf4;color:#166534;padding:2px 7px;'
                'border-radius:8px;font-size:11px;margin:2px;display:inline-block;">{}</span>',
                s.name if hasattr(s, "name") else str(s),
            )
            for s in symptoms
        )
        return format_html(tags) if tags else "—"

    @admin.display(description="Matches")
    def disease_count_badge(self, obj):
        matched = getattr(obj, "matched_diseases", None)
        if matched is None:
            count = 0
        elif isinstance(matched, (list, tuple)):
            count = len(matched)
        else:
            try:
                count = matched.count()
            except AttributeError:
                try:
                    count = len(matched)
                except TypeError:
                    count = 0
        colour = "#15803d" if count else "#9ca3af"
        return format_html(
            '<span style="background:{c}22;color:{c};padding:2px 9px;'
            'border-radius:10px;font-size:12px;font-weight:700;">{n}</span>',
            c=colour, n=count,
        )

    @admin.display(description="Raw Input")
    def raw_input_preview(self, obj):
        return _truncate(obj.raw_input, 70)


@admin.register(EmergencyLog)
class EmergencyLogAdmin(admin.ModelAdmin):
    list_display    = ("user_profile", "severity_badge", "keywords_tags", "location_shared_icon", "timestamp")
    list_filter     = ("severity", "location_shared", "timestamp")
    search_fields   = ("raw_input",)
    ordering        = ("-timestamp",)
    date_hierarchy  = "timestamp"
    list_per_page   = 30

    @admin.display(description="Severity", ordering="severity")
    def severity_badge(self, obj):
        return _severity_badge(obj.severity)

    @admin.display(description="Keywords")
    def keywords_tags(self, obj):
        try:
            keywords = obj.emergency_keywords.all()[:4]
        except AttributeError:
            raw = getattr(obj, "emergency_keywords", None) or []
            keywords = list(raw)[:4]

        tags = "".join(
            format_html(
                '<span style="background:#fef2f2;color:#991b1b;padding:2px 7px;'
                'border-radius:8px;font-size:11px;margin:2px;display:inline-block;">{}</span>',
                k.keyword if hasattr(k, "keyword") else str(k),
            )
            for k in keywords
        )
        return format_html(tags) if tags else "—"

    @admin.display(description="📍 Location", ordering="location_shared")
    def location_shared_icon(self, obj):
        if obj.location_shared:
            return format_html('<span style="color:#16a34a;font-size:15px;" title="Location shared">✔</span>')
        return format_html('<span style="color:#d1d5db;" title="Not shared">✘</span>')


# ─────────────────────────────────────────────
#  Feedback & Analytics
# ─────────────────────────────────────────────

@admin.register(FirstAidFeedback)
class FirstAidFeedbackAdmin(admin.ModelAdmin):
    list_display    = ("user_profile", "disease_name", "star_rating", "feedback_preview", "timestamp")
    list_filter     = ("rating", "timestamp")
    search_fields   = ("disease_name", "feedback_text")
    ordering        = ("-timestamp",)
    date_hierarchy  = "timestamp"
    list_per_page   = 30

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
    list_filter     = ("date",)
    date_hierarchy  = "date"
    ordering        = ("-date",)
    list_per_page   = 20
    readonly_fields = (
        "date", "total_users", "new_users", "returning_users",
        "total_messages", "emergency_detections", "location_shares",
        "average_rating", "top_diseases",
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
            '<span style="color:#2563eb;font-weight:600;">{new}</span>'
            '<span style="color:#9ca3af;"> / </span>'
            '<span style="color:#7c3aed;font-weight:600;">{ret}</span>',
            new=obj.new_users or 0,
            ret=obj.returning_users or 0,
        )

    @admin.display(description="Avg. Rating", ordering="average_rating")
    def star_avg_rating(self, obj):
        return _star_rating(obj.average_rating)
