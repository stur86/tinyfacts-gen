from pathlib import Path
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, DirectoryTree
from textual.app import ComposeResult

class ConfirmSave(ModalScreen[bool]):
    """Modal screen for confirming file overwrites."""

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

    def __init__(self, output_path: Path) -> None:
        super().__init__()
        self.output_path = output_path
        self.selected_file: str | None = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Select a file to load:"),
            DirectoryTree(self.output_path, id="file_tree"),
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