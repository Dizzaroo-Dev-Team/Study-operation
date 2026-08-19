"""REST API: visit-attached files (documents) + visit-attached communication (threads + messages).

Both URL prefixes hang off ``/visits/{visit_id}/`` and share the same helpers
(_ensure_monitor_tables, _require_monitoring_visit, _append_visit_activity)
which still live in app.modules.monitoring.aggregator. Those are pulled in via lazy import
to avoid the circular dependency that would otherwise arise.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter(tags=["monitor"])


# Lazy imports of cross-cluster helpers.
async def _ensure_tables(db: AsyncSession) -> None:
    from app.modules.monitoring.aggregator import _ensure_monitor_tables
    await _ensure_monitor_tables(db)


async def _require_visit(db: AsyncSession, visit_id: str) -> None:
    from app.modules.monitoring.aggregator import _require_monitoring_visit
    await _require_monitoring_visit(db, visit_id)


async def _append_activity(db: AsyncSession, visit_id: str, message: str, **kwargs) -> None:
    from app.modules.monitoring.aggregator import _append_visit_activity
    await _append_visit_activity(db, visit_id, message, **kwargs)


# --- Documents (file attachments) -------------------------------------------

@router.get("/visits/{visit_id}/documents")
async def get_documents(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    await _require_visit(db, visit_id)
    rows = await db.execute(
        text("SELECT * FROM monitoring_documents WHERE visit_id = :visit_id ORDER BY id DESC"),
        {"visit_id": visit_id},
    )
    result = []
    for row in rows.mappings().all():
        result.append({
            "id": row["id"],
            "category": row["category"],
            "icon": row["icon"],
            "name": row["name"],
            "size": row["size"],
            "date": row["date"],
            "uploader": {"initials": row["uploader_initials"], "name": row["uploader_name"], "color": row["uploader_color"]},
        })
    return result


@router.post("/visits/{visit_id}/documents")
async def upload_document(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    document_name = payload.get("name", f"Document_{int(datetime.now(timezone.utc).timestamp())}.pdf")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_documents (
                visit_id, category, icon, name, size, date, uploader_initials, uploader_name, uploader_color
            ) VALUES (
                :visit_id, :category, :icon, :name, :size, :date, :initials, :uploader_name, :color
            )
            """
        ),
        {
            "visit_id": visit_id,
            "category": payload.get("category", "Regulatory Documents"),
            "icon": payload.get("icon", "📄"),
            "name": document_name,
            "size": payload.get("size", "256 KB"),
            "date": payload.get("date", datetime.now(timezone.utc).strftime("%b %d, %Y")),
            "initials": payload.get("uploaderInitials", "SC"),
            "uploader_name": payload.get("uploaderName", "Sarah Chen"),
            "color": payload.get("uploaderColor", "blue"),
        },
    )
    await _append_activity(
        db,
        visit_id,
        f"Uploaded document: {document_name}",
        initials=payload.get("uploaderInitials", "SC"),
        color=payload.get("uploaderColor", "blue"),
    )
    await db.commit()
    return {"status": "uploaded"}


@router.delete("/visits/{visit_id}/documents/{document_id}")
async def delete_document(visit_id: str, document_id: int, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    await db.execute(
        text("DELETE FROM monitoring_documents WHERE id = :document_id AND visit_id = :visit_id"),
        {"document_id": document_id, "visit_id": visit_id},
    )
    await _append_activity(db, visit_id, f"Deleted document #{document_id}")
    await db.commit()
    return {"status": "deleted"}


# --- Conversations (threads + messages) -------------------------------------

@router.get("/visits/{visit_id}/conversations")
async def get_conversations(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    await _require_visit(db, visit_id)
    thread_rows = await db.execute(
        text("SELECT id, title, participants, last_msg, unread FROM monitoring_threads WHERE visit_id = :visit_id ORDER BY id ASC"),
        {"visit_id": visit_id},
    )
    message_rows = await db.execute(
        text("SELECT id, sender, initials, color, text, time, is_me FROM monitoring_messages WHERE visit_id = :visit_id ORDER BY id ASC"),
        {"visit_id": visit_id},
    )
    return {
        "threads": [
            {"id": r.id, "title": r.title, "participants": r.participants, "lastMsg": r.last_msg, "unread": r.unread}
            for r in thread_rows.fetchall()
        ],
        "messages": [
            {"id": r.id, "sender": r.sender, "initials": r.initials, "color": r.color, "text": r.text, "time": r.time, "isMe": r.is_me}
            for r in message_rows.fetchall()
        ],
    }


@router.post("/visits/{visit_id}/conversations/threads")
async def add_thread(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    title = payload.get("title", "New Thread")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_threads (visit_id, title, participants, last_msg, unread)
            VALUES (:visit_id, :title, 'Sarah Chen', 'Just now · 0 msgs', 0)
            """
        ),
        {"visit_id": visit_id, "title": title},
    )
    await _append_activity(db, visit_id, f"Started conversation thread: {title}")
    await db.commit()
    return {"status": "created"}


@router.post("/visits/{visit_id}/conversations/messages")
async def add_message(visit_id: str, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    message_text = payload.get("text", "")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_messages (visit_id, sender, initials, color, text, time, is_me)
            VALUES (:visit_id, :sender, :initials, :color, :message_text, 'Just now', true)
            """
        ),
        {
            "visit_id": visit_id,
            "sender": payload.get("sender", "Sarah Chen (You)"),
            "initials": payload.get("initials", "SC"),
            "color": payload.get("color", "blue"),
            "message_text": message_text,
        },
    )
    if message_text:
        await _append_activity(
            db,
            visit_id,
            f"Posted message: {str(message_text)[:60]}",
            initials=payload.get("initials", "SC"),
            color=payload.get("color", "blue"),
        )
    await db.commit()
    return {"status": "sent"}
