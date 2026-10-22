"""Small, synthetic preview scenarios. Stable keys are part of the seed identity."""

from dataclasses import dataclass
from uuid import UUID, uuid5

NAMESPACE = UUID("3de5e244-1389-42bd-af9d-d99667987951")
MODEL = "preview-synthetic-8d-v1"
SECOND_MODEL = "preview-synthetic-4d-v1"
DISCOVERY_MODEL = "preview-discovery-8d-v1"
DISCOVERY_OTHER_MODEL = "preview-discovery-other-4d-v1"


def fixture_id(key: str) -> UUID:
    return uuid5(NAMESPACE, key)


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    aliases: tuple[str, ...]
    description: str
    actor: str


PAGINATION_ITEMS = 14

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
    # Issue #33: sortable evidence with exact recorded-text mention variants.
    Person(
        "sorting",
        "Marta Řádková",
        ("M. Řádková",),
        "Synthetic sorting subject with varied confidence, states and mention spellings.",
        "importer",
    ),
    Person("discovery", "Zora Cartographer", ("Saffron Navigator",),
           "Synthetic discovery reference with many faces and mixed embedding availability.", "importer"),
    Person("discovery-face", "Orion Portrait", (), "Appearance match for Zora.", "importer"),
    Person("discovery-name", "Zora Cartographer II", (), "Recorded-name match for Zora.", "importer"),
    Person("discovery-alias", "Saffron Navigator", (), "Recorded-alias match for Zora.", "importer"),
    # Issue #62: a searchable, linked scenario exceeding a 12-item list batch.
    *(Person(f"pagination-{i}", f"Pagination Person {i:02}", (),
             "Synthetic automatic pagination example.", "reviewer")
      for i in range(1, PAGINATION_ITEMS + 1)),
    # Issue #52: one person linked by the curator's key, and one whose own
    # record the curator edits after a reviewer linked her face.
    Person("shared-ivo", "Ivo Ledger", (),
           "Synthetic person linked by the preview curator's API key.", "curator"),
    Person("shared-hana", "Hana Ledger", (),
           "Synthetic person whose own record the curator edited after a reviewer's face link.", "reviewer"),
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
    Document("focus", "preview-mzk", "Viewport focus practice"),
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
    Document("page-gallery", "preview-mzk", "Page gallery navigation"),
    # Accent/case name variants and uneven page counts across two libraries (#33).
    Document("sorting-ledger", "preview-nlk", "Řádková ledger"),
    Document("sorting-notes", "preview-mzk", "radkova notes"),
    Document("discovery", "preview-mzk", "Entity discovery practice"),
    # Shared filters (#52): the same archive ID in a second, unannotated library.
    Document("shared-ledger", "preview-mzk", "Shared filter ledger"),
    Document("shared-mirror", "preview-nlk", "Shared filter mirror", "shared-ledger"),
    *(Document(f"pagination-{i}", "preview-pagination", f"Pagination ledger {i:02}")
      for i in range(1, PAGINATION_ITEMS + 1)),
    Document("alignment", "preview-mzk", "Face alignment recovery"),
)


@dataclass(frozen=True)
class Face:
    key: str
    person: str | None
    slot: int
    group: int
    state: str = "automatic"
    embedded: bool = True
    box: tuple[int, int, int, int] | None = None
    confidence: float = 0.97
    models: tuple[str, ...] = (MODEL, SECOND_MODEL)
    zero_vector: bool = False
    coincident_keypoints: bool = False


@dataclass(frozen=True)
class Mention:
    key: str
    person: str
    text: str
    state: str | None = "automatic"
    y: int | None = None
    # Exact recorded text when it differs from the person's name; never normalized.
    recorded: str | None = None


@dataclass(frozen=True)
class Page:
    key: str
    document: str
    number: int
    faces: tuple[Face, ...] = ()
    mentions: tuple[Mention, ...] = ()
    has_layout: bool = True
    has_image: bool = True

    @property
    def page_id(self) -> UUID:
        return fixture_id("page/" + self.key)


PAGE_GALLERY_PAGES = 14
PAGE_GALLERY_MISSING_MEDIA = 9

