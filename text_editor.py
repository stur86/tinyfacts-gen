import json
import re
from pathlib import Path
from rich.style import Style
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, TextArea, Label, DirectoryTree
from textual.containers import Vertical, Horizontal
from textual.document._document import Document
from textual.document._wrapped_document import WrappedDocument
from textual.document._document_navigator import DocumentNavigator
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button

_WORDS_PATH = Path(__file__).parent / "tinyfacts" / "thing-explainer" / "word-forms.json"
_OUTPUT_PATH = Path(__file__).parent / "manually_created"

class ConfirmSave(ModalScreen[bool]):

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Confirm Save"),
    ]

    def __init__(self, filename: str) -> None:
        super().__init__()
        self.filename = filename
        
    def compose(self) -> ComposeResult:
        yield Vertical(Label(f"The file '{self.filename}' already exists. Overwrite?"),
            Horizontal(
                Button("Yes", id="yes", variant="success"),
                Button("No", id="no", variant="error")
            ), id="confirm_save"
        )
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
    
    def action_cancel(self) -> None:
        """Cancel the save operation."""
        self.dismiss(False)
    
    def action_confirm(self) -> None:
        """Confirm the save operation."""
        self.dismiss(True)


class LoadFile(ModalScreen[str | None]):
    """Modal screen for loading files using a DirectoryTree."""

    def __init__(self) -> None:
        super().__init__()
        self.selected_file: str | None = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Select a file to load:"),
            DirectoryTree(_OUTPUT_PATH, id="file_tree"),
            id="load_file"
        )

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        """Handle file selection."""
        self.dismiss(str(event.path))

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        """Handle directory selection - do nothing."""
        pass

    def action_cancel(self) -> None:
        """Cancel the load operation."""
        self.dismiss(None)


class SimpleTextArea(TextArea):
    """TextArea with simple word-based highlighting instead of tree-sitter.
    
    Highlights words as allowed (green) or not allowed (red) based on a word set.
    """
    
    def __init__(self, allowed_words: set[str] | None = None, **kwargs):
        self.allowed_words = allowed_words or set()
        super().__init__(**kwargs)
        # Override the word pattern AFTER super() to find whole words, not word boundaries
        self._word_pattern = re.compile(r'\b\w+\b')
    
    def _set_document(self, text: str, language: str | None) -> None:
        """Skip tree-sitter setup, always use plain Document."""
        # Don't set up tree-sitter - always use plain text
        self._highlight_query = None
        document = Document(text)
        self.document = document
        self.wrapped_document = WrappedDocument(document, tab_width=self.indent_width)
        self.navigator = DocumentNavigator(self.wrapped_document)
        self._build_highlight_map()
        self.move_cursor((0, 0))
        self._rewrap_and_refresh_virtual_size()
    
    def _build_highlight_map(self) -> None:
        """Build highlights based on allowed/disallowed words."""
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()
        
        # Iterate through each line and find words
        for line_index in range(self.document.line_count):
            line_text = self.document.get_line(line_index)
            
            for match in self._word_pattern.finditer(line_text):
                word = match.group()
                start_col = match.start()
                end_col = match.end()
                
                # Determine if word is allowed
                is_allowed = word.lower() in self.allowed_words
                highlight_name = "allowed_word" if is_allowed else "disallowed_word"
                
                highlight = (start_col, end_col, highlight_name)
                highlights[line_index].append(highlight)


class SimpleTextEditor(App):
    """A text editor app using only the allowed words from Thing Explainer."""
    
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+l", "load", "Load"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #editor {
        border: solid $primary;
    }
    
    ConfirmSave {
        align: center middle;
    }
    
    ConfirmSave Screen {
        background: $surface 50%;
    }
    
    #confirm_save {
        width: 50;
        height: 11;
        border: heavy $warning;
        background: $panel;
        layout: vertical;
    }
    
    #confirm_save Label {
        width: 100%;
        text-align: center;
        height: auto;
    }
    
    #confirm_save Horizontal {
        width: 100%;
        height: auto;
        align-horizontal: center;
    }
    
    #confirm_save Button {
        margin: 0 1;
    }
    
    LoadFile {
        align: center middle;
    }
    
    LoadFile Screen {
        background: $surface 50%;
    }
    
    #load_file {
        width: 80;
        height: 20;
        border: heavy $accent;
        background: $panel;
        layout: vertical;
    }
    
    #load_file Label {
        width: 100%;
        text-align: center;
        height: auto;
    }
    
    #file_tree {
        width: 1fr;
        height: 1fr;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        word_forms: dict[str, dict[str, str]] = json.loads(_WORDS_PATH.read_text())["words"]
        self.allowed_words = set()
        for forms in word_forms.values():
            for form in forms.values():
                self.allowed_words.add(form.lower())
        
    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Vertical():
            yield Label("File Title")
            yield Input(id="title")
            yield Label("Write your text below (green=allowed, red=not allowed):")
            self._text_area = SimpleTextArea(allowed_words=self.allowed_words, id="editor")
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
        _OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        
        # Create output path
        output_file = _OUTPUT_PATH / f"{title}.txt"
        
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
                
    
    def action_load(self) -> None:
        """Load a file using the file browser."""
        load_screen = LoadFile()
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


if __name__ == "__main__":
    app = SimpleTextEditor()
    app.run()
