from pathlib import Path
from tinyfacts.check_words import split_words, check_words_with_context

class FolderGenStats:

    word_count: int
    unique_word_count: int
    file_count: int
    invalid_files: list[Path]
        
    def __init__(self, folder: Path) -> None:
        """Compute generation stats for the given folder

        Args:
            folder (Path): The folder containing generated explanations.
        """
        gen_folders = folder.glob("*_created")
        # For each folder, find all valid text files and generate stats
        self.word_count = 0
        self.file_count = 0
        self.invalid_files = []
        word_set = set()
        
        for fold in gen_folders:
            text_files = list(fold.glob("*.txt"))
            for text_file in text_files:
                text = text_file.read_text()
                words = split_words(text)
                if check_words_with_context(text).invalid_words:
                    self.invalid_files.append(text_file)
                    continue  # Skip files with invalid words
                self.file_count += 1
                self.word_count += len(words)
                word_set.update(words)
        self.unique_word_count = len(word_set)
    
    @property
    def invalid_file_count(self) -> int:
        """Return the number of invalid files found during stats computation."""
        return len(self.invalid_files)