PAGES = (
    Page("provenance-a-1", "provenance-a", 1,
        (Face("provenance-auto", "provenance-review", 0, 1),
         Face("provenance-authority", "provenance-review", 1, 1, "verified")),
        (Mention("provenance-mention-auto", "provenance-review", "Irena Evidence imported this catalogue."),)),
    Page("provenance-b-1", "provenance-b", 1,
        (Face("provenance-manual", "provenance-review", 0, 1, "manual"),
         Face("provenance-unknown", "provenance-review", 1, 1)),
        (Mention("provenance-mention-verified", "provenance-review", "Irena Evidence verified this correspondence.", "verified"),)),
    Page("focus-1", "focus", 1,
        (Face("focus-upper", "ada", 0, 0, box=(70, 220, 160, 190)),
         Face("focus-lower", "ada", 1, 0, box=(560, 760, 160, 190)),
         Face("focus-tiny", None, 2, 2, box=(700, 260, 16, 19))),
        (Mention("focus-name-upper", "ada", "Ada Novak catalogued this portrait.", y=460),
         Mention("focus-name-lower", "ada", "Ada Novak returned to review the collection.", y=1000))),
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
    # Evidence-free pages for scan-workspace page navigation: more pages than one
    # frontend gallery batch (12), and one registered page without stored media.
    *(Page(f"page-gallery-{i}", "page-gallery", i,
           has_layout=i != PAGE_GALLERY_MISSING_MEDIA,
           has_image=i != PAGE_GALLERY_MISSING_MEDIA)
      for i in range(1, PAGE_GALLERY_PAGES + 1)),
    # Sorting scenario (#33): three ledger pages (one evidence-free) and one note.
    Page("sorting-ledger-1", "sorting-ledger", 1,
         (Face("sorting-manual", "sorting", 0, 4, "manual", confidence=0.62),
          Face("sorting-automatic", "sorting", 1, 4, confidence=0.88)),
         (Mention("sorting-exact-1", "sorting", "Marta Řádková opened the ledger.", "manual"),
          Mention("sorting-initial", "sorting", "M. Řádková signed the first entry.", recorded="M. Řádková"))),
    Page("sorting-ledger-2", "sorting-ledger", 2,
         (Face("sorting-verified", "sorting", 0, 4, "verified", confidence=0.75),
          Face("sorting-similar", None, 1, 4, confidence=0.91)),
         (Mention("sorting-upper", "sorting", "MARTA ŘÁDKOVÁ appears in the heading.", recorded="MARTA ŘÁDKOVÁ"),
          Mention("sorting-exact-2", "sorting", "Marta Řádková closed the ledger."))),
    Page("sorting-ledger-3", "sorting-ledger", 3),
    Page("sorting-notes-1", "sorting-notes", 1,
         mentions=(Mention("sorting-unaccented", "sorting", "Marta Radkova copied these notes.", recorded="Marta Radkova"),
                   Mention("sorting-exact-3", "sorting", "Marta Řádková reviewed the copy."))),
    *(Page(f"discovery-{i + 1}", "discovery", i + 1,
        tuple(Face(f"discovery-reference-{i * 2 + j}", "discovery", j, 0,
                   models=(DISCOVERY_MODEL,)) for j in range(2))) for i in range(6)),
    Page("discovery-7", "discovery", 7, (
        Face("discovery-missing", "discovery", 0, 0, embedded=False),
        Face("discovery-other-model", "discovery", 1, 0, models=(DISCOVERY_OTHER_MODEL,)),
    )),
    Page("discovery-8", "discovery", 8, (
        Face("discovery-zero-reference", "discovery", 0, 0, models=(DISCOVERY_MODEL,), zero_vector=True),
        Face("discovery-face-match", "discovery-face", 1, 0, models=(DISCOVERY_MODEL,)),
    )),
    Page("discovery-9", "discovery", 9, (
        Face("discovery-zero-candidate", "discovery-face", 0, 0, models=(DISCOVERY_MODEL,), zero_vector=True),
        Face("discovery-name-match", "discovery-name", 1, 1, models=(DISCOVERY_MODEL,)),
    )),
    Page("discovery-10", "discovery", 10, (
        Face("discovery-alias-match", "discovery-alias", 0, 2, models=(DISCOVERY_MODEL,)),
        Face("discovery-unassigned", None, 1, 0, models=(DISCOVERY_MODEL,)),
    )),
    # Shared filters (#52): the reviewer's face precedes the curator's mention,
    # so the document's latest change is the curator's.
    Page("shared-ledger-1", "shared-ledger", 1,
         (Face("shared-hana-face", "shared-hana", 0, 5, embedded=False),)),
    Page("shared-ledger-2", "shared-ledger", 2,
         mentions=(Mention("shared-ivo-mention", "shared-ivo", "Ivo Ledger recorded the shared filter ledger."),)),
    Page("shared-mirror-1", "shared-mirror", 1),
    *(Page(f"pagination-{i}", f"pagination-{i}", 1,
           mentions=(Mention(f"pagination-{i}", f"pagination-{i}",
                             f"Pagination Person {i:02} recorded this ledger."),))
      for i in range(1, PAGINATION_ITEMS + 1)),
    # Issue #64: stored, finite geometry that cannot be aligned, beside a valid
    # control. Independent keys keep existing media, reviews and timestamps intact.
    Page("alignment-1", "alignment", 1, (
        Face("alignment-coincident", None, 0, 2, embedded=False, coincident_keypoints=True),
        Face("alignment-valid", None, 1, 3, embedded=False),
    )),
)

ISSUE8_IMAGE_URL = "https://preview.invalid/issue8/portrait.png"

ISSUE8_IMAGE_PAGE = Page("issue8-image", "issue8-direct", 1, (Face("issue8-image-face", None, 0, 2, embedded=False),), has_layout=False)
