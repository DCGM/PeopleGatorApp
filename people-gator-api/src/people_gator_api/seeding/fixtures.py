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
    Person("provenance-review", "Irena Evidence", (),
           "Synthetic imported identity with separately edited annotations in two libraries.", "importer"),
    Person(
        "link-ada",
        "Ada Review",
        ("A. Review",),
        "Synthetic link review subject with automatic and verified evidence.",
        "importer",
    ),
    Person(
        "link-emil",
        "Emil Review",
        (),
        "Synthetic link review subject with manually assigned evidence.",
        "reviewer",
    ),
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
    Document("provenance-a", "preview-mzk", "Annotation review ledger"),
    Document("provenance-b", "preview-nlk", "Annotation review correspondence"),
    Document("issue8-direct", "preview-nlk", "Direct annotation ledger"),
    Document("issue8-search", "preview-mzk", "Příběhy archivářů"),
    Document("issue8-mirror", "preview-nlk", "Search isolation mirror", "issue8-search"),
    Document("issue8-orphan", "preview-mzk", "Orphan source touch", registered=False),
    Document("faces-no-ocr", "preview-mzk", "Faces without OCR"),
    Document("link-states", "preview-mzk", "Link state review"),
    Document("album", "preview-mzk", "Portrait album"),
    Document("notes", "preview-nlk", "Research notes"),
    Document("letters", "preview-mzk", "Correspondence"),
    Document("grouped-album", "preview-mzk", "Named preview album"),
    Document(
        "grouped-mirror", "preview-nlk", "Album in another library", "grouped-album"
    ),
    Document("empty-document", "preview-mzk", "Document awaiting scans"),
    Document("legacy-document", "preview-mzk", "Legacy unnamed document", named=False),
    Document(
        "scan-only", "preview-mzk", "Unregistered scan collection", registered=False
    ),
    Document("issue10-media", "preview-mzk", "Media upload sandbox"),
)


@dataclass(frozen=True)
class Face:
    key: str
    person: str | None
    slot: int
    group: int
    state: str = "automatic"
    embedded: bool = True


@dataclass(frozen=True)
class Mention:
    key: str
    person: str
    text: str
    state: str | None = "automatic"


@dataclass(frozen=True)
class Page:
    key: str
    document: str
    number: int
    faces: tuple[Face, ...] = ()
    mentions: tuple[Mention, ...] = ()
    has_layout: bool = True

    @property
    def page_id(self) -> UUID:
        return fixture_id("page/" + self.key)


PAGES = (
    Page("provenance-a-1", "provenance-a", 1,
        (Face("provenance-auto", "provenance-review", 0, 1),
         Face("provenance-authority", "provenance-review", 1, 1, "verified")),
        (Mention("provenance-mention-auto", "provenance-review", "Irena Evidence imported this catalogue."),)),
    Page("provenance-b-1", "provenance-b", 1,
        (Face("provenance-manual", "provenance-review", 0, 1, "manual"),
         Face("provenance-unknown", "provenance-review", 1, 1)),
        (Mention("provenance-mention-verified", "provenance-review", "Irena Evidence verified this correspondence.", "verified"),)),
    Page("issue8-untouched", "issue8-search", 1),
    *(Page(f"issue8-search-{i}", "issue8-search", i,
        (Face(f"issue8-face-{i}", "ada", 0, 0, "verified" if i == 6 else "automatic", embedded=False),),
        (Mention(f"issue8-mention-{i}", "nora", "Nora Svoboda indexed these archivist stories."),)
        if i == 5 else ()) for i in range(2, 7)),
    Page("issue8-mirror-1", "issue8-mirror", 1),
    Page("issue8-orphan-1", "issue8-orphan", 1,
        (Face("issue8-orphan-face", None, 0, 2, embedded=False),)),
    Page(
        "faces-no-ocr-1", "faces-no-ocr", 1,
        (Face("no-ocr-left", None, 0, 2), Face("no-ocr-right", None, 1, 3)),
        has_layout=False,
    ),
    Page(
        "links-1",
        "link-states",
        1,
        (
            Face("links-auto", "link-ada", 0, 2),
            Face("links-manual", "link-emil", 1, 3, "manual"),
        ),
        (
            Mention(
                "links-auto-mention", "link-ada", "Ada Review supplied the catalogue."
            ),
            Mention(
                "links-manual-mention",
                "link-emil",
                "Emil Review arranged the portraits.",
                "manual",
            ),
        ),
    ),
    Page(
        "links-2",
        "link-states",
        2,
        (
            Face("links-verified", "link-ada", 0, 2, "verified"),
            Face("links-unassigned", None, 1, 3),
        ),
        (
            Mention(
                "links-verified-mention",
                "link-ada",
                "Ada\nReview checked the catalogue.",
                "verified",
            ),
            Mention(
                "links-unassigned-mention",
                "link-emil",
                "Emil Review awaits identification.",
                None,
            ),
        ),
    ),
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
    # Evidence-free pages for replacing scans/layouts without invalidating boxes.
    Page("media-upload-1", "issue10-media", 1),
    Page("media-upload-2", "issue10-media", 2),
)

ISSUE8_IMAGE_URL = "https://preview.invalid/issue8/portrait.png"

ISSUE8_IMAGE_PAGE = Page("issue8-image", "issue8-direct", 1, (Face("issue8-image-face", None, 0, 2, embedded=False),), has_layout=False)
