from pathlib import Path
from tinyfacts.check_words import split_words, check_words

class FolderGenStats:

    word_count: int
    unique_word_count: int
    file_count: int
    invalid_file_count: int
        
    def __init__(self, folder: Path) -> None:
        """Compute generation stats for the given folder

        Args:
            folder (Path): The folder containing generated explanations.
        """
        gen_folders = folder.glob("*_created")
        # For each folder, find all valid text files and generate stats
        self.word_count = 0
        self.file_count = 0
        self.invalid_file_count = 0
        word_set = set()
        
        for fold in gen_folders:
            text_files = list(fold.glob("*.txt"))
            for text_file in text_files:
                words = split_words(text_file.read_text())
                invalid_words = check_words(words)
                if invalid_words:
                    self.invalid_file_count += 1
                    continue  # Skip files with invalid words
                self.file_count += 1
                self.word_count += len(words)
                word_set.update(words)
        self.unique_word_count = len(word_set)