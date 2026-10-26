"""Owner-scoped images and their reusable visual descriptions."""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.mysql_db import connect
from app.vision import validate_image_data_url


def initialize() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS chat_images (
            image_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_id TEXT NOT NULL,
            filename TEXT NOT NULL, mime_type TEXT NOT NULL, byte_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL, width INTEGER, height INTEGER, content TEXT,
            image_blob BLOB NOT NULL, created_at TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chat_images_session ON chat_images(owner_id,session_id,created_at)")


def _dimensions(raw: bytes, mime: str) -> tuple[int | None, int | None]:
    if mime == "image/png" and len(raw) >= 24:
        return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    if mime == "image/gif" and len(raw) >= 10:
        return int.from_bytes(raw[6:8], "little"), int.from_bytes(raw[8:10], "little")
    if mime == "image/webp" and raw[12:16] == b"VP8X" and len(raw) >= 30:
        return int.from_bytes(raw[24:27], "little") + 1, int.from_bytes(raw[27:30], "little") + 1
    if mime == "image/jpeg":
        offset = 2
        while offset + 9 <= len(raw):
            if raw[offset] != 0xff:
                break
            marker = raw[offset + 1]
            if marker in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                return int.from_bytes(raw[offset + 7:offset + 9], "big"), int.from_bytes(raw[offset + 5:offset + 7], "big")
            if marker in {0xd8, 0xd9}:
                offset += 2
                continue
            length = int.from_bytes(raw[offset + 2:offset + 4], "big")
            if length < 2:
                break
            offset += length + 2
    return None, None


def _public(row: dict) -> dict:
    return {key: row[key] for key in ("image_id", "session_id", "filename", "mime_type", "byte_size", "sha256", "width", "height", "content", "created_at")}


def save(owner_id: str, session_id: str, filename: str, data_url: str) -> dict:
    canonical = validate_image_data_url(data_url)
    mime = canonical[5:canonical.index(";")]
    raw = base64.b64decode(canonical.partition(",")[2])
    digest = hashlib.sha256(raw).hexdigest()
    with connect() as db:
        existing = db.execute("SELECT * FROM chat_images WHERE owner_id=? AND session_id=? AND sha256=? ORDER BY created_at DESC LIMIT 1",
                              (owner_id, session_id, digest)).fetchone()
        if existing:
            return _public(existing) | {"reused": True}
        width, height = _dimensions(raw, mime)
        image_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        filename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip()[:180] or f"image-{image_id[:8]}.{mime.split('/')[-1]}"
        db.execute("INSERT INTO chat_images(image_id,owner_id,session_id,filename,mime_type,byte_size,sha256,width,height,content,image_blob,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (image_id, owner_id, session_id, filename, mime, len(raw), digest, width, height, None, raw, created_at))
    return {"image_id": image_id, "session_id": session_id, "filename": filename, "mime_type": mime,
            "byte_size": len(raw), "sha256": digest, "width": width, "height": height,
            "content": None, "created_at": created_at, "reused": False}


def get(owner_id: str, image_id: str, session_id: str | None = None) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM chat_images WHERE owner_id=? AND image_id=?", (owner_id, image_id)).fetchone()
    if not row or (session_id is not None and row["session_id"] != session_id):
        raise HTTPException(404, "当前会话中找不到这张图片")
    return dict(row)


def latest(owner_id: str, session_id: str) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM chat_images WHERE owner_id=? AND session_id=? ORDER BY created_at DESC LIMIT 1",
                         (owner_id, session_id)).fetchone()
    return _public(row) if row else None


def context(owner_id: str, session_id: str, limit: int = 3) -> str:
    with connect() as db:
        rows = db.execute("SELECT image_id,filename,mime_type,byte_size,sha256,width,height,content FROM chat_images WHERE owner_id=? AND session_id=? ORDER BY created_at DESC LIMIT ?",
                          (owner_id, session_id, limit)).fetchall()
    return "\n".join(
        f"图片 {row['image_id']}（{row['filename']}，{row['mime_type']}，{row['byte_size']} 字节，"
        f"{row['width'] or '?'}×{row['height'] or '?'}，SHA-256 {row['sha256']}）："
        f"{row['content'] or '尚未完成视觉解析；不能声称已看见图片内容。'}"
        for row in rows
    )


def set_content(owner_id: str, image_id: str, content: str) -> None:
    with connect() as db:
        db.execute("UPDATE chat_images SET content=? WHERE owner_id=? AND image_id=?", (content[:12000], owner_id, image_id))


def data_url(row: dict) -> str:
    return f"data:{row['mime_type']};base64,{base64.b64encode(row['image_blob']).decode('ascii')}"


def delete_session(owner_id: str, session_id: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM chat_images WHERE owner_id=? AND session_id=?", (owner_id, session_id))


def delete(owner_id: str, image_id: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM chat_images WHERE owner_id=? AND image_id=?", (owner_id, image_id))


def prune_orphans() -> None:
    with connect() as db:
        db.execute("DELETE FROM chat_images WHERE NOT EXISTS (SELECT 1 FROM memory_sessions WHERE memory_sessions.owner_id=chat_images.owner_id AND memory_sessions.session_id=chat_images.session_id AND memory_sessions.deleted_at IS NULL)")


def prune_expired(owner_id: str, cutoff_utc: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM chat_images WHERE owner_id=? AND created_at<?", (owner_id, cutoff_utc))
    prune_orphans()
