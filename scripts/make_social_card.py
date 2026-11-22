"""Generate PNG social card and app icons in static/ using Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"

BG_TOP = (8, 14, 26)
BG_BOTTOM = (15, 23, 42)
GRID_COLOR = (30, 58, 138, 45)
ACCENT_BLUE = (37, 99, 235)
LIGHT_BLUE = (96, 165, 250)
TEXT_PRIMARY = (226, 232, 240)
TEXT_MUTED = (148, 163, 184)
WHITE = (255, 255, 255)


def draw_vault_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int) -> None:
    """Draw a minimal vault door emblem centered at (cx, cy) with edge length `size`."""
    half = size // 2
    stroke = max(4, size // 12)
    outer = (cx - half, cy - half, cx + half, cy + half)
    draw.rounded_rectangle(outer, radius=max(8, size // 6), outline=WHITE, width=stroke)

    ring_r = int(size * 0.24)
    draw.ellipse(
        (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
        outline=WHITE,
        width=stroke,
    )
    hub_r = max(4, size // 16)
    draw.ellipse((cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r), fill=WHITE)

    hinge_x = cx + int(size * 0.34)
    hinge_w = max(4, size // 14)
    for dy in (-int(size * 0.22), int(size * 0.14)):
        draw.rounded_rectangle(
            (hinge_x, cy + dy, hinge_x + hinge_w, cy + dy + max(8, size // 7)),
            radius=2,
            fill=WHITE,
        )


def make_square_icon(
    size: int, output_path: Path, safe_ratio: float = 0.54, rounded: bool = True
) -> None:
    """Create a square PNG app icon at `output_path`."""
    mode = "RGBA" if rounded else "RGB"
    bg_fill = (0, 0, 0, 0) if rounded else ACCENT_BLUE
    img = Image.new(mode, (size, size), bg_fill)
    draw = ImageDraw.Draw(img)

    if rounded:
        radius = int(size * 0.20)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=ACCENT_BLUE)

    draw_vault_mark(draw, size // 2, size // 2, int(size * safe_ratio))
    img.save(output_path, format="PNG")


def make_social_card(output_path: Path) -> None:
    """Create a 1200x630 Open Graph preview PNG."""
    width, height = 1200, 630
    img = Image.new("RGBA", (width, height), BG_TOP)
    draw = ImageDraw.Draw(img)

    for y in range(height):
        t = y / (height - 1)
        color = tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3)) + (255,)
        draw.line([(0, y), (width, y)], fill=color)

    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=GRID_COLOR, width=1)
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=GRID_COLOR, width=1)

    badge_size = 156
    badge_x = 120
    badge_y = (height - badge_size) // 2
    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_size, badge_y + badge_size),
        radius=32,
        fill=ACCENT_BLUE,
    )
    draw_vault_mark(
        draw, badge_x + badge_size // 2, badge_y + badge_size // 2, int(badge_size * 0.56)
    )

    title_font = ImageFont.load_default(size=72)
    subtitle_font = ImageFont.load_default(size=32)
    detail_font = ImageFont.load_default(size=24)

    text_x = badge_x + badge_size + 52
    draw.text((text_x, badge_y + 8), "PromptVault", font=title_font, fill=TEXT_PRIMARY)
    draw.text(
        (text_x, badge_y + 96),
        "Prompt Library and Image Asset Archive",
        font=subtitle_font,
        fill=LIGHT_BLUE,
    )
    draw.text(
        (text_x, badge_y + 148),
        "Flask + SQLite + Pillow  |  CS50x Final Project",
        font=detail_font,
        fill=TEXT_MUTED,
    )

    img.convert("RGB").save(output_path, format="PNG")


def main() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    make_social_card(STATIC_DIR / "og-card.png")
    make_square_icon(192, STATIC_DIR / "icon-192.png", safe_ratio=0.56, rounded=True)
    make_square_icon(512, STATIC_DIR / "icon-512.png", safe_ratio=0.56, rounded=True)
    # Keep maskable emblem inside the central 80% safe zone (0.42 < 0.80) on a solid canvas.
    make_square_icon(512, STATIC_DIR / "icon-maskable-512.png", safe_ratio=0.42, rounded=False)
    make_square_icon(180, STATIC_DIR / "apple-touch-icon.png", safe_ratio=0.54, rounded=False)


if __name__ == "__main__":
    main()
