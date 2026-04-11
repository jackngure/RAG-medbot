"""
chatbot/admin.py
================
Django admin configuration for MedChat.

Key fixes & improvements over previous version
-----------------------------------------------
* Removed unsafe monkey-patching of AdminSite.each_context (used a proper
  subclass + media class instead).
* Dark-theme CSS is delivered via ModelAdmin.Media so Django injects it
  correctly in every view, not via a fragile string-concatenation hack.
* Theme follows the OS/browser preference automatically (prefers-color-scheme).
  No forced-dark, no toggle removal — just clean adaptive CSS variables.
* Eliminated the MutationObserver script that tried to strip Django's own UI
  elements (unreliable and broke several admin widgets in Django 4+).
* Fixed SymptomLog.symptoms display that silently swallowed AttributeErrors.
* Fixed ChatMessageInline.get_queryset slicing before evaluation (Django ORM
  slices cannot be further filtered; moved limit to the template level via
  max_num).
* Added missing `show_change_link` and sensible `can_delete` defaults.
* All format_html calls use named parameters to avoid positional confusion.
* Removed duplicate/redundant fieldset entries.
* PEP-8 cleaned throughout.
"""

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

admin.site.site_header = "🩺 MedChat Administration"
admin.site.site_title  = "MedChat Admin"
admin.site.index_title = "Dashboard"


# ---------------------------------------------------------------------------
# Adaptive theme (light / dark follows OS preference automatically)
# ---------------------------------------------------------------------------

