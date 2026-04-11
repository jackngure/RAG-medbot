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
#  Admin site customisation with Dark Theme
# ─────────────────────────────────────────────

# Force dark theme and remove theme toggle
admin.site.site_header = "🩺 MedChat Administration"
admin.site.site_title = "MedChat Admin"
admin.site.index_title = "Dashboard"

# Add custom CSS to enforce dark theme and hide theme toggle
class DarkThemeAdmin(admin.AdminSite):
    def each_context(self, request):
        context = super().each_context(request)
        context.update({
            'site_header': '🩺 MedChat Administration',
            'site_title': 'MedChat Admin',
            'index_title': 'Dashboard',
        })
        return context

# Apply dark theme CSS
admin.site.index_template = None

# Custom CSS to override Django admin with dark theme
dark_theme_css = """
<style>
    /* Force dark background everywhere */
    :root {
        --primary: #3b82f6;
        --secondary: #1e293b;
        --accent: #8b5cf6;
        --primary-fg: #f1f5f9;
    }
    
    /* Hide theme toggle completely */
    .theme-toggle, 
    [data-theme-toggle],
    .theme-toggle-button,
    button[title*="theme"],
    .toggle-theme,
    .dark-mode-toggle,
    .light-mode-toggle,
    .auto-mode-toggle,
    #theme-toggle {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
        position: absolute !important;
        width: 0 !important;
        height: 0 !important;
    }
    
    /* Remove any theme selector from header */
    #header .theme-toggle-container,
    .nav-sidebar .theme-toggle,
    .theme-toggle-wrapper {
        display: none !important;
    }
    
    /* Dark theme for body and main containers */
    body, #container, #content, .dashboard, .module, .main {
        background-color: #0f172a !important;
        color: #e2e8f0 !important;
    }
    
    /* Dark header */
    #header {
        background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%) !important;
        color: #f1f5f9 !important;
        border-bottom: 1px solid #334155 !important;
    }
    
    #branding h1, #branding h1 a:link, #branding h1 a:visited {
        color: #f1f5f9 !important;
        font-weight: 600 !important;
    }
    
    /* Dark sidebar */
    #nav-sidebar, .module caption, .sidebar {
        background-color: #1e293b !important;
        color: #cbd5e1 !important;
    }
    
    /* Dark content area */
    #content-main, #content-related {
        background-color: #0f172a !important;
    }
    
    /* Dark cards/modules */
    .module, .module h2, .module caption, .inline-group h2 {
        background-color: #1e293b !important;
        color: #f1f5f9 !important;
        border-radius: 8px !important;
        border: 1px solid #334155 !important;
    }
    
    .module h2, .module caption, .inline-group h2 {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%) !important;
        border-bottom: 1px solid #334155 !important;
    }
    
    /* Dark tables */
    table, table thead th, table tbody td {
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
        border-color: #334155 !important;
    }
    
    table thead th {
        background-color: #0f172a !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
        border-bottom: 2px solid #334155 !important;
    }
    
    table tbody tr:hover td {
        background-color: #334155 !important;
    }
    
    /* Dark form elements */
    input, textarea, select, .vTextField, .vLargeTextField, .vDateField, .vTimeField {
        background-color: #0f172a !important;
        color: #e2e8f0 !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
    }
    
    input:focus, textarea:focus, select:focus {
        border-color: #3b82f6 !important;
        outline: none !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
    }
    
    /* Dark buttons */
    .button, input[type=submit], input[type=button], .submit-row input, .default {
        background-color: #3b82f6 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 8px 16px !important;
        font-weight: 500 !important;
    }
    
    .button:hover, input[type=submit]:hover, .default:hover {
        background-color: #2563eb !important;
        transform: translateY(-1px) !important;
    }
    
    .deletelink {
        background-color: #dc2626 !important;
    }
    
    .deletelink:hover {
        background-color: #b91c1c !important;
    }
    
    /* Dark breadcrumbs */
    div.breadcrumbs {
        background-color: #1e293b !important;
        color: #94a3b8 !important;
        border-bottom: 1px solid #334155 !important;
    }
    
    div.breadcrumbs a {
        color: #60a5fa !important;
    }
    
    /* Dark pagination */
    .paginator {
        background-color: #1e293b !important;
        color: #94a3b8 !important;
        border-top: 1px solid #334155 !important;
    }
    
    .paginator a:link, .paginator a:visited {
        background-color: #334155 !important;
        color: #e2e8f0 !important;
    }
    
    /* Dark object tools */
    .object-tools a:link, .object-tools a:visited {
        background-color: #3b82f6 !important;
        color: white !important;
    }
    
    /* Dark filter sidebar */
    #changelist-filter {
        background-color: #1e293b !important;
        border-left: 1px solid #334155 !important;
    }
    
    #changelist-filter h3 {
        background-color: #0f172a !important;
        color: #94a3b8 !important;
    }
    
    #changelist-filter ul li a {
        color: #94a3b8 !important;
    }
    
    #changelist-filter ul li.selected a {
        color: #60a5fa !important;
        font-weight: bold !important;
    }
    
    /* Dark calendar/time widget */
    .calendarbox, .clockbox {
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
        border: 1px solid #475569 !important;
    }
    
    .calendar caption {
        background-color: #0f172a !important;
        color: #f1f5f9 !important;
    }
    
    .calendar td, .calendar th {
        background-color: #1e293b !important;
        color: #e2e8f0 !important;
    }
    
    /* Dark help text */
    .help, .help-block {
        color: #94a3b8 !important;
    }
    
    /* Dark errors */
    .errorlist li {
        background-color: #450a0a !important;
        color: #fca5a5 !important;
        border-left: 4px solid #dc2626 !important;
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: #0f172a;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #334155;
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #475569;
    }
    
    /* Ensure all text is readable */
    a:link, a:visited {
        color: #60a5fa !important;
    }
    
    .results {
        background-color: #1e293b !important;
    }
    
    /* Dark inline formsets */
    .inline-group .tabular td.original p {
        color: #94a3b8 !important;
    }
    
    /* Dark fieldset legends */
    .aligned label {
        color: #cbd5e1 !important;
    }
</style>

<script>
    // Remove any theme toggle buttons from DOM after page load
    document.addEventListener('DOMContentLoaded', function() {
        // Remove theme toggle elements
        const selectors = [
            '.theme-toggle',
            '[data-theme-toggle]',
            '.theme-toggle-button',
            '.dark-mode-toggle',
            '.light-mode-toggle',
            '.auto-mode-toggle',
            '#theme-toggle',
            '.toggle-theme',
            '[aria-label*="theme"]',
            'button:contains("Dark")',
            'button:contains("Light")',
            'button:contains("Auto")'
        ];
        
        selectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => {
                if (el) el.remove();
            });
        });
        
        // Remove any theme-related script elements
        document.querySelectorAll('script').forEach(script => {
            if (script.textContent && script.textContent.includes('theme')) {
                script.remove();
            }
        });
        
        // Remove any localStorage theme overrides
        localStorage.removeItem('theme');
        localStorage.removeItem('django-admin-theme');
        
        // Force dark class on body
        document.body.classList.add('dark-theme');
        document.body.setAttribute('data-theme', 'dark');
        
        // Override any inline styles that might set light theme
        const style = document.createElement('style');
        style.textContent = `
            body, html {
                background-color: #0f172a !important;
                color-scheme: dark !important;
            }
        `;
        document.head.appendChild(style);
    });
    
    // Mutation observer to catch dynamically added theme toggles
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) { // Element node
                    if (node.classList && (
                        node.classList.contains('theme-toggle') ||
                        node.classList.contains('dark-mode-toggle') ||
                        node.classList.contains('light-mode-toggle')
                    )) {
                        node.remove();
                    }
                }
            });
        });
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
</script>
"""

