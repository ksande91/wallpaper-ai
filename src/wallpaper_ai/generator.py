"""Claude API integration for generating image prompts."""

import os
import random
from typing import Optional

import anthropic

from . import db

# Available categories, styles, and moods
CATEGORIES = [
    "Sci-Fi",
    "Nature",
    "Fantasy",
    "Abstract",
    "Cyberpunk",
    "Space",
    "Architecture",
]

STYLES = [
    "Realistic",
    "Digital Painting",
    "Anime",
    "Oil Painting",
    "Minimalist",
    "Photographic",
]

MOODS = [
    "Epic",
    "Serene",
    "Dark",
    "Vibrant",
    "Mysterious",
    "Dreamy",
]


class PromptGenerationError(Exception):
    """Error generating prompt."""


def get_anthropic_key() -> str:
    """Get the Anthropic API key from environment."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise PromptGenerationError(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Get your key at https://console.anthropic.com/"
        )
    return key


def build_system_prompt() -> str:
    """Build the system prompt for Claude."""
    return """You are an expert at creating detailed, evocative image prompts for AI image generators.
Your prompts should be optimized for generating stunning desktop wallpapers.

Key requirements for all prompts:
- Aspect ratio: 16:9 widescreen composition
- No text, UI elements, watermarks, or signatures
- Suitable for desktop wallpaper (balanced composition, not too busy in corners)
- High quality, detailed descriptions that evoke mood and atmosphere
- Focus on lighting, color palette, and atmosphere
- IMPORTANT: Explicitly include the requested art style(s) in your prompt (e.g., "anime style", "digital painting", "oil painting style", "photorealistic"). The image generator needs clear style keywords to render correctly.
- When the user supplies multiple categories or styles (comma-separated), blend them into a single coherent scene rather than describing them separately. Treat the combination as the creative brief (e.g., "Sci-Fi + Cyberpunk" → one scene with both genres infused).

Output ONLY the prompt text, no explanations or formatting."""


def build_examples_context(
    top_rated: list[db.Generation],
    low_rated: list[db.Generation],
) -> str:
    """Build few-shot examples from rated history."""
    if not top_rated and not low_rated:
        return ""

    parts = []

    if top_rated:
        parts.append("HIGHLY RATED EXAMPLES (user loves these styles):")
        for gen in top_rated:
            parts.append(f"- [{gen.category}/{gen.style}/{gen.mood}] Rating: {gen.rating}/5")
            parts.append(f"  Prompt: {gen.prompt[:200]}...")

    if low_rated:
        parts.append("\nLOW RATED EXAMPLES (avoid these approaches):")
        for gen in low_rated:
            parts.append(f"- [{gen.category}/{gen.style}/{gen.mood}] Rating: {gen.rating}/5")
            parts.append(f"  Prompt: {gen.prompt[:200]}...")

    return "\n".join(parts)


def build_user_prompt(
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
    preference_summary: Optional[str] = None,
    examples_context: Optional[str] = None,
) -> str:
    """Build the user prompt for Claude."""
    parts = []

    if preference_summary:
        parts.append(f"USER PREFERENCES:\n{preference_summary}\n")

    if examples_context:
        parts.append(f"{examples_context}\n")

    parts.append(f"""Generate a creative image prompt for a desktop wallpaper with:
- Category: {category}
- Style: {style} (you MUST explicitly include this style in the prompt)
- Mood(s): {mood}""")

    if custom_input:
        parts.append(f"- Additional input: {custom_input}")

    parts.append("""
