"""Wallpaper setting via awww with pywal and hyprlock integration."""

import os
import stat
import subprocess
from pathlib import Path
from typing import Optional

from . import db


DEFAULT_NVIM_RELOAD_CMD = "silent! source $HOME/.cache/wal/colors-wal.vim"


# Pywal template for Hyprland colors
HYPRLAND_TEMPLATE = """# Pywal colors for Hyprland
# Source this file in your hyprland.conf: source = ~/.cache/wal/colors-hyprland.conf

$wallpaper = {wallpaper}

$background = rgb({background.strip})
$foreground = rgb({foreground.strip})

$color0 = rgb({color0.strip})
$color1 = rgb({color1.strip})
$color2 = rgb({color2.strip})
$color3 = rgb({color3.strip})
$color4 = rgb({color4.strip})
$color5 = rgb({color5.strip})
$color6 = rgb({color6.strip})
$color7 = rgb({color7.strip})
$color8 = rgb({color8.strip})
$color9 = rgb({color9.strip})
$color10 = rgb({color10.strip})
$color11 = rgb({color11.strip})
$color12 = rgb({color12.strip})
$color13 = rgb({color13.strip})
$color14 = rgb({color14.strip})
$color15 = rgb({color15.strip})
"""

# Default Hyprland colors (used before first pywal run)
HYPRLAND_DEFAULT = """# Pywal colors for Hyprland (default - will be replaced on first wallpaper generation)
# Source this file in your hyprland.conf: source = ~/.cache/wal/colors-hyprland.conf

$wallpaper =

$background = rgb(1a1b26)
$foreground = rgb(c0caf5)

$color0 = rgb(1a1b26)
$color1 = rgb(f7768e)
$color2 = rgb(9ece6a)
$color3 = rgb(e0af68)
$color4 = rgb(7aa2f7)
$color5 = rgb(bb9af7)
$color6 = rgb(7dcfff)
$color7 = rgb(c0caf5)
$color8 = rgb(414868)
$color9 = rgb(f7768e)
$color10 = rgb(9ece6a)
$color11 = rgb(e0af68)
$color12 = rgb(7aa2f7)
$color13 = rgb(bb9af7)
$color14 = rgb(7dcfff)
$color15 = rgb(c0caf5)
"""

# Pywal template for Waybar CSS (just color definitions)
WAYBAR_TEMPLATE = """/* Pywal colors for Waybar
 * Import this file in your waybar style.css: @import "../../.cache/wal/colors-waybar.css";
 */

@define-color background {background};
@define-color foreground {foreground};

@define-color color0 {color0};
@define-color color1 {color1};
@define-color color2 {color2};
@define-color color3 {color3};
@define-color color4 {color4};
@define-color color5 {color5};
@define-color color6 {color6};
@define-color color7 {color7};
@define-color color8 {color8};
@define-color color9 {color9};
@define-color color10 {color10};
@define-color color11 {color11};
@define-color color12 {color12};
@define-color color13 {color13};
@define-color color14 {color14};
@define-color color15 {color15};
"""

# Default Waybar colors (used before first pywal run)
WAYBAR_DEFAULT = """/* Pywal colors for Waybar (default - will be replaced on first wallpaper generation)
 * Import this file in your waybar style.css: @import "../../.cache/wal/colors-waybar.css";
 */

@define-color background #1a1b26;
@define-color foreground #c0caf5;

@define-color color0 #1a1b26;
@define-color color1 #f7768e;
@define-color color2 #9ece6a;
@define-color color3 #e0af68;
@define-color color4 #7aa2f7;
@define-color color5 #bb9af7;
@define-color color6 #7dcfff;
@define-color color7 #c0caf5;
@define-color color8 #414868;
@define-color color9 #f7768e;
@define-color color10 #9ece6a;
@define-color color11 #e0af68;
@define-color color12 #7aa2f7;
@define-color color13 #bb9af7;
@define-color color14 #7dcfff;
@define-color color15 #c0caf5;
"""


def setup_pywal_templates() -> bool:
    """Set up pywal templates for Hyprland and Waybar.

    Creates template files in ~/.config/wal/templates/ that pywal
    will use to generate color configs. Also creates initial cache
    files with default colors so Hyprland doesn't error on startup.

    Returns:
        True if templates were created/updated successfully
    """
    templates_dir = Path.home() / ".config" / "wal" / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = Path.home() / ".cache" / "wal"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Write Hyprland template
        hyprland_template = templates_dir / "colors-hyprland.conf"
        hyprland_template.write_text(HYPRLAND_TEMPLATE)

        # Write Waybar template
        waybar_template = templates_dir / "colors-waybar.css"
        waybar_template.write_text(WAYBAR_TEMPLATE)

        # Create initial cache files with defaults if they don't exist
        hyprland_cache = cache_dir / "colors-hyprland.conf"
        if not hyprland_cache.exists():
            hyprland_cache.write_text(HYPRLAND_DEFAULT)

        waybar_cache = cache_dir / "colors-waybar.css"
        if not waybar_cache.exists():
            waybar_cache.write_text(WAYBAR_DEFAULT)

        return True
    except OSError:
        return False


