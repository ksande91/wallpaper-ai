# Wallpaper AI

AI-powered wallpaper generator for Arch Linux + Hyprland. Generates unique desktop wallpapers using Claude for creative prompts and FAL.ai or Google Gemini for image generation, with a learning system that adapts to your preferences over time.

## Features

- **Interactive Terminal UI** - Beautiful Textual-based interface for selecting categories, styles, and moods
- **AI Prompt Generation** - Uses Claude to create detailed, evocative image prompts
- **Multiple Image Providers** - FAL.ai (SDXL, FLUX) or Google Gemini (Imagen, native generation)
- **swww Integration** - Smooth wallpaper transitions with configurable effects
- **pywal Integration** - Auto-generate terminal, Hyprland, and Waybar colors from wallpapers
- **Rating System** - Rate wallpapers 1-5 stars to train the preference model
- **Preference Learning** - System learns from your ratings to generate better wallpapers
- **Hyprland Keybinds** - Quick access via keyboard shortcuts

## Prerequisites

- Arch Linux with Hyprland
- Python 3.11+
- swww (wallpaper daemon)
- pywal (optional, for color generation)
- API keys for Anthropic (Claude) and your chosen image provider

## Installation

```bash
# Clone or navigate to the project
cd wallpaper-ai

# Install with pip
pip install -e .

# Or with pipx for isolated install
pipx install -e .
```

## Configuration

### Environment Variables

```bash
# Required
export ANTHROPIC_API_KEY="your-anthropic-key"

# For FAL.ai provider (default)
export FAL_KEY="your-fal-key"

# For Gemini provider
export GEMINI_API_KEY="your-gemini-key"
```

Add these to your `~/.bashrc`, `~/.zshrc`, or shell config. You only need the key for your chosen image provider.

### Initialize

```bash
wallpaper-ai init
```

This creates:
- Config file at `~/.config/wallpaper-ai/config.toml`
- Database at `~/.local/share/wallpaper-ai/wallpapers.db`
- Images directory at `~/.local/share/wallpaper-ai/images/`

### swww Setup

Ensure swww-daemon is running (add to Hyprland startup):

```conf
# ~/.config/hypr/hyprland.conf
exec-once = swww-daemon
```

### Hyprland Keybinds

Add to your Hyprland config:

```conf
# Launch wallpaper selector
bind = $mainMod, W, exec, wallpaper-ai

# Rate current wallpaper (1-5 stars)
bind = $mainMod, F1, exec, wallpaper-ai --rate 1
bind = $mainMod, F2, exec, wallpaper-ai --rate 2
bind = $mainMod, F3, exec, wallpaper-ai --rate 3
bind = $mainMod, F4, exec, wallpaper-ai --rate 4
bind = $mainMod, F5, exec, wallpaper-ai --rate 5

# Generate random wallpaper using learned preferences
bind = $mainMod SHIFT, W, exec, wallpaper-ai --random
```

## Usage

### Interactive UI

```bash
wallpaper-ai
```

Navigate with arrow keys, select options, and generate wallpapers.

### Command Line

```bash
# Generate with specific options
wallpaper-ai generate -c "Cyberpunk" -s "Digital Painting" -m "Dark"

# Generate with custom input
wallpaper-ai generate -c "Space" -x "nebula with bioluminescent creatures"

# Random generation using learned preferences
wallpaper-ai --random

# Rate current wallpaper
wallpaper-ai --rate 5

# View history
wallpaper-ai history

# View statistics and preferences
wallpaper-ai stats

# Set wallpaper from history
wallpaper-ai set 42

# Regenerate preference summary
wallpaper-ai regenerate-prefs

# Show keybind config
wallpaper-ai --keybinds
```

## Categories, Styles & Moods

**Categories:** Sci-Fi, Nature, Fantasy, Abstract, Cyberpunk, Space, Architecture

**Styles:** Realistic, Digital Painting, Anime, Oil Painting, Minimalist, Photographic

**Moods:** Epic, Serene, Dark, Vibrant, Mysterious, Dreamy

## How It Works

1. **Selection**: Choose category, style, mood, and optional custom input
2. **Prompt Generation**: Claude creates a detailed image prompt incorporating:
   - Your selections
   - Highly-rated examples from history (few-shot learning)
   - Low-rated examples to avoid
   - Your preference summary
3. **Image Generation**: FAL.ai or Gemini generates a 1920x1080 wallpaper
4. **Wallpaper Setting**: swww applies the wallpaper with smooth transition
5. **Rating**: Rate the wallpaper to improve future generations

## Learning System

The preference learning system:

- Collects your ratings (1-5 stars)
- After 5+ ratings, generates a preference summary using Claude
- Regenerates preferences every 10 new ratings
- Includes top 5 highly-rated and bottom 3 low-rated examples in prompts
- Preference summary guides future generations toward your taste

## File Locations

- **Config**: `~/.config/wallpaper-ai/config.toml`
- **Database**: `~/.local/share/wallpaper-ai/wallpapers.db`
- **Images**: `~/.local/share/wallpaper-ai/images/`

## License

MIT