Create a detailed, evocative prompt that captures the essence of these selections.
Remember: 16:9 aspect ratio, no text or UI elements, suitable for desktop wallpaper.""")

    return "\n".join(parts)


def generate_prompt(
    category: str,
    style: str,
    mood: str,
    custom_input: Optional[str] = None,
    include_history: bool = True,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """Generate an image prompt using Claude.

    Args:
        category: The category (e.g., "Sci-Fi", "Nature")
        style: The style (e.g., "Realistic", "Anime")
        mood: The mood (e.g., "Epic", "Serene")
        custom_input: Optional custom text input from user
        include_history: Whether to include rated examples
        model: Claude model to use

    Returns:
        The generated image prompt
    """
    client = anthropic.Anthropic(api_key=get_anthropic_key())

    # Get examples from history
    top_rated = []
    low_rated = []
    preference_summary = None

    if include_history:
        top_rated = db.get_top_rated(limit=5)
        low_rated = db.get_low_rated(limit=3)
        pref = db.get_latest_preference()
        if pref:
            preference_summary = pref.summary_text

    examples_context = build_examples_context(top_rated, low_rated)

    user_prompt = build_user_prompt(
        category=category,
        style=style,
        mood=mood,
        custom_input=custom_input,
        preference_summary=preference_summary,
        examples_context=examples_context,
    )

    message = client.messages.create(
        model=model,
        max_tokens=500,
        system=build_system_prompt(),
        messages=[
            {"role": "user", "content": user_prompt}
        ],
    )

    if not message.content:
        raise PromptGenerationError("No response from Claude")

    return message.content[0].text.strip()


def _score_increment(rating: int) -> float:
    """Convert a 1-5 rating into a sampling-weight increment.

    5★ adds a lot, 3★ is neutral-ish, 1-2★ adds almost nothing (but never zero,
    so a previously-disliked value can still recover if it gets a good rating later).
    """
    table = {1: 0.05, 2: 0.2, 3: 0.6, 4: 1.5, 5: 3.0}
    return table.get(rating, 0.5)


def _build_weights(
    values: list[str],
    rated: list[db.Generation],
    field: str,
) -> tuple[dict[str, float], dict[str, int]]:
    """Compute sampling weights + observation counts for a dimension.

    Splits comma-separated values (e.g. "Sci-Fi, Cyberpunk") so each contributes
    independently. Uses a uniform prior of 1.0 so every option keeps a real chance.
    """
    weights = {v: 1.0 for v in values}
    counts = {v: 0 for v in values}
    for gen in rated:
        raw = getattr(gen, field) or ""
        for token in (t.strip() for t in raw.split(",")):
            if token in weights and gen.rating is not None:
                weights[token] += _score_increment(gen.rating)
                counts[token] += 1
    return weights, counts


def _sample_dimension(
    values: list[str],
    rated: list[db.Generation],
    field: str,
    explore_rate: float = 0.25,
) -> str:
    """Pick one value via weighted sampling, or uniformly from underexplored ones."""
    weights, counts = _build_weights(values, rated, field)

    if random.random() < explore_rate:
        min_count = min(counts.values())
        underexplored = [v for v, c in counts.items() if c <= min_count + 1]
        if underexplored:
            return random.choice(underexplored)

    return random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]


def generate_random_prompt(
    model: str = "claude-sonnet-4-5-20250929",
) -> tuple[str, str, str, str]:
    """Generate a random prompt using weighted sampling over rated history.

    Replaces the previous "ask Claude to pick the best combo" approach, which
    converged on the same selections. Sampling gives every well-rated value a
    real chance, and 25% of generations actively explore underused options.

    Returns:
        Tuple of (prompt, category, style, mood)
    """
    rated = db.get_rated_generations()

    if not rated:
        category = random.choice(CATEGORIES)
        style = random.choice(STYLES)
        mood = random.choice(MOODS)
    else:
        category = _sample_dimension(CATEGORIES, rated, "category")
        style = _sample_dimension(STYLES, rated, "style")
        mood = _sample_dimension(MOODS, rated, "mood")

    prompt = _generate_random_body(
        category=category,
        style=style,
        mood=mood,
        model=model,
    )

    return prompt, category, style, mood


def _generate_random_body(
    category: str,
    style: str,
    mood: str,
    model: str,
) -> str:
    """Generate the prompt text for a random pick.

    Unlike generate_prompt, this deliberately omits the hard preference summary
    (sampling already encoded preferences) and asks Claude to diverge from
    recent examples instead of mimicking them.
    """
    client = anthropic.Anthropic(api_key=get_anthropic_key())

    recent_prompts = [g.prompt for g in db.get_recent_generations(limit=4)]
    top_rated = db.get_top_rated(limit=2)

    parts = []
    if top_rated:
        parts.append("Loose stylistic reference (do NOT copy — diverge in setting, subject, and composition):")
        for gen in top_rated:
            parts.append(f"- [{gen.category}/{gen.style}/{gen.mood}] {gen.prompt[:160]}...")
        parts.append("")

    if recent_prompts:
        parts.append("Avoid repeating subjects/compositions from these recent generations:")
        for p in recent_prompts:
            parts.append(f"- {p[:140]}...")
        parts.append("")

    parts.append(f"""Generate a fresh image prompt for a desktop wallpaper with:
- Category: {category}
- Style: {style} (you MUST explicitly include this style in the prompt)
- Mood(s): {mood}

Be inventive — pick a different setting, time of day, color palette, or focal subject than the references above.
Remember: 16:9 aspect ratio, no text or UI elements, suitable for desktop wallpaper.""")

    message = client.messages.create(
        model=model,
        max_tokens=500,
        temperature=1.0,
        system=build_system_prompt(),
        messages=[{"role": "user", "content": "\n".join(parts)}],
    )

    if not message.content:
        raise PromptGenerationError("No response from Claude")

    return message.content[0].text.strip()