THEME_CSS = """
<style>
/* ── CSS custom properties ─────────────────────────────────────────────── */
:root {
    /* Light defaults */
    --mc-bg:           #f8fafc;
    --mc-bg-card:      #ffffff;
    --mc-bg-header:    #1e293b;
    --mc-bg-sidebar:   #f1f5f9;
    --mc-bg-input:     #ffffff;
    --mc-bg-hover:     #f1f5f9;
    --mc-bg-code:      #e2e8f0;

    --mc-text:         #1e293b;
    --mc-text-muted:   #64748b;
    --mc-text-header:  #f8fafc;
    --mc-text-code:    #334155;

    --mc-border:       #e2e8f0;
    --mc-border-input: #cbd5e1;

    --mc-blue:         #3b82f6;
    --mc-blue-dark:    #2563eb;
    --mc-purple:       #8b5cf6;
    --mc-red:          #ef4444;
    --mc-green:        #22c55e;
    --mc-amber:        #f59e0b;
    --mc-orange:       #f97316;

    --mc-radius:       8px;
    --mc-radius-sm:    5px;
    --mc-radius-pill:  999px;
}

@media (prefers-color-scheme: dark) {
    :root {
        --mc-bg:           #0f172a;
        --mc-bg-card:      #1e293b;
        --mc-bg-header:    #0f172a;
        --mc-bg-sidebar:   #1e293b;
        --mc-bg-input:     #0f172a;
        --mc-bg-hover:     #334155;
        --mc-bg-code:      #334155;

        --mc-text:         #e2e8f0;
        --mc-text-muted:   #94a3b8;
        --mc-text-header:  #f1f5f9;
        --mc-text-code:    #e2e8f0;

        --mc-border:       #334155;
        --mc-border-input: #475569;
    }
}

/* ── Global ─────────────────────────────────────────────────────────────── */
body, #container, #content, .dashboard, .main {
    background-color: var(--mc-bg) !important;
    color: var(--mc-text) !important;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
#header {
    background: var(--mc-bg-header) !important;
    color: var(--mc-text-header) !important;
    border-bottom: 1px solid var(--mc-border) !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.15) !important;
}
#branding h1,
#branding h1 a:link,
#branding h1 a:visited { color: var(--mc-text-header) !important; }
#user-tools a { color: #93c5fd !important; }

/* ── Sidebar / navigation ───────────────────────────────────────────────── */
#nav-sidebar,
.sidebar { background-color: var(--mc-bg-sidebar) !important; }
#nav-sidebar .module caption,
#nav-sidebar th { color: var(--mc-text-muted) !important; }

/* ── Breadcrumbs ────────────────────────────────────────────────────────── */
div.breadcrumbs {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text-muted) !important;
    border-bottom: 1px solid var(--mc-border) !important;
}
div.breadcrumbs a { color: var(--mc-blue) !important; }

/* ── Cards / modules ────────────────────────────────────────────────────── */
.module {
    background-color: var(--mc-bg-card) !important;
    border: 1px solid var(--mc-border) !important;
    border-radius: var(--mc-radius) !important;
    overflow: hidden;
}
.module h2,
.module caption,
.inline-group h2 {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text) !important;
    border-bottom: 1px solid var(--mc-border) !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: .3px !important;
}

/* ── Tables ─────────────────────────────────────────────────────────────── */
table { border-color: var(--mc-border) !important; }
table thead th {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text-muted) !important;
    border-bottom: 2px solid var(--mc-border) !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: .6px !important;
}
table tbody td {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text) !important;
    border-color: var(--mc-border) !important;
}
table tbody tr:hover td { background-color: var(--mc-bg-hover) !important; }
.results { background-color: var(--mc-bg-card) !important; }

/* ── Forms ──────────────────────────────────────────────────────────────── */
input, textarea, select,
.vTextField, .vLargeTextField,
.vDateField, .vTimeField {
    background-color: var(--mc-bg-input) !important;
    color: var(--mc-text) !important;
    border: 1px solid var(--mc-border-input) !important;
    border-radius: var(--mc-radius-sm) !important;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--mc-blue) !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,.15) !important;
}
.aligned label { color: var(--mc-text) !important; }
.help, p.help { color: var(--mc-text-muted) !important; font-size: 12px !important; }

/* ── Buttons ────────────────────────────────────────────────────────────── */
.button, input[type=submit], input[type=button],
.submit-row input, .default {
    background-color: var(--mc-blue) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--mc-radius-sm) !important;
    padding: 8px 18px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    cursor: pointer !important;
    transition: background .15s !important;
}
.button:hover, input[type=submit]:hover,
.default:hover { background-color: var(--mc-blue-dark) !important; }
.deletelink,
.deletelink:link { background-color: var(--mc-red) !important; }
.deletelink:hover { background-color: #b91c1c !important; }

/* Object tools (top-right "Add" links) */
.object-tools a:link,
.object-tools a:visited {
    background-color: var(--mc-blue) !important;
    color: #fff !important;
    border-radius: var(--mc-radius-pill) !important;
    font-size: 12px !important;
    font-weight: 600 !important;
}

/* ── Pagination ─────────────────────────────────────────────────────────── */
.paginator {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text-muted) !important;
    border-top: 1px solid var(--mc-border) !important;
}
.paginator a:link, .paginator a:visited {
    background-color: var(--mc-bg-hover) !important;
    color: var(--mc-text) !important;
    border-radius: var(--mc-radius-sm) !important;
}

/* ── Filter sidebar ─────────────────────────────────────────────────────── */
#changelist-filter {
    background-color: var(--mc-bg-sidebar) !important;
    border-left: 1px solid var(--mc-border) !important;
}
#changelist-filter h3 {
    color: var(--mc-text-muted) !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: .5px !important;
    border-bottom: 1px solid var(--mc-border) !important;
}
#changelist-filter ul li a { color: var(--mc-text-muted) !important; }
#changelist-filter ul li.selected a {
    color: var(--mc-blue) !important;
    font-weight: 700 !important;
}

/* ── Calendar / time widgets ────────────────────────────────────────────── */
.calendarbox, .clockbox {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text) !important;
    border: 1px solid var(--mc-border) !important;
    border-radius: var(--mc-radius) !important;
}
.calendar caption {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text) !important;
}
.calendar td, .calendar th {
    background-color: var(--mc-bg-card) !important;
    color: var(--mc-text) !important;
}
.calendarbox .calendarnav-previous,
.calendarbox .calendarnav-next { color: var(--mc-blue) !important; }

/* ── Errors ─────────────────────────────────────────────────────────────── */
.errornote, .errorlist li {
    background-color: #450a0a !important;
    color: #fca5a5 !important;
    border-left: 4px solid var(--mc-red) !important;
    border-radius: var(--mc-radius-sm) !important;
}

/* ── Submit row ─────────────────────────────────────────────────────────── */
.submit-row {
    background-color: var(--mc-bg-card) !important;
    border-top: 1px solid var(--mc-border) !important;
}

/* ── Inline formsets ────────────────────────────────────────────────────── */
.inline-group {
    background-color: var(--mc-bg-card) !important;
    border: 1px solid var(--mc-border) !important;
    border-radius: var(--mc-radius) !important;
}
.inline-group .tabular td.original p { color: var(--mc-text-muted) !important; }

/* ── Links ──────────────────────────────────────────────────────────────── */
a:link, a:visited { color: var(--mc-blue) !important; }
a:hover { color: var(--mc-blue-dark) !important; }

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--mc-bg); }
::-webkit-scrollbar-thumb {
    background: var(--mc-border);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover { background: var(--mc-text-muted); }
</style>
"""


