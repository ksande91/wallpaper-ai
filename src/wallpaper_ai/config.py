"""Configuration loading utilities."""

from pathlib import Path

import toml


def get_config_path() -> Path:
    """Get the config file path."""
    return Path.home() / ".config" / "wallpaper-ai" / "config.toml"


def load_config() -> dict:
    """Load configuration from file."""
    config_path = get_config_path()
    if config_path.exists():
        return toml.load(config_path)
    return {}


DEFAULT_NVIM_RELOAD_CMD = "silent! source $HOME/.cache/wal/colors-wal.vim"


def get_theming_config() -> dict:
    """Get theming configuration options.

    Returns:
        Dict with keys: enable_pywal, enable_hyprlock, enable_nvim, nvim_reload_cmd.
    """
    config = load_config()
    theming = config.get("theming", {})
    return {
        "enable_pywal": theming.get("enable_pywal", True),
        "enable_hyprlock": theming.get("enable_hyprlock", True),
        "enable_nvim": theming.get("enable_nvim", True),
        "nvim_reload_cmd": theming.get("nvim_reload_cmd", DEFAULT_NVIM_RELOAD_CMD),
    }


def get_generation_config() -> dict:
    """Get generation configuration options.

    Returns:
        Dict with provider, model, width, height settings
    """
    config = load_config()
    generation = config.get("generation", {})

    provider = generation.get("provider", "fal")

    # Map friendly model names to API model IDs
    fal_models = {
        "sdxl": "fal-ai/fast-sdxl",
        "sdxl-lightning": "fal-ai/fast-lightning-sdxl",
        "flux-schnell": "fal-ai/flux/schnell",
        "flux-dev": "fal-ai/flux/dev",
        "flux-pro": "fal-ai/flux-pro",
        "nano-banana-2": "fal-ai/nano-banana-2",
    }

    gemini_models = {
        "imagen-3": "imagen-3.0-generate-002",
        "gemini-2.5-flash-image": "gemini-2.5-flash-image",
        "gemini-3-pro": "gemini-3-pro-image-preview",
    }

    # Get model name with provider-appropriate default
    default_model = "nano-banana-2" if provider == "fal" else "imagen-3"
    model_name = generation.get("model", default_model)

    # Map to API model ID based on provider
    if provider == "fal":
        model_id = fal_models.get(model_name, model_name)
    else:
        model_id = gemini_models.get(model_name, model_name)

    return {
        "provider": provider,
        "model": model_id,
        "width": generation.get("width", 1920),
        "height": generation.get("height", 1080),
    }
