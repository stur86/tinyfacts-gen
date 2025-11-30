from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Label
from textual.containers import Vertical
from textual.binding import Binding
from rich.style import Style
from .textarea import SimpleTextArea
from .modals import ConfirmSave, LoadFile

class SimpleTextEditor(App):
    """A text editor app using only the allowed words from Thing Explainer."""
    
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+l", "load", "Load"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    
    CSS_PATH = Path(__file__).parent / "simple_editor.tcss"
    
    def __init__(self, output_path: Path, **kwargs):
        super().__init__(**kwargs)
        self.output_path = output_path
                
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Vertical():
            yield Label("File Title")
            yield Input(id="title")
            yield Label("Write your text below (green=allowed, red=not allowed):")
            self._text_area = SimpleTextArea(id="editor")
            yield self._text_area
        yield Footer()
    
    def on_mount(self) -> None:
        """Set up the theme for SimpleTextArea highlighting."""
        from textual._text_area_theme import TextAreaTheme
        
        # Create a custom theme with allowed/disallowed word styles
        custom_theme = TextAreaTheme(
            name="simple",
            base_style=Style(color="white"),
            gutter_style=Style(color="bright_black"),
            cursor_style=Style(color="white", bgcolor="blue"),
            cursor_line_style=Style(bgcolor="#2d2d2d"),
            selection_style=Style(bgcolor="#264f78"),
            syntax_styles={
                "allowed_word": Style(color="green"),
                "disallowed_word": Style(color="red", bold=True),
            },
        )
        
        self._text_area.register_theme(custom_theme)
        self._text_area.theme = "simple"
    
    async def action_save(self) -> None:
        """Save the current document with the given title."""
        title_input = self.query_one("#title", Input)
        title = title_input.value.strip()
        
        if not title:
            self.notify("Please enter a file title.", severity="error")
            return
        
        # Create output directory if it doesn't exist
        self.output_path.mkdir(parents=True, exist_ok=True)
        
        # Create output path
        output_file = self.output_path / f"{title}.txt"
        
        def save_file_confirmed(overwrite: bool | None) -> None:
            if not overwrite:
                self.notify("Save cancelled.", severity="warning")
                return
            # Save the file
            try:
                output_file.write_text(self._text_area.text)
                self.notify(f"Saved to {output_file}", severity="information")
            except Exception as e:
                self.notify(f"Error saving file: {e}", severity="error")
        
        if output_file.exists():
            # Ask for confirmation to overwrite
            confirm_screen = ConfirmSave(output_file.name)
            self.push_screen(confirm_screen, callback=save_file_confirmed)
        else:
            save_file_confirmed(True)
                
    
    def action_load(self) -> None:
        """Load a file using the file browser."""
        load_screen = LoadFile(self.output_path)
        self.push_screen(load_screen, callback=self._on_file_selected)
    
    def _on_file_selected(self, file_path: str | None) -> None:
        """Handle file selection from the load dialog."""
        if file_path is None:
            self.notify("Load cancelled.", severity="warning")
            return
        
        try:
            file_path_obj = Path(file_path)
            if file_path_obj.is_file():
                content = file_path_obj.read_text()
                title_input = self.query_one("#title", Input)
                title_input.value = file_path_obj.stem
                self._text_area.text = content
                self.notify(f"Loaded {file_path_obj.name}", severity="information")
            else:
                self.notify(f"Not a file: {file_path}", severity="error")
        except Exception as e:
            self.notify(f"Error loading file: {e}", severity="error")
    
    async def action_quit(self) -> None:
        """Quit the application."""
        self.exit()