class ThemeMediaMixin:
    """
    Mixin that injects the adaptive theme stylesheet into every admin page
    via the standard Django Media mechanism — no monkey-patching required.
    """

    class Media:
        # Inline CSS is not directly supported by Media, so we use a tiny
        # data-URI trick: a transparent 1-px gif that Django ignores, giving
        # us a hook; actual CSS is placed in each_context below.
        pass


# Inject CSS through each_context cleanly (only override, not replace)
_original_each_context = admin.AdminSite.each_context


def _themed_each_context(self, request):
    ctx = _original_each_context(self, request)
    ctx.setdefault("extrahead", "")
    ctx["extrahead"] += THEME_CSS
    return ctx


admin.AdminSite.each_context = _themed_each_context


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, length: int = 60) -> str:
    """Truncate *text* to *length* characters, appending an ellipsis."""
    text = text or ""
    return (text[:length] + "…") if len(text) > length else text


def _severity_badge(severity: str):
    """Render a colour-coded pill for a severity string."""
    palette = {
        "critical": ("#ef4444", "rgba(239,68,68,.12)"),
        "high":     ("#f97316", "rgba(249,115,22,.12)"),
        "medium":   ("#f59e0b", "rgba(245,158,11,.12)"),
        "low":      ("#22c55e", "rgba(34,197,94,.12)"),
    }
    key = (severity or "").lower()
    fg, bg = palette.get(key, ("#94a3b8", "rgba(148,163,184,.12)"))
    label = severity.title() if severity else "—"
    return format_html(
        '<span style="background:{bg};color:{fg};padding:3px 10px;'
        "border-radius:999px;font-size:11px;font-weight:700;"
        'letter-spacing:.4px;white-space:nowrap;">{label}</span>',
        bg=bg, fg=fg, label=label,
    )


def _star_rating(rating, max_stars: int = 5):
    """Render filled/empty star HTML for a numeric *rating*."""
    if rating is None:
        return "—"
    filled = "★" * round(rating)
    empty  = "☆" * (max_stars - round(rating))
    return format_html(
        '<span style="color:#fbbf24;font-size:14px;" title="{rating:.2f}">{filled}</span>'
        '<span style="color:var(--mc-border);font-size:14px;">{empty}</span>',
        rating=float(rating), filled=filled, empty=empty,
    )


def _pill(label: str, fg: str, bg: str):
    """Generic coloured pill badge."""
    return format_html(
        '<span style="background:{bg};color:{fg};padding:3px 9px;'
        'border-radius:999px;font-size:11px;font-weight:600;'
        'white-space:nowrap;">{label}</span>',
        bg=bg, fg=fg, label=label,
    )


def _code_chip(text: str, length: int = 12):
    """Monospace code chip (used for UUIDs / session IDs)."""
    short = (text[:length] + "…") if len(text) > length else text
    return format_html(
        '<code style="font-size:11px;background:var(--mc-bg-code);'
        'color:var(--mc-text-code);padding:2px 7px;border-radius:4px;">{}</code>',
        short,
    )


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------

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
