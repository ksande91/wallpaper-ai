"""CLI entry point for Wallpaper AI."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import db, generator, hue, image, openrgb, preferences, wallpaper, ui
from .config import get_config_path, load_config, get_theming_config, get_generation_config, get_hue_config, get_openrgb_config
from .wallpaper import _resolve_color_map

console = Console()


@click.group(invoke_without_command=True)
@click.option("--random", is_flag=True, help="Generate random wallpaper using learned preferences")
@click.option("--rate", type=int, help="Rate the current wallpaper (1-5)")
@click.option("--keybinds", is_flag=True, help="Print Hyprland keybind configuration")
@click.pass_context
def main(ctx: click.Context, random: bool, rate: Optional[int], keybinds: bool) -> None:
    """AI-powered wallpaper generator for Hyprland.

    Run without arguments to launch the interactive UI.
    """
    # Initialize database
    db.init_db()

    if keybinds:
        console.print(wallpaper.generate_hyprland_keybinds())
        return

    if rate is not None:
        if not 1 <= rate <= 5:
            console.print("[red]Rating must be between 1 and 5[/red]")
            sys.exit(1)

        gen_id = preferences.rate_current_wallpaper(rate)
        if gen_id:
            console.print(f"[green]Rated wallpaper {gen_id} with {rate}/5 stars[/green]")
        else:
            console.print("[yellow]No wallpaper to rate[/yellow]")
        return

    if random:
        _generate_random()
        return

    # If no subcommand, launch the UI
    if ctx.invoked_subcommand is None:
        ui.run_app()


@main.command()
@click.option("--category", "-c", type=click.Choice(generator.CATEGORIES), help="Category")
@click.option("--style", "-s", type=click.Choice(generator.STYLES), help="Style")
@click.option("--mood", "-m", type=click.Choice(generator.MOODS), multiple=True, help="Mood (can specify multiple)")
@click.option("--custom", "-x", type=str, help="Custom input text")
def generate(
    category: Optional[str],
    style: Optional[str],
    mood: tuple[str, ...],
    custom: Optional[str],
) -> None:
    """Generate a wallpaper with specified options."""
    import random as rand

    # Use defaults if not specified
    category = category or rand.choice(generator.CATEGORIES)
    style = style or rand.choice(generator.STYLES)
    mood_str = ", ".join(mood) if mood else rand.choice(generator.MOODS)

    console.print(f"[blue]Generating wallpaper: {category} / {style} / {mood_str}[/blue]")

    try:
        gen_config = get_generation_config()
        with console.status("Generating prompt..."):
            prompt = generator.generate_prompt(
                category=category,
                style=style,
                mood=mood_str,
                custom_input=custom,
                include_history=False,
                image_model=gen_config["model"],
                aspect_ratio=gen_config["aspect_ratio"],
            )

        console.print(f"[dim]Prompt: {prompt[:100]}...[/dim]")
        with console.status("Generating image..."):
            image_path, gen_id = image.generate_image(
                prompt=prompt,
                category=category,
                style=style,
                mood=mood_str,
                custom_input=custom,
                model=gen_config["model"],
                width=gen_config["width"],
                height=gen_config["height"],
                provider=gen_config["provider"],
            )

        console.print(f"[green]Image saved: {image_path}[/green]")

        with console.status("Setting wallpaper..."):
            try:
                theming = get_theming_config()
                results = wallpaper.set_wallpaper(
                    image_path,
                    apply_pywal=theming["enable_pywal"],
                    update_hyprlock=theming["enable_hyprlock"],
                    apply_nvim=theming["enable_nvim"],
                    nvim_reload_cmd=theming["nvim_reload_cmd"],
                    apply_hue=theming["enable_hue"],
                    apply_openrgb=theming["enable_openrgb"],
                )
                console.print("[green]Wallpaper set![/green]")
                if results.get("pywal"):
                    console.print("[dim]Terminal colors updated via pywal[/dim]")
                if results.get("hyprland_colors"):
                    console.print("[dim]Hyprland border colors updated[/dim]")
                if results.get("waybar_colors"):
                    console.print("[dim]Waybar colors updated[/dim]")
                if results.get("nvim"):
                    console.print(f"[dim]Nvim colors reloaded ({results['nvim_instances']} instance(s))[/dim]")
                if results.get("hyprlock"):
                    console.print("[dim]Lock screen updated in hyprlock.conf[/dim]")
                if results.get("hue_lights"):
                    console.print("[dim]Hue lights updated[/dim]")
                if results.get("openrgb"):
                    console.print("[dim]OpenRGB devices updated[/dim]")
            except wallpaper.WallpaperError as e:
                console.print(f"[yellow]Warning: {e}[/yellow]")

        console.print(f"\n[dim]Generation ID: {gen_id}. Rate with: wallpaper-ai --rate <1-5>[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def _generate_random() -> None:
    """Generate a random wallpaper using learned preferences."""
    console.print("[blue]Generating random wallpaper using learned preferences...[/blue]")

    try:
        gen_config = get_generation_config()
        with console.status("Analyzing preferences..."):
            prompt, category, style, mood = generator.generate_random_prompt(
                image_model=gen_config["model"],
                aspect_ratio=gen_config["aspect_ratio"],
            )

        console.print(f"[blue]Selected: {category} / {style} / {mood}[/blue]")
        console.print(f"[dim]Prompt: {prompt[:100]}...[/dim]")
        with console.status("Generating image..."):
            image_path, gen_id = image.generate_image(
                prompt=prompt,
                category=category,
                style=style,
                mood=mood,
                model=gen_config["model"],
                width=gen_config["width"],
                height=gen_config["height"],
                provider=gen_config["provider"],
            )

        console.print(f"[green]Image saved: {image_path}[/green]")

        with console.status("Setting wallpaper..."):
            try:
                theming = get_theming_config()
                results = wallpaper.set_wallpaper(
                    image_path,
                    apply_pywal=theming["enable_pywal"],
                    update_hyprlock=theming["enable_hyprlock"],
                    apply_nvim=theming["enable_nvim"],
                    nvim_reload_cmd=theming["nvim_reload_cmd"],
                    apply_hue=theming["enable_hue"],
                    apply_openrgb=theming["enable_openrgb"],
                )
                console.print("[green]Wallpaper set![/green]")
                if results.get("pywal"):
                    console.print("[dim]Terminal colors updated via pywal[/dim]")
                if results.get("hyprland_colors"):
                    console.print("[dim]Hyprland border colors updated[/dim]")
                if results.get("waybar_colors"):
                    console.print("[dim]Waybar colors updated[/dim]")
                if results.get("nvim"):
                    console.print(f"[dim]Nvim colors reloaded ({results['nvim_instances']} instance(s))[/dim]")
                if results.get("hyprlock"):
                    console.print("[dim]Lock screen updated in hyprlock.conf[/dim]")
                if results.get("hue_lights"):
                    console.print("[dim]Hue lights updated[/dim]")
                if results.get("openrgb"):
                    console.print("[dim]OpenRGB devices updated[/dim]")
            except wallpaper.WallpaperError as e:
                console.print(f"[yellow]Warning: {e}[/yellow]")

        console.print(f"\n[dim]Generation ID: {gen_id}. Rate with: wallpaper-ai --rate <1-5>[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
def history() -> None:
    """Show recent wallpaper history."""
    generations = db.get_recent_generations(limit=20)

    if not generations:
        console.print("[yellow]No wallpapers generated yet[/yellow]")
        return

    table = Table(title="Recent Wallpapers")
    table.add_column("ID", style="cyan")
    table.add_column("Category")
    table.add_column("Style")
    table.add_column("Mood")
    table.add_column("Rating")
    table.add_column("Date")

    for gen in generations:
        stars = "★" * (gen.rating or 0) + "☆" * (5 - (gen.rating or 0)) if gen.rating else "-"
        table.add_row(
            str(gen.id),
            gen.category,
            gen.style,
            gen.mood,
            stars,
            gen.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@main.command()
def stats() -> None:
    """Show statistics and preferences."""
    stats_data = preferences.get_stats()

    panel_content = f"""Total Generations: {stats_data['total_generations']}
