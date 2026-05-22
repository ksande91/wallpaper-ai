"""Philips Hue light integration via local bridge REST API."""

import json
import ssl
import urllib.request
import urllib.error
from pathlib import Path


class HueError(Exception):
    """Error communicating with Hue bridge."""


def hex_to_xy(hex_color: str, brightness: int = 254) -> tuple[float, float, int]:
    """Convert hex color to CIE xy colorspace + brightness.

    Uses gamma correction and Wide RGB D65 conversion matrix.

    Args:
        hex_color: Hex color string (with or without #)
        brightness: Brightness value 1-254 (default: 254, full brightness)

    Returns:
        Tuple of (x, y, brightness) where brightness is 1-254
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    # Apply gamma correction
    r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
    g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
    b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92

    # Wide RGB D65 conversion matrix
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039

    total = x + y + z
    if total == 0:
        cx, cy = 0.3127, 0.3290  # D65 white point
    else:
        cx = x / total
        cy = y / total

    bri = max(1, min(254, brightness))

    return (cx, cy, bri)


def _hue_request(
    bridge_ip: str,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    api_key: str | None = None,
) -> dict | list:
    """Make an HTTP request to the Hue bridge.

    Args:
        bridge_ip: Bridge IP address
        path: API path (e.g. "/api" or "/api/<key>/lights")
        method: HTTP method
        body: Request body (will be JSON-encoded)
        api_key: API key (unused here, included in path)

    Returns:
        Parsed JSON response

    Raises:
        HueError: On connection or API errors
    """
    url = f"https://{bridge_ip}{path}"

    # Bridge uses self-signed cert, disable verification
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise HueError(f"Failed to connect to bridge at {bridge_ip}: {e}") from e
    except json.JSONDecodeError as e:
        raise HueError(f"Invalid response from bridge: {e}") from e
    except TimeoutError as e:
        raise HueError(f"Bridge request timed out: {e}") from e


def discover_bridges() -> list[dict]:
    """Discover Hue bridges on the network.

    Returns:
        List of dicts with 'id' and 'internalipaddress' keys
    """
    ctx = ssl.create_default_context()
    req = urllib.request.Request("https://discovery.meethue.com/")
    try:
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        raise HueError(f"Bridge discovery failed: {e}") from e


def register_api_key(bridge_ip: str, device_type: str = "wallpaper-ai") -> str:
    """Register a new API key with the bridge.

    The bridge link button must be pressed within 30 seconds before calling this.

    Args:
        bridge_ip: Bridge IP address
        device_type: Device type identifier

    Returns:
        API key string

    Raises:
        HueError: If registration fails (e.g. button not pressed)
    """
    result = _hue_request(bridge_ip, "/api", method="POST", body={"devicetype": device_type})

    if isinstance(result, list) and result:
        entry = result[0]
        if "success" in entry:
            return entry["success"]["username"]
        if "error" in entry:
            raise HueError(f"Registration failed: {entry['error']['description']}")

    raise HueError(f"Unexpected registration response: {result}")


def list_lights(bridge_ip: str, api_key: str) -> dict:
    """List all lights on the bridge.

    Args:
        bridge_ip: Bridge IP address
        api_key: API key

    Returns:
        Dict mapping light IDs to light info dicts
    """
    return _hue_request(bridge_ip, f"/api/{api_key}/lights")


def set_light_color(
    bridge_ip: str,
    api_key: str,
    light_id: str,
    hex_color: str,
    transition_time: int = 10,
    brightness: int = 254,
) -> bool:
    """Set a light to a specific color.

    Args:
        bridge_ip: Bridge IP address
        api_key: API key
        light_id: Light ID string
        hex_color: Hex color string
        transition_time: Transition time in 100ms units (10 = 1 second)
        brightness: Brightness 1-254 (default: 254, full brightness)

    Returns:
        True if successful
    """
    x, y, bri = hex_to_xy(hex_color, brightness)
    body = {
        "on": True,
        "xy": [x, y],
        "bri": bri,
        "transitiontime": transition_time,
    }
    result = _hue_request(
        bridge_ip, f"/api/{api_key}/lights/{light_id}/state", method="PUT", body=body
    )

    if isinstance(result, list):
        return any("success" in entry for entry in result)
    return False


def apply_hue_colors(
    bridge_ip: str,
    api_key: str,
    light_color_map: dict[str, int],
    transition_time: int = 10,
    brightness: int = 254,
) -> bool:
    """Apply pywal palette colors to configured Hue lights.

    Reads colors from ~/.cache/wal/colors and maps them to lights based
    on the light_color_map configuration.

    Never raises - returns False on any failure.

    Args:
        bridge_ip: Bridge IP address
        api_key: API key
        light_color_map: Dict mapping light IDs to palette color indices (0-15)
        transition_time: Transition time in 100ms units
        brightness: Brightness 1-254 (default: 254, full brightness)

    Returns:
        True if at least one light was updated successfully
    """
    if not bridge_ip or not api_key or not light_color_map:
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
    for light_id, color_index in light_color_map.items():
        if color_index < 0 or color_index >= len(colors):
            continue

        hex_color = colors[color_index].strip()
        if not hex_color:
            continue

        try:
            if set_light_color(bridge_ip, api_key, light_id, hex_color, transition_time, brightness):
                any_success = True
        except HueError:
            continue

    return any_success
