"""Small, synthetic preview scenarios. Stable keys are part of the seed identity."""

from dataclasses import dataclass
from uuid import UUID, uuid5

NAMESPACE = UUID("3de5e244-1389-42bd-af9d-d99667987951")
MODEL = "preview-synthetic-8d-v1"
SECOND_MODEL = "preview-synthetic-4d-v1"


def fixture_id(key: str) -> UUID:
    return uuid5(NAMESPACE, key)


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    aliases: tuple[str, ...]
    description: str
    actor: str


PEOPLE = (
    Person(
        "ada",
        "Ada Novak",
        ("A. Novak",),
        "Synthetic archivist with faces and mentions across two documents.",
        "importer",
    ),
    Person(
        "emil",
        "Emil Dvorak",
        ("E. Dvorak",),
        "Synthetic photographer linked through face detections only.",
        "reviewer",
    ),
    Person(
        "nora",
        "Nora Svoboda",
        ("N. Svoboda",),
        "Synthetic researcher linked through OCR mentions only.",
        "ocr",
    ),
    Person(
        "viktor",
        "Viktor Marek",
        (),
        "Synthetic editor in a second library, with faces and mentions.",
        "reviewer",
    ),
    Person(
        "lenka",
        "Lenka Vesela",
        (),
        "Synthetic identity without evidence, ready for manual linking.",
        "reviewer",
    ),
    Person(
        "ada-candidate",
        "A. Novak",
        ("Ada N.",),
        "Synthetic duplicate candidate: similar vectors make it discoverable from Ada Novak.",
        "importer",
    ),
)


@dataclass(frozen=True)
class Document:
    key: str
    library: str
    title: str
    identity_key: str | None = None
    registered: bool = True
    named: bool = True

    @property
    def document_id(self) -> UUID:
        return fixture_id("document/" + (self.identity_key or self.key))


DOCUMENTS = (
    Document("album", "preview-mzk", "Portrait album"),
    Document("notes", "preview-nlk", "Research notes"),
    Document("letters", "preview-mzk", "Correspondence"),
    Document("grouped-album", "preview-mzk", "Named preview album"),
    Document("grouped-mirror", "preview-nlk", "Album in another library", "grouped-album"),
    Document("empty-document", "preview-mzk", "Document awaiting scans"),
    Document("legacy-document", "preview-mzk", "Legacy unnamed document", named=False),
    Document("scan-only", "preview-mzk", "Unregistered scan collection", registered=False),
)


@dataclass(frozen=True)
class Face:
    key: str
    person: str | None
    slot: int
    group: int


@dataclass(frozen=True)
class Mention:
    key: str
    person: str
    text: str


@dataclass(frozen=True)
class Page:
    key: str
    document: str
    number: int
    faces: tuple[Face, ...] = ()
    mentions: tuple[Mention, ...] = ()

    @property
    def page_id(self) -> UUID:
        return fixture_id("page/" + self.key)


PAGES = (
    Page(
        "album-1",
        "album",
        1,
        (
            Face("ada-portrait", "ada", 0, 0),
            Face("emil-portrait", "emil", 1, 1),
            Face("unassigned-ada", None, 2, 0),
        ),
        (
            Mention(
                "ada-caption",
                "ada",
                "Ada Novak catalogued the portraits with Emil Dvorak.",
            ),
        ),
    ),
    Page(
        "album-2",
        "album",
        2,
        (
            Face("ada-second", "ada", 0, 0),
            Face("ada-candidate", "ada-candidate", 1, 0),
            Face("unassigned-other", None, 2, 3),
        ),
    ),
    Page(
        "notes-1",
        "notes",
        1,
        (Face("viktor-portrait", "viktor", 0, 2),),
        (
            Mention(
                "nora-notes",
                "nora",
                "Nora Svoboda discussed the archive with Viktor Marek.",
            ),
            Mention(
                "viktor-notes", "viktor", "Viktor Marek edited these research notes."
            ),
        ),
    ),
    Page(
        "notes-2",
        "notes",
        2,
        (Face("emil-second", "emil", 0, 1),),
        (
            Mention(
                "ada-notes", "ada", "Ada Novak supplied photographs for Nora Svoboda."
            ),
            Mention(
                "nora-second", "nora", "Nora Svoboda prepared the final catalogue."
            ),
        ),
    ),
    Page(
        "letters-1",
        "letters",
        1,
        mentions=(
            Mention(
                "nora-letter",
                "nora",
                "Nora Svoboda wrote to Ada Novak about the collection.",
            ),
        ),
    ),
    Page("letters-2", "letters", 2),
    Page("grouped-album-1", "grouped-album", 1),
    Page("grouped-album-2", "grouped-album", 2),
    Page("grouped-mirror-1", "grouped-mirror", 1),
    Page("legacy-document-1", "legacy-document", 1),
    Page("scan-only-1", "scan-only", 1),
)
