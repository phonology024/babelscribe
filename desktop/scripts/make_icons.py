"""Draw the babelscribe "b" mark and every icon and installer picture made from it.

    pip install fontTools brotli Pillow
    python desktop/scripts/make_icons.py              # writes desktop/src-tauri/icons/* and desktop/src-tauri/installer/*

The mark is a rounded square with a lowercase "b" in Poppins SemiBold (600), the same as the window's logo. The "b"
is taken as outlines from the Poppins file the app already bundles (SIL Open Font License), so no font is needed when
the icon is shown. Small sizes (16-32 px) are drawn on the pixel grid with a slightly larger, heavier "b", because
a scaled-down outline turns grey and blurry there.

Then run `npx @tauri-apps/cli@2.12.6 icon desktop/src-tauri/icons/icon-source.png -o <tmp>` for the Square*Logo
files (see docs/desktop-app.md); this script already writes icon.ico and the PNGs Windows uses.
"""
from __future__ import annotations


from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw, ImageFilter

DESKTOP = Path(__file__).resolve().parents[1]
FONT = DESKTOP / "src/assets/fonts/poppins-latin-600-normal.woff2"
ICONS = DESKTOP / "src-tauri/icons"
INSTALLER = DESKTOP / "src-tauri/installer"

TILE = (0x0B, 0x0B, 0x0C)        # near-black
INK = (0xEC, 0xE8, 0xE0)         # off-white "b"
EDGE = (0x3A, 0x38, 0x34)        # 1 px edge at small sizes, so the tile shows on a dark taskbar
GOLD = (0xC9, 0xA7, 0x5D)
RADIUS = 5 / 18                  # the window's .logo: 18 px square, 5 px corners
FONT_SIZE = 11 / 18              # ... and an 11 px "b"


class Flatten(BasePen):
    """Glyph outlines as closed polygons (font units, y up)."""

    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.contours: list[list[tuple[float, float]]] = []

    def _moveTo(self, p):
        self.contours.append([p])

    def _lineTo(self, p):
        self.contours[-1].append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.contours[-1][-1]
        for i in range(1, 17):
            t = i / 16
            a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
            self.contours[-1].append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                                      a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))

    def _qCurveToOne(self, p1, p2):
        p0 = self.contours[-1][-1]
        for i in range(1, 17):
            t = i / 16
            self.contours[-1].append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                                      (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))


def glyph():
    font = TTFont(FONT)
    glyphs = font.getGlyphSet()
    name = font.getBestCmap()[ord("b")]
    flat = Flatten(glyphs)
    glyphs[name].draw(flat)
    svg = SVGPathPen(glyphs)
    glyphs[name].draw(svg)
    xs = [x for c in flat.contours for x, _ in c]
    ys = [y for c in flat.contours for _, y in c]
    return flat.contours, svg.getCommands(), (min(xs), min(ys), max(xs), max(ys))


CONTOURS, SVG_PATH, (X0, Y0, X1, Y1) = glyph()


def glyph_mask(size: int, scale: float, left: float, top: float, bold: int = 0) -> Image.Image:
    """The "b" as an 8-bit mask: scale px per font unit, ink box at (left, top). Even-odd fill."""
    mask = Image.new("L", (size, size), 0)
    for contour in CONTOURS:
        one = Image.new("L", (size, size), 0)
        pts = [(left + (x - X0) * scale, top + (Y1 - y) * scale) for x, y in contour]
        ImageDraw.Draw(one).polygon(pts, fill=255)
        mask = ImageChops.logical_xor(mask.convert("1"), one.convert("1")).convert("L")
    if bold:
        mask = mask.filter(ImageFilter.MaxFilter(2 * bold + 1))
    return mask