Rated: {stats_data['rated_count']}
Average Rating: {stats_data['average_rating'] or 'N/A'}

Top Categories: {', '.join(stats_data['top_categories']) or 'N/A'}
Top Styles: {', '.join(stats_data['top_styles']) or 'N/A'}
Top Moods: {', '.join(stats_data['top_moods']) or 'N/A'}

Preferences: {'Yes' if stats_data['has_preferences'] else 'No'}"""

    if stats_data['preference_age_days'] is not None:
        panel_content += f" (updated {stats_data['preference_age_days']} days ago)"

    console.print(Panel(panel_content, title="Wallpaper AI Statistics"))

    # Show preference summary if available
    pref_summary = preferences.get_preference_summary()
    if pref_summary:
        console.print(Panel(pref_summary, title="Learned Preferences"))


@main.command()
@click.argument("generation_id", type=int)
def set(generation_id: int) -> None:
    """Set a wallpaper from history by ID."""
    gen = db.get_generation(generation_id)

    if not gen:
        console.print(f"[red]Generation {generation_id} not found[/red]")
        sys.exit(1)

    if not Path(gen.image_path).exists():
        console.print(f"[red]Image file not found: {gen.image_path}[/red]")
        sys.exit(1)

    try:
        theming = get_theming_config()
        results = wallpaper.set_wallpaper(
            gen.image_path,
            apply_pywal=theming["enable_pywal"],
            update_hyprlock=theming["enable_hyprlock"],
            apply_nvim=theming["enable_nvim"],
            nvim_reload_cmd=theming["nvim_reload_cmd"],
            apply_hue=theming["enable_hue"],
            apply_openrgb=theming["enable_openrgb"],
        )
        console.print(f"[green]Wallpaper set: {gen.image_path}[/green]")
        if results.get("pywal"):
            console.print("[dim]Terminal colors updated via pywal[/dim]")
        if results.get("nvim"):
            console.print(f"[dim]Nvim colors reloaded ({results['nvim_instances']} instance(s))[/dim]")
        if results.get("hyprlock"):
            console.print("[dim]Lock screen updated in hyprlock.conf[/dim]")
        if results.get("hue_lights"):
            console.print("[dim]Hue lights updated[/dim]")
        if results.get("openrgb"):
            console.print("[dim]OpenRGB devices updated[/dim]")
    except wallpaper.WallpaperError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
def regenerate_prefs() -> None:
    """Manually regenerate preference summary from ratings."""
    try:
        with console.status("Analyzing ratings..."):
            summary = preferences.regenerate_preferences()

        console.print("[green]Preferences regenerated![/green]")
        console.print(Panel(summary, title="New Preference Summary"))

    except preferences.PreferenceError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
def init() -> None:
    """Initialize configuration and database."""
    # Create config directory
    config_dir = Path.home() / ".config" / "wallpaper-ai"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create default config if it doesn't exist
    config_path = config_dir / "config.toml"
    if not config_path.exists():
        default_config = """# Wallpaper AI Configuration