# Inject CSS into admin
def add_dark_theme(request):
    from django.utils.safestring import mark_safe
    return mark_safe(dark_theme_css)

# Monkey patch admin base template
from django.contrib.admin.templatetags.admin_modify import submit_row
from django.contrib.admin import AdminSite

# Add the CSS to extrahead
original_each_context = AdminSite.each_context
def each_context_with_dark_theme(self, request):
    context = original_each_context(self, request)
    if 'extrahead' not in context:
        context['extrahead'] = ''
    context['extrahead'] += dark_theme_css
    return context

AdminSite.each_context = each_context_with_dark_theme


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
        "critical": ("#ef4444", "#7f1d1d"),
        "high":     ("#f97316", "#7c2d12"),
        "medium":   ("#f59e0b", "#78350f"),
        "low":      ("#22c55e", "#14532d"),
    }
    key = (severity or "").lower()
    fg, bg = colours.get(key, ("#9ca3af", "#374151"))
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
        '<span style="color:#fbbf24;font-size:14px;" title="{rating:.2f}">{filled}</span>'
        '<span style="color:#4b5563;font-size:14px;">{empty}</span>',
        rating=rating, filled=filled, empty=empty,
    )


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
        colour = "#3b82f6" if count else "#64748b"
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
                '<span style="background:#1e3a5f;color:#93c5fd;padding:2px 8px;'
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
                '<a style="color:#60a5fa;font-weight:600;" href="{}">{}</a>',
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
            '<code style="font-size:12px;background:#334155;padding:2px 6px;border-radius:4px;color:#e2e8f0;">{}</code>',
            sid[:12] + "…" if len(sid) > 12 else sid,
        )

    @admin.display(description="Messages", ordering="message_count")
    def message_count_badge(self, obj):
        try:
            count = obj.messages.count()
        except AttributeError:
            count = 0
        return format_html(
            '<strong style="color:#e2e8f0;">{}</strong>', count
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
            '<code style="font-size:11px;background:#334155;padding:2px 6px;border-radius:4px;color:#e2e8f0;">{}</code>',
            sid + "…",
        )

    @admin.display(description="Role", ordering="role")
    def role_badge(self, obj):
        colours = {
            "user":      ("#a78bfa", "#2e1065"),
            "assistant": ("#34d399", "#064e3b"),
            "system":    ("#38bdf8", "#082f49"),
        }
        key = (obj.role or "").lower()
        fg, bg = colours.get(key, ("#94a3b8", "#374151"))
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
                '<span style="color:#ef4444;font-size:16px;" title="Emergency detected">🚨</span>'
            )
        return format_html('<span style="color:#4b5563;">—</span>')


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
            '<code style="font-size:12px;background:#334155;padding:2px 6px;border-radius:4px;color:#e2e8f0;">{}</code>',
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
                '<span style="background:#064e3b;color:#6ee7b7;padding:2px 7px;'
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
        colour = "#22c55e" if count else "#64748b"
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
                '<span style="background:#7f1d1d;color:#fca5a5;padding:2px 7px;'
                'border-radius:8px;font-size:11px;margin:2px;display:inline-block;">{}</span>',
                k.keyword if hasattr(k, "keyword") else str(k),
            )
            for k in keywords
        )
        return format_html(tags) if tags else "—"

    @admin.display(description="📍 Location", ordering="location_shared")
    def location_shared_icon(self, obj):
        if obj.location_shared:
            return format_html('<span style="color:#22c55e;font-size:15px;" title="Location shared">✔</span>')
        return format_html('<span style="color:#64748b;" title="Not shared">✘</span>')


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
            '<span style="color:#3b82f6;font-weight:600;">{new}</span>'
            '<span style="color:#64748b;"> / </span>'
            '<span style="color:#a78bfa;font-weight:600;">{ret}</span>',
            new=obj.new_users or 0,
            ret=obj.returning_users or 0,
        )

    @admin.display(description="Avg. Rating", ordering="average_rating")
    def star_avg_rating(self, obj):
        return _star_rating(obj.average_rating)
