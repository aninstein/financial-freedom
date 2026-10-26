"""Owner-scoped Markdown browser and editor for the investment wiki."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import investment_memory as memory, security
from app.mysql_db import connect


router = APIRouter(prefix="/api/v1/ai/memory/wiki", tags=["investment-wiki"])
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
VERSION = re.compile(r"report-v\d+\.md\Z")


class WikiEdit(BaseModel):
    path: str = Field(min_length=1, max_length=400)
    content: str = Field(min_length=1, max_length=30000)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _parts(relative: str) -> tuple[str, ...]:
    if not relative:
        return ()
    if "\\" in relative or relative.startswith("/") or "\x00" in relative:
        raise HTTPException(422, "无效的 wiki 路径")
    parts = tuple(relative.split("/"))
    if any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        raise HTTPException(422, "无效的 wiki 路径")
    return parts


def _path(owner_id: str, relative: str) -> tuple[Path, tuple[str, ...]]:
    parts = _parts(relative)
    if len(parts) >= 2 and parts[0] in {"sessions", "daily"} and DATE.fullmatch(parts[1]):
        field = "session_days" if parts[0] == "sessions" else "archive_days"
        if parts[1] < memory._cutoff(owner_id, field):
            raise HTTPException(404, "文档已超过保留期限")
    root = memory.wiki_root(owner_id)
    if not root.is_dir():
        root = memory.ensure_space(owner_id)
    target = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise HTTPException(404, "wiki 路径不可用")
    if target.resolve() != root and root not in target.resolve().parents:
        raise HTTPException(422, "无效的 wiki 路径")
    return target, parts


def _kind(parts: tuple[str, ...]) -> str:
    if not parts or not parts[-1].endswith(".md"):
        raise HTTPException(404, "仅支持 Markdown 文档")
    name = parts[-1]
    if name in {"index.md", "readme.md", "log.md"}:
        return name[:-3]
    if len(parts) == 3 and parts[0] == "daily" and DATE.fullmatch(parts[1]):
        if name == "report.md":
            return "daily"
        if VERSION.fullmatch(name):
            return "daily-version"
    if len(parts) == 2 and parts[0] in {"short-term", "long-term"} and re.fullmatch(r"M-[a-f0-9]{24}\.md", name):
        return "entry"
    if len(parts) == 3 and parts[0] == "sessions" and DATE.fullmatch(parts[1]) and name.endswith(".summary.md"):
        return "summary"
    raise HTTPException(404, "不支持的 wiki 文档")


def list_directory(owner_id: str, relative: str = "") -> dict[str, Any]:
    folder, parts = _path(owner_id, relative)
    if not folder.is_dir():
        raise HTTPException(404, "wiki 目录不存在")
    items: list[dict[str, Any]] = []
    for child in folder.iterdir():
        if child.name.startswith(".") or child.is_symlink():
            continue
        path = "/".join((*parts, child.name))
        if child.is_dir():
            if len(parts) == 1 and parts[0] in {"daily", "sessions"} and DATE.fullmatch(child.name):
                field = "archive_days" if parts[0] == "daily" else "session_days"
                if child.name < memory._cutoff(owner_id, field):
                    continue
            items.append({"name": child.name, "path": path, "type": "directory"})
        elif child.is_file() and child.name.endswith(".md"):
            try:
                kind = _kind((*parts, child.name))
            except HTTPException:
                continue
            items.append({"name": child.name, "path": path, "type": "markdown",
                          "editable": kind != "daily-version", "kind": kind})
    items.sort(key=lambda item: (item["type"] != "directory", item["name"] != "index.md", item["name"]), reverse=False)
    return {"path": relative, "items": items}


def get_document(owner_id: str, relative: str) -> dict[str, Any]:
    path, parts = _path(owner_id, relative)
    kind = _kind(parts)
    if not path.is_file():
        raise HTTPException(404, "Markdown 文档不存在")
    if kind == "daily":
        try:
            verified = memory.get_daily(owner_id, parts[1])
        except KeyError as exc:
            raise HTTPException(404, "日报待重新归档") from exc
        if path.read_text(encoding="utf-8") != verified["content"]:
            with memory._FILE_LOCK:
                memory._atomic(path, verified["content"])
                memory._manifest(owner_id, path, verified["version"])
    if kind == "entry":
        try:
            memory.get_entry(owner_id, path.stem)
        except KeyError as exc:
            raise HTTPException(404, "记忆条目不可用") from exc
    content = path.read_text(encoding="utf-8")
    return {"path": relative, "name": path.name, "kind": kind,
            "editable": kind != "daily-version", "content": content,
            "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _source_block(content: str) -> str:
    start = content.find("## 来源索引")
    end = content.find("## 说明", start + 1)
    if start < 0 or end < 0:
        raise HTTPException(422, "日报必须保留系统来源索引和说明章节")
    return content[start:end]


def _metadata_line(content: str, prefix: str) -> str:
    return next((line for line in content.splitlines() if line.startswith(prefix)), "")


def _save_daily(owner_id: str, day: str, content: str, previous: str) -> None:
    if _source_block(content) != _source_block(previous):
        raise HTTPException(422, "来源索引由系统维护，不能在编辑器中更改")
    for label in ("状态：", "输入哈希：", "消息："):
        if _metadata_line(content, label) != _metadata_line(previous, label):
            raise HTTPException(422, f"{label}由系统维护，不能更改")
    if not content.startswith(f"# {day}") or not _metadata_line(content, "版本："):
        raise HTTPException(422, "日报标题或版本元数据无效")
    with connect() as db:
        pub = db.execute("SELECT version,status,input_hash FROM memory_archive_publications WHERE owner_id=? AND local_date=?",
                         (owner_id, day)).fetchone()
        job = db.execute("SELECT version,input_hash FROM memory_archive_jobs WHERE owner_id=? AND local_date=?",
                         (owner_id, day)).fetchone()
    if not pub or not job or pub["input_hash"] != job["input_hash"] or pub["version"] != job["version"]:
        raise HTTPException(409, "日报已变化，请刷新后重试")
    version = int(pub["version"]) + 1
    edited = re.sub(r"(?m)^版本：.*$", f"版本：{version}", content, count=1)
    if "编辑来源：用户" not in edited:
        edited = edited.replace("\n## 主题与决策", "\n编辑来源：用户\n\n## 主题与决策", 1)
    edited = edited.rstrip() + "\n"
    folder = memory.wiki_root(owner_id) / "daily" / day
    version_file = folder / f"report-v{version}.md"
    memory._atomic(version_file, edited)
    memory._manifest(owner_id, version_file, version)
    try:
        with connect() as db:
            updated = db.execute("UPDATE memory_archive_publications SET version=?,published_at=? WHERE owner_id=? AND local_date=? AND version=? AND input_hash=?",
                                 (version, memory.stamp(), owner_id, day, pub["version"], pub["input_hash"]))
            if updated.rowcount != 1:
                raise HTTPException(409, "日报已变化，请刷新后重试")
            job_update = db.execute("UPDATE memory_archive_jobs SET version=?,updated_at=? WHERE owner_id=? AND local_date=? AND version=? AND input_hash=?",
                                    (version, memory.stamp(), owner_id, day, pub["version"], pub["input_hash"]))
            if job_update.rowcount != 1:
                raise HTTPException(409, "日报输入已变化，请刷新后重试")
    except Exception:
        version_file.unlink(missing_ok=True)
        memory._drop_manifest(owner_id, version_file)
        raise
    memory._atomic(folder / "report.md", edited)
    memory._manifest(owner_id, folder / "report.md", version)
    memory._refresh_index(folder, f"{day} 日报")
    memory._log(folder, "owner-edit", f"report-v{version}.md")


def save_document(owner_id: str, relative: str, content: str, expected_sha256: str) -> dict[str, Any]:
    if len(content.encode("utf-8")) > 60000:
        raise HTTPException(422, "Markdown 文档过大")
    with memory._FILE_LOCK:
        current = get_document(owner_id, relative)
        if not current["editable"]:
            raise HTTPException(422, "历史版本只读，请编辑当前 report.md")
        if current["sha256"] != expected_sha256:
            raise HTTPException(409, "文档已更新，请刷新后合并修改")
        path, parts = _path(owner_id, relative)
        kind = current["kind"]
        if kind == "entry":
            old_end = current["content"].find("\n---\n", 4)
            new_end = content.find("\n---\n", 4)
            if not current["content"].startswith("---\n") or old_end < 0 or new_end < 0 or content[:new_end + 5] != current["content"][:old_end + 5]:
                raise HTTPException(422, "来源与状态元数据由系统维护，请只编辑正文")
            body = content[new_end + 5:].strip()
            if not 3 <= len(body) <= 1000:
                raise HTTPException(422, "记忆正文须为 3–1000 字")
            memory.update_entry(owner_id, path.stem, body)
        elif kind == "daily":
            _save_daily(owner_id, parts[1], content, current["content"])
        elif kind == "summary":
            anchor = "## 用户议题（摘述）"
            if anchor not in content or content.split(anchor, 1)[0] != current["content"].split(anchor, 1)[0]:
                raise HTTPException(422, "会话来源元数据由系统维护，请只编辑议题部分")
            memory._atomic(path.parent / f".{path.name}.manual", content.rstrip() + "\n")
            memory._atomic(path, content.rstrip() + "\n")
            memory._manifest(owner_id, path)
        else:
            normalized = content.rstrip() + "\n"
            if kind in {"index", "log"}:
                memory._atomic(path.parent / f".{path.name}.manual", normalized)
            memory._atomic(path, normalized)
            memory._manifest(owner_id, path)
        return get_document(owner_id, relative)


@router.get("/tree")
def api_tree(path: str = Query(default="", max_length=400)) -> dict[str, Any]:
    return list_directory(security.current_owner_id(), path)


@router.get("/file")
def api_file(path: str = Query(min_length=1, max_length=400)) -> dict[str, Any]:
    return get_document(security.current_owner_id(), path)


@router.put("/file")
def api_save_file(body: WikiEdit) -> dict[str, Any]:
    return save_document(security.current_owner_id(), body.path, body.content, body.expected_sha256)
