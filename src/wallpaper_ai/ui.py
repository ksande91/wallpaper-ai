"""Terminal UI using Textual."""

import asyncio

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    OptionList,
    SelectionList,
    Static,
)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from . import db, generator, image, preferences, wallpaper
from .config import get_theming_config, get_generation_config


class SelectionScreen(Screen):
    """Main selection screen for generating wallpapers."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("h", "show_history", "History"),
        Binding("g", "generate", "Generate"),
    ]

    CSS = """
    SelectionScreen {
        layout: vertical;
    }

    #main-container {
        height: 100%;
        padding: 1 2;
    }

    .selection-row {
        height: auto;
        margin-bottom: 1;
    }

    .selection-label {
        width: 100%;
        text-style: bold;
        margin-bottom: 0;
    }

    OptionList {
        height: 8;
        border: solid $primary;
    }

    SelectionList {
        height: 8;
        border: solid $primary;
    }

    #custom-input {
        margin-top: 1;
    }

    #custom-input-field {
        width: 100%;
    }

    #button-row {
        margin-top: 2;
        height: auto;
    }

    #button-row Button {
        margin-right: 2;
    }

    #stats-panel {
        dock: right;
        width: 30;
        padding: 1;
        border-left: solid $primary;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.selected_category = generator.CATEGORIES[0]
        self.selected_style = generator.STYLES[0]
        self.selected_moods: list[str] = [generator.MOODS[0]]

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="main-container"):
            with Horizontal():
                with Vertical(id="selection-panel"):
                    # Category selection
                    with Vertical(classes="selection-row"):
                        yield Label("Category", classes="selection-label")
                        yield OptionList(
                            *[Option(cat, id=cat) for cat in generator.CATEGORIES],
                            id="category-list",
                        )

                    # Style selection
                    with Vertical(classes="selection-row"):
                        yield Label("Style", classes="selection-label")
                        yield OptionList(
                            *[Option(style, id=style) for style in generator.STYLES],
                            id="style-list",
                        )

                    # Mood selection (multi-select)
                    with Vertical(classes="selection-row"):
                        yield Label("Mood (multi-select)", classes="selection-label")
                        yield SelectionList[str](
                            *[
                                Selection(mood, mood, i == 0)
                                for i, mood in enumerate(generator.MOODS)
                            ],
                            id="mood-list",
                        )

                    # Custom input
                    with Vertical(id="custom-input"):
                        yield Label("Custom Input (optional)", classes="selection-label")
                        yield Input(
                            placeholder="Add custom elements to influence generation...",
                            id="custom-input-field",
                        )

                    # Buttons
                    with Horizontal(id="button-row"):
                        yield Button("Generate", variant="primary", id="generate-btn")
                        yield Button("History", variant="default", id="history-btn")
                        yield Button("Random", variant="success", id="random-btn")

                # Stats panel
                with Vertical(id="stats-panel"):
                    yield Label("Statistics", classes="selection-label")
                    yield Static(id="stats-display")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the database and update stats."""
        db.init_db()
        self._update_stats()

        # Set initial selections
        cat_list = self.query_one("#category-list", OptionList)
        cat_list.highlighted = 0

        style_list = self.query_one("#style-list", OptionList)
        style_list.highlighted = 0

    def _update_stats(self) -> None:
        """Update the stats display."""
        stats = preferences.get_stats()
        stats_display = self.query_one("#stats-display", Static)

        lines = [
            f"Total: {stats['total_generations']}",
            f"Rated: {stats['rated_count']}",
        ]

        if stats["average_rating"]:
            lines.append(f"Avg Rating: {stats['average_rating']:.1f}/5")

        if stats["has_preferences"]:
            lines.append(f"Prefs Age: {stats['preference_age_days']}d")

        if stats["top_categories"]:
            lines.append(f"\nTop: {', '.join(stats['top_categories'][:2])}")

        stats_display.update("\n".join(lines))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle option selection for category and style."""
        list_id = event.option_list.id
        if list_id == "category-list":
            self.selected_category = str(event.option.id)
        elif list_id == "style-list":
            self.selected_style = str(event.option.id)

    def on_selection_list_selection_toggled(self, event: SelectionList.SelectionToggled) -> None:
        """Handle mood multi-selection toggle."""
        mood_list = self.query_one("#mood-list", SelectionList)
        self.selected_moods = list(mood_list.selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "generate-btn":
            self.action_generate()
        elif event.button.id == "history-btn":
            self.action_show_history()
        elif event.button.id == "random-btn":
            self.action_random_generate()

    def action_generate(self) -> None:
        """Generate a new wallpaper."""
        if not self.selected_moods:
            self.notify("Select at least one mood", severity="warning")
            return

        custom_input = self.query_one("#custom-input-field", Input).value or None
        mood = ", ".join(self.selected_moods)

        self.app.push_screen(
            GeneratingScreen(
                category=self.selected_category,
                style=self.selected_style,
                mood=mood,
                custom_input=custom_input,
            )
        )

    def action_random_generate(self) -> None:
        """Generate a random wallpaper based on preferences."""
        self.app.push_screen(GeneratingScreen(random_mode=True))

    def action_show_history(self) -> None:
        """Show the history screen."""
        self.app.push_screen(HistoryScreen())


class GeneratingScreen(Screen):
    """Screen shown while generating a wallpaper."""

    CSS = """
    GeneratingScreen {
        align: center middle;
    }

    #generating-container {
        width: 70;
        height: auto;
        padding: 2 4;
        border: double $primary;
        background: $surface;
    }

    #status-label {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }

    #details-label {
        text-align: center;
        color: $text-muted;
    }

    #spinner-container {
        align: center middle;
        height: 5;
        margin: 1 0;
    }

    #spinner-art {
        text-align: center;
        color: $primary;
    }

    #step-indicator {
        text-align: center;
        margin-top: 1;
        color: $text-muted;
    }

    #progress-bar {
        margin: 1 2;
        height: 1;
    }

    .progress-track {
        background: $surface-darken-1;
    }

    .progress-fill {
        background: $primary;
    }

    LoadingIndicator {
        margin: 1;
    }
    """

    SPINNER_FRAMES = [
        "    ◐    ",
        "    ◓    ",
        "    ◑    ",
        "    ◒    ",
    ]

    SPINNER_ART = [
        [
            "  ╭───────╮  ",
            "  │ ◠ ◡ ◠ │  ",
            "  ╰───────╯  ",
        ],
        [
            "  ╭───────╮  ",
            "  │ ◡ ◠ ◡ │  ",
            "  ╰───────╯  ",
        ],
        [
            "  ╭───────╮  ",
            "  │ ◠ ◠ ◡ │  ",
            "  ╰───────╯  ",
        ],
        [
            "  ╭───────╮  ",
            "  │ ◡ ◡ ◠ │  ",
            "  ╰───────╯  ",
        ],
    ]

    def __init__(
        self,
        category: str = "",
        style: str = "",
        mood: str = "",
        custom_input: str | None = None,
        random_mode: bool = False,
    ) -> None:
        super().__init__()
        self.category = category
        self.style = style
        self.mood = mood
        self.custom_input = custom_input
        self.random_mode = random_mode
        self.spinner_frame = 0
        self.current_step = 1
        self.total_steps = 3

    def compose(self) -> ComposeResult:
        with Container(id="generating-container"):
            yield Label("Generating wallpaper...", id="status-label")
            with Container(id="spinner-container"):
                yield Static("\n".join(self.SPINNER_ART[0]), id="spinner-art")
            yield Label(f"Step {self.current_step} of {self.total_steps}", id="step-indicator")
            if self.random_mode:
                yield Label("Using learned preferences", id="details-label")
            else:
                yield Label(
                    f"{self.category} / {self.style} / {self.mood}",
                    id="details-label",
                )

    def on_mount(self) -> None:
        """Start the generation process."""
        self.set_interval(0.15, self._animate_spinner)
        self.run_worker(self._generate(), exclusive=True)

    def _animate_spinner(self) -> None:
        """Animate the spinner art."""
        self.spinner_frame = (self.spinner_frame + 1) % len(self.SPINNER_ART)
        spinner = self.query_one("#spinner-art", Static)
        spinner.update("\n".join(self.SPINNER_ART[self.spinner_frame]))

    def _update_step(self, step: int, message: str) -> None:
        """Update the current step and status message."""
        self.current_step = step
        status = self.query_one("#status-label", Label)
        step_indicator = self.query_one("#step-indicator", Label)
        status.update(message)
        step_indicator.update(f"Step {step} of {self.total_steps}")

    async def _generate(self) -> None:
        """Generate the wallpaper."""
        try:
            # Step 1: Generate prompt
            self._update_step(1, "✨ Crafting prompt...")
            await asyncio.sleep(0.1)  # Allow UI to update

            if self.random_mode:
                prompt, category, style, mood = await asyncio.to_thread(
                    generator.generate_random_prompt
                )
                self.category = category
                self.style = style
                self.mood = mood
                details = self.query_one("#details-label", Label)
                details.update(f"{category} / {style} / {mood}")
            else:
                prompt = await asyncio.to_thread(
                    generator.generate_prompt,
                    category=self.category,
                    style=self.style,
                    mood=self.mood,
                    custom_input=self.custom_input,
                    include_history=False,
                )

            # Step 2: Generate image
            self._update_step(2, "🎨 Generating image...")
            await asyncio.sleep(0.1)  # Allow UI to update

            gen_config = get_generation_config()
            image_path, generation_id = await asyncio.to_thread(
                image.generate_image,
                prompt=prompt,
                category=self.category,
                style=self.style,
                mood=self.mood,
                custom_input=self.custom_input,
                model=gen_config["model"],
                width=gen_config["width"],
                height=gen_config["height"],
                provider=gen_config["provider"],
            )

            # Step 3: Set wallpaper
            self._update_step(3, "🖼️ Setting wallpaper...")
            await asyncio.sleep(0.1)  # Allow UI to update

            try:
                enable_pywal, enable_hyprlock = get_theming_config()
                results = await asyncio.to_thread(
                    wallpaper.set_wallpaper,
                    image_path,
                    apply_pywal=enable_pywal,
                    update_hyprlock=enable_hyprlock,
                )
                if results.get("pywal"):
                    self.notify("Terminal colors updated")
                if results.get("hyprlock"):
                    self.notify("Lock screen updated")
            except wallpaper.WallpaperError as e:
                # Don't fail completely if swww isn't running
                self.notify(str(e), severity="warning")

            # Show success
            self.app.pop_screen()
            self.app.push_screen(
                SuccessScreen(
                    image_path=image_path,
                    generation_id=generation_id,
                    prompt=prompt,
                )
            )

        except Exception as e:
            self.app.pop_screen()
            self.notify(f"Error: {e}", severity="error")


class SuccessScreen(Screen):
    """Screen shown after successful generation."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("1", "rate_1", "Rate 1"),
        Binding("2", "rate_2", "Rate 2"),
        Binding("3", "rate_3", "Rate 3"),
        Binding("4", "rate_4", "Rate 4"),
        Binding("5", "rate_5", "Rate 5"),
    ]

    CSS = """
    SuccessScreen {
        align: center middle;
    }

    #success-container {
        width: 80;
        height: auto;
        padding: 2;
        border: solid $success;
        background: $surface;
    }

    #success-title {
        text-align: center;
        text-style: bold;
        color: $success;
        margin-bottom: 1;
    }

    #path-label {
        margin-bottom: 1;
    }

    #prompt-label {
        margin-bottom: 2;
        color: $text-muted;
    }

    #rating-row {
        height: auto;
        margin-top: 1;
    }

    #rating-row Button {
        margin-right: 1;
        min-width: 5;
    }
    """

    def __init__(self, image_path: str, generation_id: int, prompt: str) -> None:
        super().__init__()
        self.image_path = image_path
        self.generation_id = generation_id
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Container(id="success-container"):
            yield Label("Wallpaper Generated!", id="success-title")
            yield Label(f"Path: {self.image_path}", id="path-label")
            yield Label(f"Prompt: {self.prompt[:200]}...", id="prompt-label")

            yield Label("Rate this wallpaper:")
            with Horizontal(id="rating-row"):
                yield Button("1 ★", id="rate-1")
                yield Button("2 ★", id="rate-2")
                yield Button("3 ★", id="rate-3")
                yield Button("4 ★", id="rate-4")
                yield Button("5 ★", id="rate-5")

            yield Button("Back to Selection", variant="primary", id="back-btn")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id and event.button.id.startswith("rate-"):
            rating = int(event.button.id.split("-")[1])
            self._rate(rating)
        elif event.button.id == "back-btn":
            self.action_back()

    def _rate(self, rating: int) -> None:
        """Rate the wallpaper."""
        preferences.rate_wallpaper(self.generation_id, rating)
        self.notify(f"Rated {rating}/5 stars!")

    def action_rate_1(self) -> None:
        self._rate(1)

    def action_rate_2(self) -> None:
        self._rate(2)

    def action_rate_3(self) -> None:
        self._rate(3)

    def action_rate_4(self) -> None:
        self._rate(4)

    def action_rate_5(self) -> None:
        self._rate(5)

    def action_back(self) -> None:
        """Go back to selection screen."""
        self.app.pop_screen()


class HistoryScreen(Screen):
    """Screen for viewing wallpaper history."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("s", "set_selected", "Set Wallpaper"),
        Binding("1", "rate_1", "Rate 1"),
        Binding("2", "rate_2", "Rate 2"),
        Binding("3", "rate_3", "Rate 3"),
        Binding("4", "rate_4", "Rate 4"),
        Binding("5", "rate_5", "Rate 5"),
    ]

    CSS = """
    HistoryScreen {
        layout: horizontal;
    }

    #history-list-container {
        width: 50%;
        height: 100%;
        border-right: solid $primary;
    }

    ListView {
        height: 100%;
    }

    ListItem {
        padding: 1;
    }

    #details-panel {
        width: 50%;
        padding: 1 2;
    }

    #details-title {
        text-style: bold;
        margin-bottom: 1;
    }

    .detail-row {
        margin-bottom: 0;
    }

    #prompt-text {
        margin-top: 1;
        color: $text-muted;
    }

    #action-buttons {
        margin-top: 2;
    }

    #action-buttons Button {
        margin-right: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.generations: list[db.Generation] = []
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal():
            with VerticalScroll(id="history-list-container"):
                yield ListView(id="history-list")

            with Vertical(id="details-panel"):
                yield Label("Select a wallpaper", id="details-title")
                yield Static(id="details-content")

                with Horizontal(id="action-buttons"):
                    yield Button("Set Wallpaper", variant="primary", id="set-btn")
                    yield Button("Rate", variant="default", id="rate-btn")

        yield Footer()

    def on_mount(self) -> None:
        """Load history data."""
        self.generations = db.get_recent_generations(limit=50)
        history_list = self.query_one("#history-list", ListView)

        for gen in self.generations:
            stars = "★" * (gen.rating or 0) + "☆" * (5 - (gen.rating or 0))
            rating_str = f"[{stars}]" if gen.rating else "[unrated]"
            label = f"{gen.category} / {gen.style} - {rating_str}"
            history_list.append(ListItem(Label(label), id=f"gen-{gen.id}"))

        if self.generations:
            self._update_details(0)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list selection."""
        if event.item.id:
            gen_id = int(event.item.id.split("-")[1])
            for i, gen in enumerate(self.generations):
                if gen.id == gen_id:
                    self.selected_index = i
                    self._update_details(i)
                    break

    def _update_details(self, index: int) -> None:
        """Update the details panel."""
        if not self.generations:
            return

        gen = self.generations[index]
        title = self.query_one("#details-title", Label)
        content = self.query_one("#details-content", Static)

        title.update(f"{gen.category} / {gen.style} / {gen.mood}")

        stars = "★" * (gen.rating or 0) + "☆" * (5 - (gen.rating or 0))
        rating_str = stars if gen.rating else "Not rated"

        details = f"""Rating: {rating_str}
Created: {gen.created_at.strftime('%Y-%m-%d %H:%M')}
Path: {gen.image_path}

Prompt:
{gen.prompt[:300]}{'...' if len(gen.prompt) > 300 else ''}"""

        content.update(details)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "set-btn":
            self.action_set_selected()
        elif event.button.id == "rate-btn":
            # Show rating options
            self.notify("Press 1-5 to rate")

    def action_set_selected(self) -> None:
        """Set the selected wallpaper."""
        if not self.generations:
            return

        gen = self.generations[self.selected_index]
        try:
            enable_pywal, enable_hyprlock = get_theming_config()
            results = wallpaper.set_wallpaper(
                gen.image_path,
                apply_pywal=enable_pywal,
                update_hyprlock=enable_hyprlock,
            )
            self.notify(f"Wallpaper set: {gen.image_path}")
            if results.get("pywal"):
                self.notify("Terminal colors updated")
            if results.get("hyprlock"):
                self.notify("Lock screen updated")
        except wallpaper.WallpaperError as e:
            self.notify(str(e), severity="error")

    def _rate_selected(self, rating: int) -> None:
        """Rate the selected wallpaper."""
        if not self.generations:
            return

        gen = self.generations[self.selected_index]
        if gen.id:
            preferences.rate_wallpaper(gen.id, rating)
            self.notify(f"Rated {rating}/5 stars!")
            # Refresh the list
            self.generations = db.get_recent_generations(limit=50)
            self._update_details(self.selected_index)

    def action_rate_1(self) -> None:
        self._rate_selected(1)

    def action_rate_2(self) -> None:
        self._rate_selected(2)

    def action_rate_3(self) -> None:
        self._rate_selected(3)

    def action_rate_4(self) -> None:
        self._rate_selected(4)

    def action_rate_5(self) -> None:
        self._rate_selected(5)


class WallpaperApp(App):
    """Main application."""

    TITLE = "Wallpaper AI"
    CSS = """
    Screen {
        background: $background;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("k", "show_keybinds", "Keybinds"),
    ]

    def on_mount(self) -> None:
        """Initialize the app."""
        db.init_db()
        self.push_screen(SelectionScreen())

    def action_show_keybinds(self) -> None:
        """Show Hyprland keybind configuration."""
        keybinds = wallpaper.generate_hyprland_keybinds()
        self.notify(f"Keybinds copied to clipboard:\n{keybinds[:100]}...")
        # In a real implementation, we'd copy to clipboard


def run_app() -> None:
    """Run the Textual application."""
    app = WallpaperApp()
    app.run()
