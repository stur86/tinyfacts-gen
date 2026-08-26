"""Where the dataset lives."""

import os
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

    repo_id: str = Field("Stur86/tinyfacts", description="Owner and name of the dataset repo.")
    private: bool = Field(False, description="Make the repo private when it is first made.")
    data_dir: str = Field("data", description="Folder inside the repo that holds the chunks.")
    chunk_prefix: str = Field("tinyfacts", description="Name each chunk file starts with.")
    license: str | None = Field(
        "cc-by-4.0",
        description="License of the dataset, for the card. Not the license of this "
        "software, which is its own thing.",
    )


class StoreConfig(BaseModel):
    """The working copy of the dataset on this machine."""

    path: Path = Field(Path(".dataset"), description="Folder to keep the working copy in.")
    chunk_size: int = Field(2000, gt=0, description="How many rows go in one chunk file.")


class DatasetConfig(BaseModel):
    """Everything the dataset commands need to know.

    Only where the dataset goes. What is known about a text — its title, the
    question it answers, the model that wrote it — is kept in the text's own
    YAML block, so nothing here has to be taught about each run of generations.
    """

    hub: HubConfig = Field(default_factory=HubConfig)
    store: StoreConfig = Field(default_factory=StoreConfig)

    #: Folder the config file was found in. Paths are taken from here.
    root: Path = Field(Path.cwd(), exclude=True)

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

    def source_for_folder(self, folder: Path) -> str:
        """The source name a folder of generated text gives its rows."""
        name = folder.name
        if name.endswith(FOLDER_SUFFIX):
            name = name[: -len(FOLDER_SUFFIX)]
        return name

    def generation_folders(self, root: Path | None = None) -> list[Path]:
        """Every folder of generated text, in name order."""
        base = root or self.root
        return sorted(path for path in base.glob(f"*{FOLDER_SUFFIX}") if path.is_dir())


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
