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
        Dict with keys: enable_pywal, enable_hyprlock, enable_nvim,
        nvim_reload_cmd, enable_hue, enable_openrgb.
    """
    config = load_config()
    theming = config.get("theming", {})
    return {
        "enable_pywal": theming.get("enable_pywal", True),
        "enable_hyprlock": theming.get("enable_hyprlock", True),
        "enable_nvim": theming.get("enable_nvim", True),
        "nvim_reload_cmd": theming.get("nvim_reload_cmd", DEFAULT_NVIM_RELOAD_CMD),
        "enable_hue": theming.get("enable_hue", False),
        "enable_openrgb": theming.get("enable_openrgb", False),
    }


def get_hue_config() -> dict:
    """Get Hue bridge configuration.

    Returns:
        Dict with bridge_ip, api_key, transition_time, and lights mapping.
        Light values can be int (color index) or "dominant" (auto-detect).
    """
    config = load_config()
    hue = config.get("hue", {})
    lights_raw = hue.get("lights", {})
    lights = {}
    for k, v in lights_raw.items():
        if isinstance(v, str) and v.lower() == "dominant":
            lights[str(k)] = "dominant"
        else:
            lights[str(k)] = int(v)
    return {
        "bridge_ip": hue.get("bridge_ip", ""),
        "api_key": hue.get("api_key", ""),
        "transition_time": hue.get("transition_time", 10),
        "brightness": hue.get("brightness", 254),
        "lights": lights,
    }


def get_openrgb_config() -> dict[str, int | str]:
    """Get OpenRGB device-to-color mapping.

    Returns:
        Dict mapping device IDs (str) to palette color indices (int)
        or "dominant" for auto-detected prominent color.
    """
    config = load_config()
    openrgb = config.get("openrgb", {})
    devices_raw = openrgb.get("devices", {})
    result = {}
    for k, v in devices_raw.items():
        if isinstance(v, str) and v.lower() == "dominant":
            result[str(k)] = "dominant"
        else:
            result[str(k)] = int(v)
    return result


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

    width = generation.get("width", 1920)
    height = generation.get("height", 1080)

    from math import gcd
    g = gcd(width, height)
    aspect_ratio = f"{width // g}:{height // g}"

    return {
        "provider": provider,
        "model": model_id,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
    }
