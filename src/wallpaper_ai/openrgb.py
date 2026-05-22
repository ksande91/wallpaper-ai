"""OpenRGB integration for PC RGB hardware via the openrgb CLI."""

import subprocess
from pathlib import Path


def list_devices() -> list[dict]:
    """List available OpenRGB devices by parsing `openrgb --list-devices`.

    Returns:
        List of dicts with 'id', 'name', and 'type' keys.
        Empty list if openrgb is not available or fails.
    """
    try:
        result = subprocess.run(
            ["openrgb", "--list-devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    devices = []
    current_id = None
    current_name = None
    current_type = None

    for line in result.stdout.splitlines():
        # Device headers are unindented: "0: Kingston Fury DDR5 DRAM"
        # Properties are indented:       "  Type:           DRAM"
        if line and not line[0].isspace() and ":" in line:
            # Save previous device
            if current_id is not None and current_name is not None:
                devices.append({
                    "id": current_id,
                    "name": current_name,
                    "type": current_type or "Unknown",
                })

            id_str, name = line.split(":", 1)
            if id_str.strip().isdigit():
                current_id = id_str.strip()
                current_name = name.strip()
                current_type = None
            else:
                # Not a device line (e.g. stderr noise), skip
                current_id = None
                current_name = None

        elif line.strip().startswith("Type:"):
            current_type = line.strip()[len("Type:"):].strip()

    # Don't forget the last device
    if current_id is not None and current_name is not None:
        devices.append({
            "id": current_id,
            "name": current_name,
            "type": current_type or "Unknown",
        })

    return devices


def apply_openrgb_colors(device_color_map: dict[str, int]) -> bool:
    """Apply pywal palette colors to configured OpenRGB devices.

    Reads colors from ~/.cache/wal/colors and sets each device's color
    via `openrgb --device <id> --mode Direct --color <hex>`.

    Never raises - returns False on any failure.

    Args:
        device_color_map: Dict mapping device IDs to palette color indices (0-15)

    Returns:
        True if at least one device was updated successfully
    """
    if not device_color_map:
        return False

    # Read pywal colors
    colors_file = Path.home() / ".cache" / "wal" / "colors"
    try:
        colors = colors_file.read_text().strip().splitlines()
    except OSError:
        return False

    if not colors:
        return False

    any_success = False
    for device_id, color_index in device_color_map.items():
        if color_index < 0 or color_index >= len(colors):
            continue

        hex_color = colors[color_index].strip().lstrip("#")
        if not hex_color:
            continue

        try:
            result = subprocess.run(
                ["openrgb", "--device", str(device_id), "--mode", "Direct", "--color", hex_color],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                any_success = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return any_success
