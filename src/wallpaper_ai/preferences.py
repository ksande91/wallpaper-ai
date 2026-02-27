"""Rating and preference learning system."""

import os
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from . import db


class PreferenceError(Exception):
    """Error with preference operations."""


def rate_wallpaper(generation_id: int, rating: int) -> None:
    """Rate a wallpaper and potentially update preferences.

    Args:
        generation_id: The ID of the generation to rate
        rating: Rating from 1-5
    """
    if not 1 <= rating <= 5:
        raise PreferenceError("Rating must be between 1 and 5")

    db.update_rating(generation_id, rating)

    # Check if we should regenerate preferences
    rated_count = db.get_rated_count()

    # Regenerate preferences every 10 ratings, or after first 5
    if rated_count >= 5 and (rated_count == 5 or rated_count % 10 == 0):
        try:
            regenerate_preferences()
        except Exception:
            # Don't fail rating if preference regeneration fails
            pass


def rate_current_wallpaper(rating: int) -> Optional[int]:
    """Rate the most recently generated wallpaper.

    Args:
        rating: Rating from 1-5

    Returns:
        The generation ID that was rated, or None if no generation found
    """
    generation = db.get_latest_generation()
    if generation and generation.id:
        rate_wallpaper(generation.id, rating)
        return generation.id
    return None


def regenerate_preferences(model: str = "claude-sonnet-4-5-20250929") -> str:
    """Regenerate the preference summary from rating history.

    Args:
        model: Claude model to use

    Returns:
        The new preference summary
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise PreferenceError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Get all rated generations
    rated = db.get_rated_generations()

    if not rated:
        raise PreferenceError("No rated generations to analyze")

    # Build the analysis prompt
    ratings_data = []
    for gen in rated:
        ratings_data.append({
            "category": gen.category,
            "style": gen.style,
            "mood": gen.mood,
            "rating": gen.rating,
            "prompt_preview": gen.prompt[:150] + "..." if len(gen.prompt) > 150 else gen.prompt,
        })

    prompt = f"""Analyze these wallpaper ratings to understand user preferences:

{_format_ratings(ratings_data)}

Based on this rating history, create a concise preference summary (2-4 sentences) that captures:
1. Preferred categories, styles, and moods
2. Specific themes or elements they seem to enjoy
3. Things to avoid based on low ratings

Write the summary as direct guidance for generating future wallpapers.
Example: "User prefers dark, atmospheric sci-fi scenes with cyberpunk elements. They favor digital painting style over realistic. Avoid overly bright or minimalist compositions."

Preference summary:"""

    message = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    if not message.content:
        raise PreferenceError("No response from Claude")

    summary = message.content[0].text.strip()

    # Save the new preference
    db.save_preference(summary)

    return summary


def _format_ratings(ratings: list[dict]) -> str:
    """Format ratings data for the prompt."""
    lines = []
    for r in ratings:
        stars = "★" * r["rating"] + "☆" * (5 - r["rating"])
        lines.append(
            f"[{stars}] {r['category']} / {r['style']} / {r['mood']}\n"
            f"   Prompt: {r['prompt_preview']}"
        )
    return "\n\n".join(lines)


def get_preference_summary() -> Optional[str]:
    """Get the current preference summary if available."""
    pref = db.get_latest_preference()
    return pref.summary_text if pref else None


def should_regenerate_preferences() -> bool:
    """Check if preferences should be regenerated."""
    pref = db.get_latest_preference()

    if not pref:
        # Regenerate if we have enough ratings but no preferences
        return db.get_rated_count() >= 5

    # Regenerate if more than 7 days old and we have new ratings
    age = datetime.now() - pref.updated_at
    if age > timedelta(days=7):
        # Check if there are new ratings since last preference update
        rated = db.get_rated_generations()
        for gen in rated:
            if gen.created_at > pref.updated_at:
                return True

    return False


def get_stats() -> dict:
    """Get statistics about ratings and preferences."""
    total = db.get_generation_count()
    rated = db.get_rated_count()
    pref = db.get_latest_preference()

    top_rated = db.get_top_rated(limit=3)
    avg_rating = None

    if rated > 0:
        all_rated = db.get_rated_generations()
        avg_rating = sum(g.rating for g in all_rated if g.rating) / len(all_rated)

    return {
        "total_generations": total,
        "rated_count": rated,
        "average_rating": round(avg_rating, 2) if avg_rating else None,
        "has_preferences": pref is not None,
        "preference_age_days": (
            (datetime.now() - pref.updated_at).days if pref else None
        ),
        "top_categories": _count_field(top_rated, "category"),
        "top_styles": _count_field(top_rated, "style"),
        "top_moods": _count_field(top_rated, "mood"),
    }


def _count_field(generations: list[db.Generation], field: str) -> list[str]:
    """Count occurrences of a field value in generations."""
    counts: dict[str, int] = {}
    for gen in generations:
        value = getattr(gen, field)
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.keys(), key=lambda x: counts[x], reverse=True)
