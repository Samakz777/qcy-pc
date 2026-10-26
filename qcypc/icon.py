from PIL import Image, ImageDraw


def make_icon(size: int = 256) -> Image.Image:
    """Ícone do app e da bandeja: dois fones brancos sobre fundo azul."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 4, fill=(31, 106, 165, 255))
    for cx in (0.34, 0.66):
        x, r = cx * s, 0.15 * s
        d.rounded_rectangle((x - 0.045 * s, 0.40 * s, x + 0.045 * s, 0.80 * s), radius=int(0.045 * s), fill="white")
        d.ellipse((x - r, 0.20 * s, x + r, 0.20 * s + 2 * r), fill="white")
    return img
