"""The dataset of generated texts: how it is kept, filtered and synced.

The rows live in .jsonl chunks under a working copy folder, and that folder is
mirrored to a dataset repository on the Hugging Face Hub. Nothing here is kept
in git, so the repository does not grow with every generation.
"""

from .config import ConfigError, DatasetConfig, HubConfig, StoreConfig, resolve_token
from .documents import (
    GeneratedDocument,
    find_document,
    iter_documents,
    join_frontmatter,
    read_document,
    split_frontmatter,
    write_document,
)
from .filters import FilterError, RecordFilter
from .ingest import IngestReport, document_to_record, iter_records
from .records import DatasetRecord, make_id, utc_now
from .store import AddResult, DatasetStore, StoreError, read_jsonl_records

__all__ = [
    "AddResult",
    "ConfigError",
    "DatasetConfig",
    "DatasetRecord",
    "DatasetStore",
    "FilterError",
    "GeneratedDocument",
    "HubConfig",
    "IngestReport",
    "RecordFilter",
    "StoreConfig",
    "StoreError",
    "document_to_record",
    "find_document",
    "iter_documents",
    "iter_records",
    "join_frontmatter",
    "make_id",
    "read_document",
    "read_jsonl_records",
    "resolve_token",
    "split_frontmatter",
    "utc_now",
    "write_document",
]
