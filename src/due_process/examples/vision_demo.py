"""Prove the scanned-IEP vision path on a real image.

    python -m due_process.examples.vision_demo

Generates a realistic IEP services-page *image* (synthetic content — no real
child), sends the IMAGE to Qwen's vision model to transcribe it, then runs the
deterministic extractor on the transcription. This exercises the full
scanned-document pipeline end to end, not just the wiring.

Privacy note: vision OCR sends the raw image (which on a real IEP contains the
child's PII) to the cloud. For real records, redact the image first or use the
self-hosted open-weight model. Here the content is synthetic, so it is safe.
"""

from __future__ import annotations

from pathlib import Path

from ..ingest import read_iep_image
from ..llm.client import default_client
from ..llm.extraction import extract_commitments

RULE = "=" * 72
_IMG = Path(__file__).with_name("sample_iep.png")

# A realistic (synthetic) IEP services page.
_LINES_TITLE = "INDIVIDUALIZED EDUCATION PROGRAM (IEP)"
_LINES_INFO = "Student: Jordan Rivera    DOB: 03/14/2017    Grade: 3"
_LINES_SCHOOL = "School: Maple Elementary    District: Springfield USD"
_LINES_SECTION = "SPECIAL EDUCATION AND RELATED SERVICES"
_TABLE = [
    ("Service", "Frequency", "Duration", "Setting", "Location"),
    ("Speech-Language Therapy", "3x / week", "30 min", "Individual", "Pull-out"),
    ("Occupational Therapy", "2x / week", "30 min", "Group (max 3)", "Push-in"),
    ("Physical Therapy", "1x / week", "30 min", "Individual", "Pull-out"),
]


def generate_iep_image(path: Path = _IMG) -> Path:
    """Render a synthetic IEP services page to a PNG (needs Pillow)."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1000, 620
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    def font(sz: int):
        try:
            return ImageFont.load_default(size=sz)
        except TypeError:  # very old Pillow
            return ImageFont.load_default()

    d.text((40, 24), _LINES_TITLE, fill="black", font=font(26))
    d.text((40, 64), _LINES_INFO, fill="black", font=font(18))
    d.text((40, 90), _LINES_SCHOOL, fill="black", font=font(18))
    d.text((40, 134), _LINES_SECTION, fill="black", font=font(20))

    cols = [40, 320, 470, 600, 800]
    y = 174
    for r, row in enumerate(_TABLE):
        f = font(18 if r == 0 else 17)
        for x, cell in zip(cols, row):
            d.text((x, y), cell, fill="black", font=f)
        d.line((40, y - 6, 960, y - 6), fill="black", width=1)
        y += 44
    d.line((40, y - 6, 960, y - 6), fill="black", width=1)

    d.text((40, y + 30), "Services begin: 09/02/2025   Annual review: 05/2026",
           fill="black", font=font(16))
    img.save(path)
    return path


def main() -> None:
    client = default_client()
    print(RULE)
    print("DUE PROCESS — scanned-IEP vision proof")
    print(RULE)

    try:
        generate_iep_image()
        print(f"Generated synthetic IEP image: {_IMG.name}")
    except ImportError:
        if not _IMG.exists():
            print("Pillow not installed and no committed image — cannot run.")
            return
        print(f"Using committed image: {_IMG.name}")

    if not client.available:
        print("\nNo DASHSCOPE_API_KEY — set it to run the live vision transcription.")
        return

    print(f"\nSending the IMAGE to Qwen vision ({client.config.vision_model}) ...")
    transcription = read_iep_image(str(_IMG), client)
    print("\n--- QWEN VISION TRANSCRIPTION ---")
    print(transcription)

    print("\n--- DETERMINISTIC EXTRACTION FROM THE TRANSCRIPTION ---")
    extracted = extract_commitments(transcription)  # rule-based, offline
    for e in extracted:
        c = e.commitment
        print(f"  {c.service_type.value}: {c.frequency_count}x/"
              f"{c.frequency_period.value}, {c.duration_minutes}min, "
              f"{c.setting.value}"
              + (f", {c.location.value}" if c.location else ""))
    print(f"\nParsed {len(extracted)} service(s) from a photographed IEP page. "
          "Vision pipeline verified end-to-end.")


if __name__ == "__main__":
    main()
