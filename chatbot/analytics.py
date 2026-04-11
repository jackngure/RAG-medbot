# chatbot/analytics.py
"""
Daily analytics generation for the medical chatbot.
Generates metrics about user activity, emergencies, feedback, and diseases.
"""

import logging
from datetime import date, timedelta
from collections import Counter
from typing import Optional

from django.db.models import Avg, Count
from django.db.models.functions import ExtractHour
from django.utils import timezone

from .models import (
    ChatAnalytics,
    ChatMessage,
    EmergencyLog,
    FirstAidFeedback,
    SymptomLog,
    UserProfile,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOP_DISEASES_LIMIT = 10
PEAK_HOURS_LIMIT = 5
ERROR_MESSAGE_MAX_LENGTH = 500
ERROR_SAVE_ATTEMPT = "Could not save error state to analytics record"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _date_window(target_date: date) -> tuple[timezone.datetime, timezone.datetime]:
    """Return a timezone-aware (start, end) window for a given calendar date."""
    start = timezone.make_aware(
        timezone.datetime(target_date.year, target_date.month, target_date.day)
    )
    return start, start + timedelta(days=1)


def _extract_disease_names(matched_diseases) -> list[str]:
    """
    Parse a matched_diseases value from a SymptomLog into a flat list of names.

    Handles three storage formats:
      - dict  → single disease record, e.g. {"name": "Malaria", ...}
      - list  → multiple disease records or plain strings
      - str   → bare disease name
    """
    if isinstance(matched_diseases, dict):
        name = matched_diseases.get("name")
        return [name] if name else []

    if isinstance(matched_diseases, (list, tuple)):
        names = []
        for item in matched_diseases:
            if isinstance(item, dict):
                name = item.get("name")
            elif isinstance(item, str):
                name = item
            else:
                name = None
            if name:
                names.append(name)
        return names

    if isinstance(matched_diseases, str):
        return [matched_diseases]

    return []


def _count_diseases(yesterday_start: timezone.datetime, yesterday_end: timezone.datetime) -> dict:
    """
    Tally disease occurrences from SymptomLogs within the given window.

    Returns a dict of {disease_name: count} for the top N diseases.
    """
    counter: Counter = Counter()

    logs = SymptomLog.objects.filter(
        timestamp__gte=yesterday_start,
        timestamp__lt=yesterday_end,
        matched_diseases__isnull=False,
    ).only("matched_diseases").iterator()

    for log in logs:
        try:
            names = _extract_disease_names(log.matched_diseases)
            counter.update(names)
        except (TypeError, AttributeError) as exc:
            logger.warning("Could not parse matched_diseases (pk=%s): %s", log.pk, exc)

    return dict(counter.most_common(TOP_DISEASES_LIMIT))


# ---------------------------------------------------------------------------
# Daily analytics
# ---------------------------------------------------------------------------


def generate_daily_analytics(target_date: Optional[date] = None) -> Optional[ChatAnalytics]:
    """
    Generate an analytics report for *target_date* (defaults to yesterday).

    Calculates:
    - User activity (active, new, returning, cumulative)
    - Message statistics
    - Emergency detection metrics
    - User feedback ratings and distribution
    - Most common diseases
    - Peak usage hours

    Returns:
        Saved ChatAnalytics instance, or None if a fatal error occurs.
    """
    if target_date is None:
        target_date = (timezone.now() - timedelta(days=1)).date()

    window_start, window_end = _date_window(target_date)

    try:
        analytics, created = ChatAnalytics.objects.get_or_create(date=target_date)
        if created:
            logger.debug("Created new analytics record for %s", target_date)

        # ----------------------------------------------------------------
        # User metrics
        # ----------------------------------------------------------------

        analytics.active_users = UserProfile.objects.filter(
            last_seen__gte=window_start,
            last_seen__lt=window_end,
        ).count()

        analytics.new_users = UserProfile.objects.filter(
            first_seen__gte=window_start,
            first_seen__lt=window_end,
        ).count()

        analytics.returning_users = UserProfile.objects.filter(
            first_seen__lt=window_start,
            last_seen__gte=window_start,
            last_seen__lt=window_end,
        ).count()

        analytics.total_users_cumulative = UserProfile.objects.filter(
            first_seen__lt=window_end,
        ).count()

        # ----------------------------------------------------------------
        # Message metrics
        # ----------------------------------------------------------------

        messages_qs = ChatMessage.objects.filter(
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        )

        analytics.total_messages = messages_qs.count()

        session_counts = (
            messages_qs
            .values("user_session")
            .annotate(msg_count=Count("id"))
        )
        session_count = len(session_counts)  # evaluate once

        analytics.avg_messages_per_user = (
            round(analytics.total_messages / session_count, 2)
            if session_count > 0
            else 0
        )

        # ----------------------------------------------------------------
        # Emergency metrics
        # ----------------------------------------------------------------

        emergencies_qs = EmergencyLog.objects.filter(
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        )

        analytics.emergency_detections = emergencies_qs.count()

        analytics.location_shares = emergencies_qs.filter(location_shared=True).count()

        analytics.emergency_rate = (
            round((analytics.emergency_detections / session_count) * 100, 2)
            if session_count > 0
            else 0
        )

        # ----------------------------------------------------------------
        # Feedback metrics
        # ----------------------------------------------------------------

        feedback_agg = FirstAidFeedback.objects.filter(
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        ).aggregate(
            avg_rating=Avg("rating"),
            total_feedback=Count("id"),
        )

        analytics.average_rating = (
            round(feedback_agg["avg_rating"], 2)
            if feedback_agg["avg_rating"] is not None
            else None
        )
        analytics.total_feedback = feedback_agg["total_feedback"] or 0

        rating_rows = (
            FirstAidFeedback.objects.filter(
                timestamp__gte=window_start,
                timestamp__lt=window_end,
                rating__isnull=False,
            )
            .values("rating")
            .annotate(count=Count("id"))
        )
        analytics.rating_distribution = {row["rating"]: row["count"] for row in rating_rows}

        # ----------------------------------------------------------------
        # Disease metrics
        # ----------------------------------------------------------------

        analytics.top_diseases = _count_diseases(window_start, window_end)

        # ----------------------------------------------------------------
        # Peak usage hours
        # ----------------------------------------------------------------

        peak_hours_qs = (
            messages_qs
            .annotate(hour=ExtractHour("timestamp"))
            .values("hour")
            .annotate(message_count=Count("id"))
            .order_by("-message_count")[:PEAK_HOURS_LIMIT]
        )
        # Materialise to plain dicts so the value is JSON-serialisable
        analytics.peak_hours = list(peak_hours_qs.values("hour", "message_count"))

        # ----------------------------------------------------------------
        # Finalise
        # ----------------------------------------------------------------

        analytics.is_complete = True
        analytics.error_occurred = False
        analytics.error_message = ""
        analytics.save()

        logger.info(
            "Analytics generated for %s — active_users=%d, emergencies=%d, avg_rating=%s",
            target_date,
            analytics.active_users,
            analytics.emergency_detections,
            analytics.average_rating,
        )

        return analytics

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Error generating analytics for %s: %s",
            target_date,
            exc,
            exc_info=True,
        )
        try:
            analytics, _ = ChatAnalytics.objects.get_or_create(date=target_date)
            analytics.is_complete = False
            analytics.error_occurred = True
            analytics.error_message = str(exc)[:ERROR_MESSAGE_MAX_LENGTH]
            analytics.save()
        except Exception as save_exc:  # noqa: BLE001
            logger.error("%s: %s", ERROR_SAVE_ATTEMPT, save_exc)

        return None