[generation]
# FAL model to use: sdxl (default, good style control), sdxl-lightning (fast), flux-schnell, flux-dev, flux-pro
model = "sdxl"

# Image dimensions (16:9 recommended)
width = 1920
height = 1080

[wallpaper]
# Transition type: grow, wipe, fade, left, right, top, bottom
transition_type = "grow"
transition_duration = 1.5
transition_fps = 60

[theming]
# Enable pywal integration to generate terminal colors from wallpapers
# Requires pywal to be installed (python-pywal package)
enable_pywal = true

# Enable hyprlock background updates
# Automatically sets the lock screen wallpaper in ~/.config/hypr/hyprlock.conf
enable_hyprlock = true

# Reload running nvim instances after pywal generates new colors.
# Sends nvim_reload_cmd via `nvim --remote-send` to every socket in
# $XDG_RUNTIME_DIR/nvim.*. Set to false to leave running nvim alone.
enable_nvim = true

# Ex-command sent to each running nvim instance. The default sources
# pywal's auto-generated vim colorscheme. For lushwal.nvim users:
#   nvim_reload_cmd = "lua require('lushwal').reload_theme()"
# For AlphaTechnolog/pywal.nvim users:
#   nvim_reload_cmd = "colorscheme pywal"
nvim_reload_cmd = "silent! source $HOME/.cache/wal/colors-wal.vim"

