"""Validate transient clipboard images before passing them to a vision model."""

from __future__ import annotations

import base64
import binascii
import re

MAX_IMAGE_BYTES = 5 * 1024 * 1024
_DATA_URL = re.compile(r"\Adata:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/]+={0,2})\Z")


def validate_image_data_url(value: str) -> str:
    match = _DATA_URL.fullmatch(value)
    if not match or len(match.group(2)) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise ValueError("请粘贴不超过 5 MB 的 PNG、JPEG、GIF 或 WebP 图片")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except binascii.Error as exc:
        raise ValueError("剪贴板图片编码无效") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("请粘贴不超过 5 MB 的图片")
    mime = match.group(1)
    valid = {
        "png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpeg": raw.startswith(b"\xff\xd8\xff"),
        "gif": raw.startswith((b"GIF87a", b"GIF89a")),
        "webp": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
    }
    if not valid[mime]:
        raise ValueError("剪贴板内容不是有效的图片格式")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode('ascii')}"