# ---------------------------------------------------------------------------
# Weekly summary
# ---------------------------------------------------------------------------


def generate_weekly_summary(end_date: Optional[date] = None) -> Optional[dict]:
    """
    Aggregate daily analytics records into a 7-day summary.

    Args:
        end_date: Exclusive upper bound (defaults to today). The summary
                  covers the 7 calendar days that precede this date.

    Returns:
        Dictionary with aggregated metrics, or None if no complete records exist.
    """
    if end_date is None:
        end_date = timezone.now().date()

    period_start = end_date - timedelta(days=7)

    records = list(
        ChatAnalytics.objects.filter(
            date__gte=period_start,
            date__lt=end_date,
            is_complete=True,
        )
    )

    if not records:
        logger.warning(
            "generate_weekly_summary: no complete analytics records between %s and %s",
            period_start,
            end_date,
        )
        return None

    # Aggregate disease counts across all days in the window
    all_diseases: Counter = Counter()
    for record in records:
        if record.top_diseases:
            all_diseases.update(record.top_diseases)

    # Average rating: only count days that actually have a rating
    rated_records = [r for r in records if r.average_rating is not None]
    avg_daily_rating = (
        round(sum(r.average_rating for r in rated_records) / len(rated_records), 2)
        if rated_records
        else None
    )

    return {
        "period_start": period_start,
        "period_end": end_date - timedelta(days=1),
        "total_days": len(records),
        "total_active_users": sum(r.active_users for r in records),
        "total_new_users": sum(r.new_users for r in records),
        "total_emergencies": sum(r.emergency_detections for r in records),
        "total_messages": sum(r.total_messages for r in records),
        "avg_daily_rating": avg_daily_rating,
        "top_diseases_week": dict(all_diseases.most_common(TOP_DISEASES_LIMIT)),
    }
