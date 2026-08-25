"""One row of the dataset."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..check_words import split_words


def utc_now() -> datetime:
    """The time now, with a time zone on it, so rows sort the same everywhere."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def make_id(source: str, name: str) -> str:
    """The id of a row: the source it came from and the name of the file."""
    return f"{source}/{name}"


class DatasetRecord(BaseModel):
    """A text, and everything known about where it came from."""

    id: str = Field(..., description="Unique row id, '<source>/<name>'.")
    text: str = Field(..., description="The explanation itself.")
    title: str = Field("", description="What the text is about.")
    source: str = Field("", description="The folder or run the text came from.")
    model: str | None = Field(None, description="Model that wrote the text.")
    provider: str | None = Field(None, description="Provider the model was asked through.")
    instruction: str | None = Field(
        None, description="The user question this text answers, if it is known."
    )
    instruction_model: str | None = Field(
        None, description="Model that worked out the instruction, if one did."
    )
    tags: list[str] = Field(default_factory=list, description="Free labels.")
    word_count: int = Field(0, description="Number of words in the text.")
    added_at: datetime = Field(default_factory=utc_now, description="When the row was made.")

    @property
    def name(self) -> str:
        """The part of the id after the source."""
        return self.id.split("/", 1)[-1]

    @classmethod
    def build(cls, id: str, text: str, **fields) -> "DatasetRecord":
        """Make a row, counting its words for it."""
        text = text.strip()
        fields.setdefault("word_count", len(split_words(text)))
        return cls(id=id, text=text, **fields)

    def to_json_line(self) -> str:
        return self.model_dump_json()

    def merged_with(self, other: "DatasetRecord") -> "DatasetRecord":
        """This row, with anything it is missing taken from `other`.

        Used when the same id turns up twice: nothing that is already known is
        thrown away, and what only the other row knows is kept.
        """
        data = self.model_dump()
        other_data = other.model_dump()
        for key, value in other_data.items():
            if data.get(key) in (None, "", [], 0) and value not in (None, "", [], 0):
                data[key] = value
        return DatasetRecord(**data)
