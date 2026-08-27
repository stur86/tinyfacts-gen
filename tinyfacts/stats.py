from pathlib import Path

from tinyfacts.check_words import split_words
from tinyfacts.word_forms import WordFormsDictionary
from tinyfacts.dataset.documents import iter_documents, read_document


class FolderGenStats:
    word_count: int
    unique_word_count: int
    file_count: int
    invalid_files: list[Path]

    def __init__(self, folder: Path) -> None:
        """Compute generation stats for the given folder

        Both `.txt` files and `.md` files are counted. A `.md` file that starts
        with a YAML block is counted on its text alone, so what the file says
        about itself does not go into the word count.

        Args:
            folder (Path): The folder containing generated explanations.
        """
        gen_folders = folder.glob("*_created")
        # For each folder, find all valid text files and generate stats
        self.word_count = 0
        self.file_count = 0
        self.invalid_files = []
        word_set: set[str] = set()

        # Counting needs the words anyway, so they are split once and the check
        # is made on them: which words are wrong is enough, where they are is not.
        allowed_words = WordFormsDictionary().allowed_words
        for fold in gen_folders:
            for text_file in iter_documents(fold):
                words = split_words(read_document(text_file).text)
                if not set(words) <= allowed_words:
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
