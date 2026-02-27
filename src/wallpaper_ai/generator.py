"""Claude API integration for generating image prompts."""

import os
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
- IMPORTANT: Explicitly include the requested art style in your prompt (e.g., "anime style", "digital painting", "oil painting style", "photorealistic"). The image generator needs clear style keywords to render correctly.

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


def generate_random_prompt(
    model: str = "claude-sonnet-4-5-20250929",
) -> tuple[str, str, str, str]:
    """Generate a random prompt based on learned preferences.

    Returns:
        Tuple of (prompt, category, style, mood)
    """
    import random

    client = anthropic.Anthropic(api_key=get_anthropic_key())

    # Get preference summary and examples
    top_rated = db.get_top_rated(limit=5)
    pref = db.get_latest_preference()

    # Build context
    context_parts = []

    if pref:
        context_parts.append(f"USER PREFERENCES:\n{pref.summary_text}")

    if top_rated:
        context_parts.append("\nHIGHLY RATED EXAMPLES:")
        for gen in top_rated:
            context_parts.append(f"- Category: {gen.category}, Style: {gen.style}, Mood: {gen.mood}")

    # If no history, use random selections
    if not top_rated and not pref:
        category = random.choice(CATEGORIES)
        style = random.choice(STYLES)
        mood = random.choice(MOODS)
    else:
        # Let Claude choose based on preferences
        selection_prompt = f"""{chr(10).join(context_parts)}

Based on the user's preferences and highly-rated examples, choose the best combination for a new wallpaper.

Available options:
- Categories: {', '.join(CATEGORIES)}
- Styles: {', '.join(STYLES)}
- Moods: {', '.join(MOODS)}

Respond with EXACTLY three lines:
CATEGORY: <chosen category>
STYLE: <chosen style>
MOOD: <chosen mood>"""

        selection = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[{"role": "user", "content": selection_prompt}],
        )

        # Parse the response
        lines = selection.content[0].text.strip().split("\n")
        category = style = mood = None

        for line in lines:
            if line.startswith("CATEGORY:"):
                category = line.split(":", 1)[1].strip()
            elif line.startswith("STYLE:"):
                style = line.split(":", 1)[1].strip()
            elif line.startswith("MOOD:"):
                mood = line.split(":", 1)[1].strip()

        # Fallback to random if parsing failed
        if not category or category not in CATEGORIES:
            category = random.choice(CATEGORIES)
        if not style or style not in STYLES:
            style = random.choice(STYLES)
        if not mood or mood not in MOODS:
            mood = random.choice(MOODS)

    # Generate the actual prompt
    prompt = generate_prompt(
        category=category,
        style=style,
        mood=mood,
        include_history=True,
        model=model,
    )

    return prompt, category, style, mood