def init_color_files() -> None:
    """Initialize color files for first-time setup.

    Call this to create the cache files so Hyprland/Waybar can source them
    before the first wallpaper is generated.
    """
    setup_pywal_templates()


class WallpaperError(Exception):
    """Error setting wallpaper."""


def check_pywal_available() -> bool:
    """Check if pywal is installed."""
    result = subprocess.run(
        ["which", "wal"],
        capture_output=True,
    )
    return result.returncode == 0


def apply_pywal_colors(image_path: str | Path) -> dict:
    """Generate and apply colors using pywal for terminal, Hyprland, and Waybar.

    Args:
        image_path: Path to the image file

    Returns:
        Dict with status of each operation (pywal, hyprland_reload, waybar_reload)
    """
    results = {"pywal": False, "hyprland_reload": False, "waybar_reload": False}

    if not check_pywal_available():
        return results

    image_path = Path(image_path)
    if not image_path.exists():
        return results

    # Ensure pywal templates are set up for Hyprland and Waybar
    setup_pywal_templates()

    # -n flag: skip setting wallpaper (we handle that with awww)
    # -i flag: specify image file
    cmd = ["wal", "-n", "-i", str(image_path)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    results["pywal"] = result.returncode == 0

    if results["pywal"]:
        # Reload Hyprland to pick up new border colors
        hypr_reload = subprocess.run(
            ["hyprctl", "reload"],
            capture_output=True,
        )
        results["hyprland_reload"] = hypr_reload.returncode == 0

        # Reload Waybar to pick up new colors
        # First try SIGUSR2 (reload config), fall back to restart
        waybar_reload = subprocess.run(
            ["pkill", "-SIGUSR2", "waybar"],
            capture_output=True,
        )
        results["waybar_reload"] = waybar_reload.returncode == 0

    return results


def _find_nvim_sockets() -> list[Path]:
    """Find Unix sockets for running nvim instances in $XDG_RUNTIME_DIR."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        runtime_dir = f"/run/user/{os.getuid()}"

    runtime_path = Path(runtime_dir)
    if not runtime_path.is_dir():
        return []

    sockets: list[Path] = []
    for candidate in runtime_path.glob("nvim.*"):
        try:
            if stat.S_ISSOCK(candidate.stat().st_mode):
                sockets.append(candidate)
        except OSError:
            continue
    return sockets


def reload_nvim_colors(reload_cmd: str = DEFAULT_NVIM_RELOAD_CMD) -> dict:
    """Send a color-reload command to every running nvim instance.

    Args:
        reload_cmd: Ex-command to execute in each nvim. Leading ':' is stripped.
            The command is sent as a <Cmd> keymap so it works in any mode
            without disturbing the user's current buffer state.

    Returns:
        Dict with keys "nvim" (bool: any instance reached) and "instances"
        (int: number of instances that accepted the command).
    """
    sockets = _find_nvim_sockets()
    if not sockets:
        return {"nvim": False, "instances": 0}

    keys = f"<Cmd>{reload_cmd.lstrip(':').strip()}<CR>"

    successes = 0
    for sock in sockets:
        try:
            result = subprocess.run(
                ["nvim", "--server", str(sock), "--remote-send", keys],
                capture_output=True,
                timeout=3,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0:
            successes += 1

    return {"nvim": successes > 0, "instances": successes}


def update_hyprlock_background(image_path: str | Path) -> bool:
    """Update hyprlock configuration with the new wallpaper.

    Args:
        image_path: Path to the image file

    Returns:
        True if successful, False otherwise
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return False

    hyprlock_conf = Path.home() / ".config" / "hypr" / "hyprlock.conf"

    if not hyprlock_conf.exists():
        return False

    content = hyprlock_conf.read_text()
    lines = content.split("\n")
    new_lines = []
    in_background_block = False
    brace_depth = 0
    path_replaced = False

    for line in lines:
        stripped = line.strip()

        # Detect entering background block
        if stripped.startswith("background") and "{" in stripped:
            in_background_block = True
            brace_depth = 1
            new_lines.append(line)
            continue

        if in_background_block:
            # Track brace depth
            brace_depth += line.count("{") - line.count("}")

            # Skip all existing path lines, we'll add one new one
            if stripped.startswith("path"):
                if not path_replaced:
                    # Add the new path (preserve indentation from original)
                    indent = len(line) - len(line.lstrip())
                    if indent == 0:
                        indent = 4  # default indent
                    new_lines.append(" " * indent + f"path = {image_path}")
                    path_replaced = True
                # Skip this line (don't add duplicate paths)
                continue

            # Check if we're exiting the background block
            if brace_depth == 0:
                # If we never found a path line, add one before closing brace
                if not path_replaced:
                    new_lines.append(f"    path = {image_path}")
                    path_replaced = True
                in_background_block = False

            new_lines.append(line)
        else:
            new_lines.append(line)

    # If no background block existed, create one
    if not path_replaced:
        new_lines.append("")
        new_lines.append("background {")
        new_lines.append("    monitor =")
        new_lines.append(f"    path = {image_path}")
        new_lines.append("}")

    hyprlock_conf.write_text("\n".join(new_lines))
    return True


def check_awww_daemon() -> bool:
    """Check if awww-daemon is running."""
    result = subprocess.run(
        ["pgrep", "-x", "awww-daemon"],
        capture_output=True,
    )
    return result.returncode == 0


def set_wallpaper(
    image_path: str | Path,
    transition_type: str = "grow",
    transition_duration: float = 1.5,
    transition_fps: int = 60,
    apply_pywal: bool = True,
    update_hyprlock: bool = True,
    apply_nvim: bool = True,
    nvim_reload_cmd: str = DEFAULT_NVIM_RELOAD_CMD,
) -> dict:
    """Set the wallpaper using awww with optional pywal and hyprlock integration.

    Args:
        image_path: Path to the image file
        transition_type: Transition effect (grow, wipe, fade, etc.)
        transition_duration: Duration of transition in seconds
        transition_fps: Frames per second for transition
        apply_pywal: Whether to generate colors with pywal (terminal, Hyprland, Waybar)
        update_hyprlock: Whether to update hyprlock lock screen background
        apply_nvim: Whether to reload running nvim instances after pywal
        nvim_reload_cmd: Ex-command sent to each running nvim instance

    Returns:
        Dict with status of each operation
    """
    image_path = Path(image_path)
    results = {
        "wallpaper": False,
        "pywal": False,
        "hyprland_colors": False,
        "waybar_colors": False,
        "hyprlock": False,
        "nvim": False,
        "nvim_instances": 0,
    }

    if not image_path.exists():
        raise WallpaperError(f"Image not found: {image_path}")

    if not check_awww_daemon():
        raise WallpaperError(
            "awww-daemon is not running. Start it with: awww-daemon &"
        )

    cmd = [
        "awww",
        "img",
        str(image_path),
        "--transition-type",
        transition_type,
        "--transition-duration",
        str(transition_duration),
        "--transition-fps",
        str(transition_fps),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise WallpaperError(f"Failed to set wallpaper: {result.stderr}")

    results["wallpaper"] = True

    # Apply pywal colors if enabled (terminal, Hyprland borders, Waybar)
    if apply_pywal:
        pywal_results = apply_pywal_colors(image_path)
        results["pywal"] = pywal_results.get("pywal", False)
        results["hyprland_colors"] = pywal_results.get("hyprland_reload", False)
        results["waybar_colors"] = pywal_results.get("waybar_reload", False)

        # Reload running nvim instances so they pick up the new palette
        if apply_nvim and results["pywal"]:
            nvim_results = reload_nvim_colors(nvim_reload_cmd)
            results["nvim"] = nvim_results.get("nvim", False)
            results["nvim_instances"] = nvim_results.get("instances", 0)

    # Update hyprlock background if enabled
    if update_hyprlock:
        results["hyprlock"] = update_hyprlock_background(image_path)

    return results


def get_current_wallpaper() -> Optional[str]:
    """Get the current wallpaper path from awww."""
    if not check_awww_daemon():
        return None

    result = subprocess.run(
        ["awww", "query"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return None

    # Parse output: format is "output: image_path"
    for line in result.stdout.strip().split("\n"):
        if ":" in line:
            parts = line.split(":", 1)
            if len(parts) >= 2:
                # Extract the image path from "image:" part
                image_info = parts[1].strip()
                if image_info.startswith("/"):
                    return image_info.split()[0]

    return None


def set_latest_generated(
    apply_pywal: bool = True,
    update_hyprlock: bool = True,
    apply_nvim: bool = True,
    nvim_reload_cmd: str = DEFAULT_NVIM_RELOAD_CMD,
) -> Optional[str]:
    """Set the most recently generated wallpaper. Returns the path if successful."""
    generation = db.get_latest_generation()
    if generation and Path(generation.image_path).exists():
        set_wallpaper(
            generation.image_path,
            apply_pywal=apply_pywal,
            update_hyprlock=update_hyprlock,
            apply_nvim=apply_nvim,
            nvim_reload_cmd=nvim_reload_cmd,
        )
        return generation.image_path
    return None


def generate_hyprland_keybinds(wallpaper_cmd: str = "wallpaper-ai") -> str:
    """Generate Hyprland keybind configuration snippet.

    Args:
        wallpaper_cmd: The command to launch the wallpaper selector

    Returns:
        Hyprland configuration snippet for keybinds
    """
    return f"""# Wallpaper AI Keybinds
# Add these to your ~/.config/hypr/hyprland.conf

# Launch wallpaper selector
bind = $mainMod, W, exec, {wallpaper_cmd}

# Rate current wallpaper (1-5 stars)
bind = $mainMod, F1, exec, {wallpaper_cmd} --rate 1
bind = $mainMod, F2, exec, {wallpaper_cmd} --rate 2
bind = $mainMod, F3, exec, {wallpaper_cmd} --rate 3
bind = $mainMod, F4, exec, {wallpaper_cmd} --rate 4
bind = $mainMod, F5, exec, {wallpaper_cmd} --rate 5

# Generate random wallpaper using learned preferences
bind = $mainMod SHIFT, W, exec, {wallpaper_cmd} --random
"""