# Enable Philips Hue light integration
# Run 'wallpaper-ai hue-setup' to configure
# enable_hue = false

# [hue]
# bridge_ip = ""
# api_key = ""
# transition_time = 10  # In 100ms units (10 = 1 second)

# [hue.lights]
# light_id = palette_color_index (0-15)
# "1" = 1   # Light strip -> color1 (primary accent)
# "3" = 4   # Bulb -> color4 (contrasting accent)

# Enable OpenRGB integration for PC RGB hardware
# Run 'wallpaper-ai openrgb-test' to list devices and test
# enable_openrgb = false

# [openrgb.devices]
# device_id = palette_color_index (0-15)
# "0" = 1   # RAM -> color1 (primary accent)
# "1" = 2   # Motherboard -> color2

[learning]
# Number of ratings before regenerating preferences
ratings_threshold = 10
"""
        config_path.write_text(default_config)
        console.print(f"[green]Created config: {config_path}[/green]")
    else:
        console.print(f"[yellow]Config already exists: {config_path}[/yellow]")

    # Initialize database
    db.init_db()
    console.print(f"[green]Database initialized: {db.get_db_path()}[/green]")

    # Create images directory
    images_dir = db.get_images_dir()
    console.print(f"[green]Images directory: {images_dir}[/green]")

    # Initialize pywal templates and color files
    wallpaper.init_color_files()
    console.print("[green]Pywal templates and color files initialized[/green]")
    console.print("[dim]  Templates: ~/.config/wal/templates/[/dim]")
    console.print("[dim]  Colors: ~/.cache/wal/colors-hyprland.conf, colors-waybar.css[/dim]")

    # Print setup instructions
    console.print("\n[blue]Add these to your configs:[/blue]")
    console.print("\n[yellow]~/.config/hypr/hyprland.conf:[/yellow]")
    console.print("  source = ~/.cache/wal/colors-hyprland.conf")
    console.print("\n[yellow]Then use these variables for borders:[/yellow]")
    console.print("  general {")
    console.print("      col.active_border = $color1 $color2 45deg")
    console.print("      col.inactive_border = $color0")
    console.print("  }")
    console.print("\n[yellow]~/.config/waybar/style.css:[/yellow]")
    console.print('  @import "../../.cache/wal/colors-waybar.css";')
    console.print("\n[yellow]Then use @background, @foreground, @color0-15 in your CSS[/yellow]")

    # Print keybinds
    console.print("\n[blue]Add these keybinds to your Hyprland config:[/blue]")
    console.print(wallpaper.generate_hyprland_keybinds())


@main.command(name="hue-setup")
def hue_setup() -> None:
    """Set up Philips Hue bridge integration.

    Discovers bridges, registers an API key (press bridge link button first),
    and lists available lights.
    """
    # Step 1: Discover bridges
    console.print("[blue]Discovering Hue bridges...[/blue]")
    try:
        bridges = hue.discover_bridges()
    except hue.HueError as e:
        console.print(f"[red]Discovery failed: {e}[/red]")
        console.print("[dim]You can manually specify bridge_ip in config.toml[/dim]")
        return

    if not bridges:
        console.print("[yellow]No bridges found on network[/yellow]")
        console.print("[dim]You can manually specify bridge_ip in config.toml[/dim]")
        return

    bridge_ip = bridges[0].get("internalipaddress", "")
    console.print(f"[green]Found bridge: {bridge_ip}[/green]")

    if len(bridges) > 1:
        for b in bridges:
            console.print(f"  [dim]{b.get('id', '?')}: {b.get('internalipaddress', '?')}[/dim]")
        console.print(f"[dim]Using first bridge. Set bridge_ip in config.toml to override.[/dim]")

    # Step 2: Register API key
    console.print("\n[yellow]Press the link button on your Hue bridge, then press Enter...[/yellow]")
    input()

    try:
        api_key = hue.register_api_key(bridge_ip)
        console.print(f"[green]API key registered: {api_key}[/green]")
    except hue.HueError as e:
        console.print(f"[red]Registration failed: {e}[/red]")
        console.print("[dim]Make sure you pressed the link button within 30 seconds[/dim]")
        return

    # Step 3: List lights
    try:
        lights = hue.list_lights(bridge_ip, api_key)
    except hue.HueError as e:
        console.print(f"[red]Failed to list lights: {e}[/red]")
        lights = {}

    if lights:
        table = Table(title="Available Lights")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("State")

        for light_id, info in lights.items():
            name = info.get("name", "?")
            light_type = info.get("type", "?")
            state = "on" if info.get("state", {}).get("on") else "off"
            table.add_row(light_id, name, light_type, state)

        console.print(table)

    # Print config snippet
    console.print("\n[blue]Add this to your ~/.config/wallpaper-ai/config.toml:[/blue]")
    config_snippet = f"""
