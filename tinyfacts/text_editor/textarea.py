from textual.widgets import TextArea
from textual.document._document import Document
from textual.document._wrapped_document import WrappedDocument
from textual.document._document_navigator import DocumentNavigator
from tinyfacts.check_words import WordFormsDictionary, find_word_matches

class SimpleTextArea(TextArea):
    """TextArea with simple word-based highlighting instead of tree-sitter.
    
    Highlights words as allowed (green) or not allowed (red) based on a word set.
    """
    
    def __init__(self, **kwargs):
        self._dict = WordFormsDictionary()
        super().__init__(**kwargs)
    
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
            
            for word, start_col, end_col in find_word_matches(line_text):
                
                # Determine if word is allowed
                is_allowed = word.lower() in self._dict.allowed_words
                highlight_name = "allowed_word" if is_allowed else "disallowed_word"
                
                highlight = (start_col, end_col, highlight_name)
                highlights[line_index].append(highlight)