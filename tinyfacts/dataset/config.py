"""Where the dataset lives, and what is known about each folder of texts."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

#: The file that holds all of this, looked for next to the repository root.
CONFIG_NAME = "dataset.yaml"

#: Set this to send the dataset somewhere other than the repo in the config file.
REPO_ENV_VAR = "TINYFACTS_HF_REPO"

#: Any of these is used as the Hugging Face token when none is given.
TOKEN_ENV_VARS = ("TINYFACTS_HF_TOKEN", "HF_TOKEN", "HUGGINGFACE_TOKEN")

#: Folders of generated text are named like this.
FOLDER_SUFFIX = "_created"


class ConfigError(Exception):
    """The config file is missing or does not make sense."""


class HubConfig(BaseModel):
    """The Hugging Face dataset repository the rows are kept in."""

    repo_id: str = Field("stur86/tinyfacts", description="Owner and name of the dataset repo.")
    private: bool = Field(False, description="Make the repo private when it is first made.")
    data_dir: str = Field("data", description="Folder inside the repo that holds the chunks.")
    chunk_prefix: str = Field("tinyfacts", description="Name each chunk file starts with.")
    license: str | None = Field("mit", description="License to put in the dataset card.")


class StoreConfig(BaseModel):
    """The working copy of the dataset on this machine."""

    path: Path = Field(Path(".dataset"), description="Folder to keep the working copy in.")
    chunk_size: int = Field(2000, gt=0, description="How many rows go in one chunk file.")


class SourceConfig(BaseModel):
    """What is known about one folder of generated text.

    Only what cannot be worked out from the folder name needs to be here. A
    folder that is not named in the config file still works: its source name and
    its model are taken from the folder name.
    """

    folder: str | None = Field(None, description="Folder name, if not '<source>_created'.")
    model: str | None = Field(None, description="Model that wrote these texts.")
    provider: str | None = Field(None, description="Provider the model was asked through.")
    instruction_template: str | None = Field(
        None,
        description="Question every text in the folder answers, with '{title}' "
        "standing for the title of the text.",
    )
    instructions_file: str | None = Field(
        None,
        description="File in the folder with one question per line, used when the "
        "texts are named after the line they answer.",
    )
    instructions_name_pattern: str | None = Field(
        None,
        description="Regular expression with one group, run on the file name, that "
        "gives the line of 'instructions_file' the text answers (counting from 0).",
    )
    instruction_model: str | None = Field(
        None, description="Model that wrote the questions, when they were not written by hand."
    )
    title_template: str | None = Field(
        None,
        description="Title to give texts whose file name says nothing useful, with "
        "'{name}' and '{instruction}' standing for those.",
    )
    tags: list[str] = Field(default_factory=list, description="Labels put on every row.")
    skip: bool = Field(False, description="Leave this folder out of the dataset.")
    known: bool = Field(
        False,
        exclude=True,
        description="True when the folder is named in the config file, so that a "
        "field left empty there means empty, not unknown.",
    )

    def folder_name(self, source: str) -> str:
        return self.folder or f"{source}{FOLDER_SUFFIX}"

    def instruction_for(self, name: str, title: str, questions: list[str]) -> str | None:
        """The question a text answers, as far as the config can tell.

        Args:
            name: File name of the text, with no suffix.
            title: Title of the text.
            questions: Lines of `instructions_file`, or an empty list.
        """
        if self.instructions_name_pattern and questions:
            match = re.search(self.instructions_name_pattern, name)
            if match:
                try:
                    line = int(match.group(1))
                except (IndexError, ValueError):
                    line = -1
                if 0 <= line < len(questions) and questions[line].strip():
                    return questions[line].strip()
        if self.instruction_template:
            return self.instruction_template.format(title=title, name=name)
        return None

    def title_for(self, name: str, title: str, instruction: str | None) -> str:
        """The title to give a text, when the folder says how to make one."""
        if not self.title_template:
            return title
        try:
            made = self.title_template.format(
                name=name, title=title, instruction=(instruction or "").strip()
            )
        except (IndexError, KeyError):
            return title
        return made.strip() or title


class DatasetConfig(BaseModel):
    """Everything the dataset commands need to know."""

    hub: HubConfig = Field(default_factory=HubConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)

    #: Folder the config file was found in. Paths are taken from here.
    root: Path = Field(Path.cwd(), exclude=True)

    def model_post_init(self, _context: Any) -> None:
        # A folder named in the config file is 'known', so a model left out
        # there is taken to mean there is no model, not that nobody said.
        for source in self.sources.values():
            source.known = True

    @classmethod
    def load(cls, path: Path | None = None, root: Path | None = None) -> "DatasetConfig":
        """Read the config file, falling back to the built-in defaults.

        Args:
            path: The config file. When it is not given, `dataset.yaml` is looked
                for in `root` and then in the folders above it.
            root: Where to start looking, and what paths are relative to.
        """
        start = (root or Path.cwd()).resolve()
        if path is None:
            path = _find_config(start)
        data: dict[str, Any] = {}
        if path is not None:
            path = Path(path)
            if not path.exists():
                raise ConfigError(f"No config file at {path}.")
            try:
                data = yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError as exc:
                raise ConfigError(f"Could not read {path}: {exc}") from exc
            if not isinstance(data, dict):
                raise ConfigError(f"{path} should hold a mapping.")
            start = path.parent
        config = cls(**data, root=start)
        env_repo = os.environ.get(REPO_ENV_VAR)
        if env_repo:
            config.hub.repo_id = env_repo
        return config

    @property
    def store_path(self) -> Path:
        path = self.store.path
        return path if path.is_absolute() else self.root / path

    def source_for_folder(self, folder: Path) -> tuple[str, SourceConfig]:
        """The source name and config for a folder of generated text."""
        name = folder.name
        for source, config in self.sources.items():
            if config.folder_name(source) == name:
                return source, config
        if name.endswith(FOLDER_SUFFIX):
            name = name[: -len(FOLDER_SUFFIX)]
        return name, SourceConfig()

    def generation_folders(self, root: Path | None = None) -> list[Path]:
        """Every folder of generated text, in name order."""
        base = root or self.root
        folders = {path for path in base.glob(f"*{FOLDER_SUFFIX}") if path.is_dir()}
        for source, config in self.sources.items():
            if config.folder:
                candidate = base / config.folder
                if candidate.is_dir():
                    folders.add(candidate)
        return sorted(folders)


def _find_config(start: Path) -> Path | None:
    for folder in [start, *start.parents]:
        candidate = folder / CONFIG_NAME
        if candidate.exists():
            return candidate
    return None


def resolve_token(token: str | None = None) -> str | None:
    """The Hugging Face token to use: the one given, or one from the environment."""
    if token:
        return token
    for name in TOKEN_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None
