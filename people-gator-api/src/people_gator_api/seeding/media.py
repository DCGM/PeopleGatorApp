"""Generate deterministic page scans and matching OCR geometry without downloads."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from people_gator_api.schemas.common import BoundingBox
from people_gator_api.schemas.enums import FaceKeypointType
from people_gator_api.schemas.faces import FaceKeypoint
from people_gator_api.schemas.pero import (
    PageLayoutModel,
    RegionLayoutModel,
    TextLineModel,
)
from .fixtures import PEOPLE, Document, Face, Page

PAGE_SIZE = (800, 1100)  # width, height


def face_box(face: Face) -> BoundingBox:
    if face.box is not None:
        return BoundingBox(x=face.box[0], y=face.box[1], width=face.box[2], height=face.box[3])
    return BoundingBox(x=70 + face.slot * 250, y=220, width=160, height=190)


def face_keypoints(face: Face) -> list[FaceKeypoint]:
    box = face_box(face)
    points = ((50, 65), (110, 65), (80, 100), (55, 135), (105, 135))
    if face.coincident_keypoints:
        points = ((80, 95),) * 5  # All required types, at the in-bounds box center.
    return [
        FaceKeypoint(type=kind, x=box.x + x * box.width / 160, y=box.y + y * box.height / 190)
        for kind, (x, y) in zip(FaceKeypointType, points, strict=True)
    ]


def page_layout(page: Page) -> PageLayoutModel:
    lines: list[TextLineModel] = []
    for mention in page.mentions:
        for fragment, transcription in enumerate(mention.text.split("\n")):
            index = len(lines)
            y = mention.y if mention.y is not None else 540 + index * 55
            lines.append(TextLineModel(
                id=mention.key + (f"-{fragment}" if "\n" in mention.text else ""),
                baseline=[[50, y + 25], [750, y + 25]],
                polygon=[[50, y], [750, y], [750, y + 35], [50, y + 35]],
                heights=[25, 10], transcription=transcription, index=index,
                transcription_confidence=0.99,
            ))
    return PageLayoutModel(
        id=str(page.page_id),
        page_size=(PAGE_SIZE[1], PAGE_SIZE[0]),
        regions=[
            RegionLayoutModel(
                id="text",
                polygon=[[40, 500], [760, 500], [760, 1000], [40, 1000]],
                transcription="\n".join(line.transcription for line in lines),
                lines=lines,
            )
        ],
        reading_order={"text": 0},
    )


def page_image(page: Page, document: Document) -> bytes:
    image = Image.new("RGB", PAGE_SIZE, "#faf7ee")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    draw.rectangle((25, 25, 775, 1075), outline="#aaa28e", width=2)
    draw.text((50, 55), "PEOPLE GATOR / SYNTHETIC PREVIEW", fill="#555555", font=font)
    draw.text(
        (50, 100), f"{document.title} / page {page.number}", fill="#202020", font=font
    )
    draw.text(
        (50, 145),
        "Illustrated fixtures, not archive scans or real people.",
        fill="#555555",
        font=font,
    )
    for face in page.faces:
        box = face_box(face)
        x, y = box.x, box.y
        colors = ("#e6bd99", "#c99d80", "#efd3b8", "#bfa58c")
        draw.ellipse((x, y, x + box.width, y + box.height), fill=colors[face.group % len(colors)])
        if face.box is not None:
            for point in face_keypoints(face)[:2]:
                radius = max(1, box.width / 32)
                draw.ellipse((point.x - radius, point.y - radius,
                              point.x + radius, point.y + radius), fill="#303030")
            continue
        draw.arc((x, y - 5, x + box.width, y + 100), 180, 360, fill="#54463b", width=18)
        points = face_keypoints(face)
        for point in points[:2]:
            draw.ellipse(
                (point.x - 5, point.y - 4, point.x + 5, point.y + 4), fill="#303030"
            )
        draw.line(
            (x + 80, y + 80, x + 75, y + 105, x + 85, y + 105), fill="#775544", width=2
        )
        draw.arc((x + 55, y + 120, x + 105, y + 145), 0, 180, fill="#775544", width=3)
        draw.text(
            (x, y + 205),
            next(
                (person.name for person in PEOPLE if person.key == face.person),
                "Unassigned face",
            ),
            fill="#303030",
            font=font,
        )
    for line in page_layout(page).regions[0].lines:
        draw.text((50, line.polygon[0][1]), line.transcription, fill="#303030", font=font)
    if not page.faces and not page.mentions:
        draw.text(
            (50, 220),
            "An empty page for testing evidence filters.",
            fill="#555555",
            font=font,
        )
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def png_image(page: Page, document: Document) -> bytes:
    """An actual PNG for arbitrary image sources with a PNG URL identity."""
    buffer = BytesIO()
    with Image.open(BytesIO(page_image(page, document))) as image:
        image.save(buffer, "PNG")
    return buffer.getvalue()
