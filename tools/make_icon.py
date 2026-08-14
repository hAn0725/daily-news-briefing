"""生成简约商务风应用图标（新闻简报）"""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
ASSETS = Path(__file__).resolve().parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)


def make_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # ---- 圆角方块 + 蓝渐变背景 ----
    top = (31, 78, 121)        # #1F4E79
    bottom = (46, 117, 182)    # #2E75B6
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1],
                                           radius=58, fill=255)
    grad = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        gd.line([(0, y), (SIZE, y)], fill=c + (255,))
    img.paste(grad, (0, 0), mask)

    # ---- 顶部柔和高光 ----
    shine = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    sd.rounded_rectangle([18, 18, SIZE - 18, SIZE - 18], radius=44,
                         outline=(255, 255, 255, 34), width=3)
    img = Image.alpha_composite(img, shine)

    d = ImageDraw.Draw(img)

    # ---- 白色新闻文档 ----
    paper = (72, 54, 184, 202)
    d.rounded_rectangle(paper, radius=16, fill=(255, 255, 255, 255))

    # 折角（右上角）
    fold = [(184, 54), (184, 84), (154, 54)]
    d.polygon(fold, fill=(208, 216, 230, 255))
    d.line([(184, 84), (154, 54)], fill=(185, 195, 212, 255), width=3)

    # 红色强调条（顶部左侧）
    d.rounded_rectangle([88, 72, 122, 88], radius=8, fill=(232, 76, 61, 255))

    # 文字行（灰色）
    line = (176, 186, 201, 255)
    rows = [(88, 168), (88, 150), (88, 160), (88, 142)]
    y = 104
    for x0, x1 in rows:
        d.rounded_rectangle([x0, y, x1, y + 8], radius=4, fill=line)
        y += 20

    return img


def main():
    img = make_icon()
    out = ASSETS / "news.ico"
    img.save(out, sizes=[(256, 256), (128, 128), (64, 64),
                         (48, 48), (32, 32), (16, 16)])
    png = ASSETS / "news.png"
    img.save(png)
    print(f"图标已生成: {out} / {png}")


if __name__ == "__main__":
    main()