[theming]
enable_hue = true

[hue]
bridge_ip = "{bridge_ip}"
api_key = "{api_key}"
transition_time = 10  # In 100ms units (10 = 1 second)

[hue.lights]
# light_id = palette_color_index (0-15)
# Colors 1-6 are vibrant accents extracted from the wallpaper"""

    for light_id in lights:
        name = lights[light_id].get("name", "?")
        config_snippet += f'\n# "{light_id}" = 1  # {name} -> color1 (primary accent)'

    console.print(config_snippet)


@main.command(name="hue-test")
def hue_test() -> None:
    """Test Philips Hue bridge connection and optionally apply current colors."""
    hue_config = get_hue_config()

    if not hue_config["bridge_ip"] or not hue_config["api_key"]:
        console.print("[red]Hue not configured. Run 'wallpaper-ai hue-setup' first.[/red]")
        return

    bridge_ip = hue_config["bridge_ip"]
    api_key = hue_config["api_key"]

    # List current light states
    console.print(f"[blue]Connecting to bridge at {bridge_ip}...[/blue]")
    try:
        lights = hue.list_lights(bridge_ip, api_key)
    except hue.HueError as e:
        console.print(f"[red]Connection failed: {e}[/red]")
        return

    table = Table(title="Light States")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("On")
    table.add_column("Brightness")
    table.add_column("Configured")

    configured_lights = hue_config["lights"]
    for light_id, info in lights.items():
        name = info.get("name", "?")
        state = info.get("state", {})
        on = "yes" if state.get("on") else "no"
        bri = str(state.get("bri", "?"))
        configured = f"color{configured_lights[light_id]}" if light_id in configured_lights else "-"
        table.add_row(light_id, name, on, bri, configured)

    console.print(table)

    # Try applying current pywal colors if configured
    if configured_lights:
        console.print("\n[blue]Applying current pywal colors to configured lights...[/blue]")
        success = hue.apply_hue_colors(
            bridge_ip=bridge_ip,
            api_key=api_key,
            light_color_map=configured_lights,
            transition_time=hue_config["transition_time"],
            brightness=hue_config["brightness"],
        )
        if success:
            console.print("[green]Hue lights updated![/green]")
        else:
            console.print("[yellow]Failed to update lights. Check pywal colors exist (~/.cache/wal/colors)[/yellow]")
    else:
        console.print("\n[yellow]No lights configured in [hue.lights] section[/yellow]")


