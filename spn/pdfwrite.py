"""把一张 JPEG 包成最小 PDF（纯标准库，用于生成演示样本）。

只做一件事：单页、满幅、DCTDecode 图片。够用来模拟"扫描件"。
"""

from __future__ import annotations

_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(data: bytes) -> tuple[int, int, int]:
    """返回 (宽, 高, 通道数)。"""
    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        if i + 4 > n:
            break
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in _SOF_MARKERS:
            height = int.from_bytes(data[i + 5:i + 7], "big")
            width = int.from_bytes(data[i + 7:i + 9], "big")
            comps = data[i + 9]
            return width, height, comps
        i += 2 + length
    raise ValueError("不是可解析的 JPEG")


def image_pdf(jpg: bytes, dpi: float = 150.0) -> bytes:
    width, height, comps = jpeg_size(jpg)
    color = {1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK"}.get(comps, "/DeviceRGB")
    pw = width / dpi * 72.0
    ph = height / dpi * 72.0

    content = f"q {pw:.2f} 0 0 {ph:.2f} 0 0 cm /Im0 Do Q".encode("ascii")
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.2f} {ph:.2f}] "
         f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>").encode("ascii"),
        (f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
         f"/ColorSpace {color} /BitsPerComponent 8 /Filter /DCTDecode "
         f"/Length {len(jpg)} >>\nstream\n").encode("ascii") + jpg + b"\nendstream",
        (f"<< /Length {len(content)} >>\nstream\n").encode("ascii") + content + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode("ascii")
    return bytes(out)