def render(px: int, ink_height: float | None = None, bold: float = 0, edge: bool = False, snap: bool = False) -> Image.Image:
    """One icon of px x px. ink_height: height of the "b" in px (default: the window's proportions)."""
    ss = 16                                            # supersampling
    big = px * ss
    if ink_height is None:
        ink_height = px * FONT_SIZE * (Y1 - Y0) / 1000
    scale = ink_height * ss / (Y1 - Y0)
    w, h = (X1 - X0) * scale, (Y1 - Y0) * scale
    left, top = (big - w) / 2, (big - h) / 2
    if snap:                                           # stem edge and top of the "b" on whole pixels
        left, top = round(left / ss) * ss, round(top / ss) * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = RADIUS * big
    if edge:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=r, fill=EDGE + (255,))
        d.rounded_rectangle([ss, ss, big - 1 - ss, big - 1 - ss], radius=r - ss, fill=TILE + (255,))
    else:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=r, fill=TILE + (255,))
    mask = glyph_mask(big, scale, left, top, round(bold * ss))
    img.paste(Image.new("RGBA", (big, big), INK + (255,)), (0, 0), mask)
    return img.resize((px, px), Image.Resampling.BOX)


# Per-size drawing: the small sizes get a larger, heavier "b" on the pixel grid (hand-tuned by eye).
SMALL = {
    16: dict(ink_height=10, bold=0.25, edge=True, snap=True),
    20: dict(ink_height=12, bold=0.25, edge=True, snap=True),
    24: dict(ink_height=14, bold=0.25, edge=True, snap=True),
    32: dict(ink_height=18, bold=0.2, edge=True, snap=True),
    40: dict(ink_height=21, bold=0.15, edge=True, snap=True),
    48: dict(ink_height=25, bold=0.1, edge=True, snap=True),
}


def icon(px: int) -> Image.Image:
    return render(px, **SMALL.get(px, {}))


def svg() -> str:
    s = 1024 * FONT_SIZE / 1000
    tx = 512 - (X0 + X1) / 2 * s
    ty = 512 + (Y0 + Y1) / 2 * s
    r = RADIUS * 1024
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">\n'
        '  <title>babelscribe</title>\n'
        f'  <rect width="1024" height="1024" rx="{r:.1f}" fill="#0B0B0C"/>\n'
        '  <!-- lowercase b, Poppins SemiBold (SIL Open Font License 1.1), as outlines -->\n'
        f'  <path fill="#ECE8E0" transform="translate({tx:.2f} {ty:.2f}) scale({s:.6f} {-s:.6f})" d="{SVG_PATH}"/>\n'
        '</svg>\n'
    )


def bmp(img: Image.Image, path: Path) -> None:
    img.convert("RGB").save(path, format="BMP")


def header(w: int = 150, h: int = 57) -> Image.Image:
    """NSIS header picture: black with the mark and a thin gold rule."""
    img = Image.new("RGB", (w, h), TILE)
    mark = icon(32)
    img.paste(mark, (w - 32 - 12, (h - 32) // 2), mark)
    ImageDraw.Draw(img).rectangle([0, h - 2, w, h], fill=GOLD)
    return img


def sidebar(w: int = 164, h: int = 314) -> Image.Image:
    """NSIS welcome/finish picture (only shown by the uninstaller's finish, if at all)."""
    img = Image.new("RGB", (w, h), TILE)
    mark = icon(64)
    img.paste(mark, ((w - 64) // 2, 48), mark)
    ImageDraw.Draw(img).rectangle([(w - 40) // 2, 48 + 64 + 18, (w + 40) // 2, 48 + 64 + 19], fill=GOLD)
    return img


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    INSTALLER.mkdir(parents=True, exist_ok=True)
    (ICONS / "logo.svg").write_text(svg(), encoding="utf-8")
    render(1024).save(ICONS / "icon-source.png")
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    ico = {n: icon(n) for n in sizes}
    ico[256].save(ICONS / "icon.ico", format="ICO", sizes=[(n, n) for n in sizes],
                  append_images=[ico[n] for n in sizes if n != 256])
    for n, name in [(32, "32x32.png"), (64, "64x64.png"), (128, "128x128.png"), (256, "128x128@2x.png"),
                    (512, "icon.png")]:
        icon(n).save(ICONS / name)
    bmp(header(), INSTALLER / "header.bmp")
    bmp(sidebar(), INSTALLER / "sidebar.bmp")
    print("wrote", ICONS, INSTALLER)


if __name__ == "__main__":
    main()