@main.command(name="apply-lights")
def apply_lights() -> None:
    """Apply current pywal colors to configured Hue lights and OpenRGB devices."""
    _, _, enable_hue, enable_openrgb = get_theming_config()
    any_success = False

    if enable_hue:
        hue_config = get_hue_config()
        if hue_config["bridge_ip"] and hue_config["api_key"] and hue_config["lights"]:
            light_map = _resolve_color_map(hue_config["lights"])
            success = hue.apply_hue_colors(
                bridge_ip=hue_config["bridge_ip"],
                api_key=hue_config["api_key"],
                light_color_map=light_map,
                transition_time=hue_config["transition_time"],
                brightness=hue_config["brightness"],
            )
            if success:
                console.print("[green]Hue lights updated[/green]")
                any_success = True
            else:
                console.print("[yellow]Failed to update Hue lights[/yellow]")
        else:
            console.print("[yellow]Hue enabled but not fully configured. Run 'wallpaper-ai hue-setup'.[/yellow]")

    if enable_openrgb:
        device_map = get_openrgb_config()
        if device_map:
            device_map = _resolve_color_map(device_map)
            success = openrgb.apply_openrgb_colors(device_map)
            if success:
                console.print("[green]OpenRGB devices updated[/green]")
                any_success = True
            else:
                console.print("[yellow]Failed to update OpenRGB devices[/yellow]")
        else:
            console.print("[yellow]OpenRGB enabled but no devices configured[/yellow]")

    if not enable_hue and not enable_openrgb:
        console.print("[yellow]No light integrations enabled in config.toml[/yellow]")
    elif not any_success:
        console.print("[dim]Check that ~/.cache/wal/colors exists (run pywal first)[/dim]")


@main.command(name="openrgb-test")
def openrgb_test() -> None:
    """List OpenRGB devices and apply current pywal colors."""
    # List devices
    console.print("[blue]Detecting OpenRGB devices...[/blue]")
    devices = openrgb.list_devices()

    if not devices:
        console.print("[yellow]No devices found. Is OpenRGB running? (openrgb --server)[/yellow]")
        return

    table = Table(title="OpenRGB Devices")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Configured")

    device_map = get_openrgb_config()
    for dev in devices:
        configured = f"color{device_map[dev['id']]}" if dev["id"] in device_map else "-"
        table.add_row(dev["id"], dev["name"], dev["type"], configured)

    console.print(table)

    # Apply current pywal colors if any devices are configured
    if device_map:
        console.print("\n[blue]Applying current pywal colors to configured devices...[/blue]")
        success = openrgb.apply_openrgb_colors(device_map)
        if success:
            console.print("[green]OpenRGB devices updated![/green]")
        else:
            console.print("[yellow]Failed to update devices. Check pywal colors exist (~/.cache/wal/colors)[/yellow]")
    else:
        console.print("\n[yellow]No devices configured in [openrgb.devices] section[/yellow]")
        console.print("[dim]Add this to ~/.config/wallpaper-ai/config.toml:[/dim]")
        console.print()
        config_snippet = "[theming]\nenable_openrgb = true\n\n[openrgb.devices]\n# device_id = palette_color_index (0-15)"
        for dev in devices:
            config_snippet += f'\n# "{dev["id"]}" = 1  # {dev["name"]} -> color1'
        console.print(config_snippet)


if __name__ == "__main__":
    main()
