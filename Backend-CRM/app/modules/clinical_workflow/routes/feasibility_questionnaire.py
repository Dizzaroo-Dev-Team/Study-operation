"""REST API: feasibility questionnaire (custom questions + MongoDB merge + debug)."""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.db import get_db
from app.models import ProjectFeasibilityCustomQuestion, Study

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Clinical Workflow"])


@router.get("/feasibility-questionnaire/{project_id}", response_model=schemas.FeasibilityQuestionnaireResponse)
async def get_feasibility_questionnaire(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get feasibility questionnaire for a project/study.
    Merges external MongoDB questions with CRM custom questions.

    - project_id: Can be Study.id (UUID) or Study.study_id (string)
    - Returns merged list of questions from both sources
    - If external MongoDB is unavailable or no questions found, returns empty list (no error)
    """
    from app.modules.feasibility.services.feasibility_service import get_feasibility_questions_for_questionnaire

    study, all_questions = await get_feasibility_questions_for_questionnaire(db, project_id)

    return schemas.FeasibilityQuestionnaireResponse(
        project_id=str(study.id),
        questions=all_questions,
    )


@router.get("/feasibility-questionnaire/debug/test-connection")
async def debug_test_feasibility_connection(
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    Debug endpoint to test MongoDB connection and see what's actually in the database.
    This helps diagnose why questions aren't being fetched.
    """
    from app.db.feasibility_mongo import get_feasibility_mongo_db

    result = {
        "connection_status": "unknown",
        "database_name": None,
        "collections": [],
        "feasibilityquestionnaires_count": 0,
        "sample_documents": [],
        "test_queries": {},
    }

    try:
        feasibility_db = await get_feasibility_mongo_db()
        if feasibility_db is None:
            result["connection_status"] = "failed - no database connection"
            return result

        result["connection_status"] = "connected"
        result["database_name"] = feasibility_db.name

        collections = await feasibility_db.list_collection_names()
        result["collections"] = collections

        collection = feasibility_db["feasibilityquestionnaires"]
        doc_count = await collection.count_documents({})
        result["feasibilityquestionnaires_count"] = doc_count

        sample_docs = await collection.find({}).limit(5).to_list(length=5)
        for sample in sample_docs:
            project_val = sample.get("project")
            questions_count = len(sample.get("questionnaire", []))
            result["sample_documents"].append(
                {
                    "_id": str(sample.get("_id")),
                    "project": str(project_val) if project_val else None,
                    "project_type": type(project_val).__name__ if project_val else None,
                    "questions_count": questions_count,
                    "keys": list(sample.keys()),
                }
            )

        all_docs = await collection.find({}).to_list(length=100)
        result["all_project_objectids"] = []
        for doc in all_docs:
            proj = doc.get("project")
            if proj:
                result["all_project_objectids"].append(
                    {
                        "objectid": str(proj),
                        "questions_count": len(doc.get("questionnaire", [])),
                    }
                )

    except Exception as e:
        result["connection_status"] = f"error: {str(e)}"
        import traceback
        result["traceback"] = traceback.format_exc()

    return result


@router.post("/feasibility-questionnaire/custom-questions", response_model=schemas.CustomQuestionResponse)
async def create_custom_question(
    question_data: schemas.CustomQuestionCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom feasibility question in CRM DB."""
    study = None
    try:
        try:
            study_uuid = UUID(str(question_data.study_id))
            study_result = await db.execute(select(Study).where(Study.id == study_uuid))
            study = study_result.scalar_one_or_none()
        except (ValueError, TypeError):
            study_result = await db.execute(
                select(Study).where(
                    (Study.study_id == str(question_data.study_id)) |
                    (Study.name == str(question_data.study_id))
                )
            )
            study = study_result.scalar_one_or_none()
    except Exception as e:
        logger.exception(f"Error resolving study: {e}")

    if not study:
        raise HTTPException(status_code=404, detail=f"Study not found: {question_data.study_id}")

    custom_question = ProjectFeasibilityCustomQuestion(
        study_id=study.id,
        workflow_step="feasibility",
        question_text=question_data.question_text,
        section=question_data.section,
        expected_response_type=question_data.expected_response_type or "text",
        display_order=question_data.display_order or 0,
        created_by=current_user.get("user_id") if current_user else None,
    )

    db.add(custom_question)
    await db.commit()
    await db.refresh(custom_question)

    return custom_question


@router.get("/feasibility-questionnaire/custom-questions/{study_id}", response_model=List[schemas.CustomQuestionResponse])
async def list_custom_questions(
    study_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """List all custom questions for a study."""
    try:
        study_uuid = UUID(str(study_id))
        study_result = await db.execute(select(Study).where(Study.id == study_uuid))
        study = study_result.scalar_one_or_none()
    except (ValueError, TypeError):
        study_result = await db.execute(select(Study).where(Study.study_id == study_id))
        study = study_result.scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    result = await db.execute(
        select(ProjectFeasibilityCustomQuestion)
        .where(ProjectFeasibilityCustomQuestion.study_id == study.id)
        .where(ProjectFeasibilityCustomQuestion.workflow_step == "feasibility")
        .order_by(ProjectFeasibilityCustomQuestion.display_order, ProjectFeasibilityCustomQuestion.created_at)
    )

    return result.scalars().all()


@router.put("/feasibility-questionnaire/custom-questions/{question_id}", response_model=schemas.CustomQuestionResponse)
async def update_custom_question(
    question_id: UUID,
    question_data: schemas.CustomQuestionUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom feasibility question."""
    result = await db.execute(
        select(ProjectFeasibilityCustomQuestion).where(ProjectFeasibilityCustomQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(status_code=404, detail="Custom question not found")

    if question_data.question_text is not None:
        question.question_text = question_data.question_text
    if question_data.section is not None:
        question.section = question_data.section
    if question_data.expected_response_type is not None:
        question.expected_response_type = question_data.expected_response_type
    if question_data.display_order is not None:
        question.display_order = question_data.display_order

    await db.commit()
    await db.refresh(question)

    return question


@router.delete("/feasibility-questionnaire/custom-questions/{question_id}")
async def delete_custom_question(
    question_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom feasibility question."""
    result = await db.execute(
        select(ProjectFeasibilityCustomQuestion).where(ProjectFeasibilityCustomQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(status_code=404, detail="Custom question not found")

    await db.delete(question)
    await db.commit()

    return {"message": "Custom question deleted successfully"}
