"""
Feasibility service layer for external MongoDB integration.

Centralizes all MongoDB queries related to feasibility questionnaires so that
endpoints don't access the Mongo client directly.
"""

from typing import List, Optional
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.feasibility_mongo import get_feasibility_mongo_db
from app.models import Study
from app import schemas

logger = logging.getLogger(__name__)


async def _get_project_and_feasibility_doc(study: Study):
    """
    Internal helper to find the matching project and feasibilityquestionnaires document
    for a given Study, using the same matching logic as the existing endpoints.
    """
    try:
        try:
            from bson import ObjectId
        except ImportError:
            from pymongo import ObjectId
    except Exception:  # pragma: no cover - import fallback
        ObjectId = None  # type: ignore

    feasibility_db = await get_feasibility_mongo_db()
    if feasibility_db is None:
        return None

    logger.info(
        "[FEASIBILITY] Querying MongoDB for study.id=%s, study.study_id='%s', study.name='%s'",
        study.id,
        study.study_id,
        study.name,
    )

    projects_collection = feasibility_db["projects"]
    feasibility_collection = feasibility_db["feasibilityquestionnaires"]

    project_doc = None

    # Build candidate filters based on study_id/name
    candidates = []
    if study.study_id:
        candidates.append({"studyId": study.study_id})
        candidates.append({"name": study.study_id})
    if getattr(study, "name", None):
        candidates.append({"studyId": study.name})
        candidates.append({"name": study.name})

    # Step 1: exact matches
    for filt in candidates:
        if project_doc:
            break
        logger.info("[FEASIBILITY] Trying project filter: %s", filt)
        project_doc = await projects_collection.find_one(filt)

    # Step 1b: fuzzy search if no exact match
    if not project_doc and (study.study_id or getattr(study, "name", None)):
        all_projects = await projects_collection.find({}).to_list(length=200)
        logger.info("[FEASIBILITY] No exact project match; scanning %d projects", len(all_projects))

        search_keys = [v for v in [study.study_id, getattr(study, "name", None)] if v]
        lowered_search = [v.lower() for v in search_keys]

        for proj in all_projects:
            proj_name = str(proj.get("name", "")).lower()
            proj_study_id = str(proj.get("studyId", "")).lower()
            for sv in lowered_search:
                if sv == proj_name or sv == proj_study_id or sv in proj_name or sv in proj_study_id:
                    project_doc = proj
                    logger.info(
                        "[FEASIBILITY] ✅ Fuzzy project match: proj.studyId='%s', proj.name='%s'",
                        proj.get("studyId"),
                        proj.get("name"),
                    )
                    break
            if project_doc:
                break

    if not project_doc:
        logger.warning(
            "[FEASIBILITY] ❌ No project found in 'projects' collection for study.study_id='%s'",
            study.study_id,
        )
        return None

    project_id = project_doc.get("_id") or project_doc.get("id")
    logger.info("[FEASIBILITY] ✅ Using project _id=%s", project_id)

    # Step 2: query feasibilityquestionnaires by project ObjectId
    if ObjectId is None:
        return None

    try:
        if isinstance(project_id, str):
            project_obj_id = ObjectId(project_id)
        else:
            project_obj_id = project_id

        doc = await feasibility_collection.find_one({"project": project_obj_id})
        if doc:
            logger.info(
                "[FEASIBILITY] ✅ Found feasibility questionnaire! Questions: %d",
                len(doc.get("questionnaire", [])),
            )
        return doc
    except Exception as e:
        logger.warning("[FEASIBILITY] Error converting/querying ObjectId: %s", e)
        return None


async def get_feasibility_questions_for_questionnaire(
    db: AsyncSession,
    project_id: str,
) -> tuple[Study, List[schemas.FeasibilityQuestion]]:
    """
    Fetch external + custom feasibility questions for the questionnaire endpoint.
    Mirrors the previous logic in get_feasibility_questionnaire.
    """
    # Resolve study by UUID or study_id
    from uuid import UUID as UUIDType
    from app.models import Study as StudyModel, ProjectFeasibilityCustomQuestion

    try:
        study_uuid = UUIDType(str(project_id))
        study_result = await db.execute(select(StudyModel).where(StudyModel.id == study_uuid))
        study = study_result.scalar_one_or_none()
    except (ValueError, TypeError):
        study_result = await db.execute(select(StudyModel).where(StudyModel.study_id == project_id))
        study = study_result.scalar_one_or_none()

    if not study:
        raise ValueError("Study/Project not found")

    all_questions: List[schemas.FeasibilityQuestion] = []

    # 1. External questions from MongoDB
    try:
        doc = await _get_project_and_feasibility_doc(study)

        questions_list = None
        if doc:
            if "questionnaire" in doc:
                questions_list = doc.get("questionnaire", [])
            elif "object" in doc:
                questions_list = doc.get("object", [])

        if questions_list:
            for idx, q in enumerate(questions_list):
                question_text = q.get("question_text") or q.get("text", "")
                question_section = q.get("section")
                question_type = q.get("expected_response_type") or q.get("type", "text")
                criterion_ref = q.get("criterion_reference") or q.get("criterion")

                if question_text:
                    all_questions.append(
                        schemas.FeasibilityQuestion(
                            text=question_text,
                            section=question_section,
                            type=question_type,
                            source="external",
                            criterion_reference=criterion_ref,
                            display_order=idx,
                        )
                    )
    except Exception as e:
        logger.warning("External feasibility MongoDB unavailable: %s", e)

    # 2. Custom questions from CRM DB (unchanged)
    custom_questions_result = await db.execute(
        select(ProjectFeasibilityCustomQuestion)
        .where(ProjectFeasibilityCustomQuestion.study_id == study.id)
        .where(ProjectFeasibilityCustomQuestion.workflow_step == "feasibility")
        .order_by(
            ProjectFeasibilityCustomQuestion.display_order,
            ProjectFeasibilityCustomQuestion.created_at,
        )
    )
    custom_questions = custom_questions_result.scalars().all()

    for cq in custom_questions:
        all_questions.append(
            schemas.FeasibilityQuestion(
                text=cq.question_text,
                section=cq.section,
                type=cq.expected_response_type or "text",
                source="custom",
                criterion_reference=None,
                display_order=cq.display_order,
                id=cq.id,
            )
        )

    # Sort by display_order, then source (external first)
    all_questions.sort(key=lambda q: (q.display_order or 0, 0 if q.source == "external" else 1))

    return study, all_questions


async def get_feasibility_questions_for_form(
    db: AsyncSession,
    study_id: str,
) -> tuple[Optional[Study], List[schemas.FeasibilityQuestion]]:
    """
    Fetch external feasibility questions for the public form endpoint.
    Mirrors the previous MongoDB logic in get_feasibility_form.
    """
    from uuid import UUID as UUIDType
    from app.models import Study as StudyModel

    # Resolve study (same as in clinical_workflow)
    try:
        study_uuid = UUIDType(str(study_id))
        study_result = await db.execute(select(StudyModel).where(StudyModel.id == study_uuid))
        study = study_result.scalar_one_or_none()
    except (ValueError, TypeError):
        study_result = await db.execute(select(StudyModel).where(StudyModel.study_id == study_id))
        study = study_result.scalar_one_or_none()

    if not study:
        return None, []

    all_questions: List[schemas.FeasibilityQuestion] = []

    try:
        doc = await _get_project_and_feasibility_doc(study)

        questions_list = None
        if doc:
            if "questionnaire" in doc:
                questions_list = doc.get("questionnaire", [])
            elif "object" in doc:
                questions_list = doc.get("object", [])

        if questions_list:
            for q in questions_list:
                question_text = (
                    q.get("question_text") or q.get("text") or q.get("question") or ""
                )
                question_section = q.get("section")
                question_type = q.get("expected_response_type") or q.get("type", "text")
                criterion_ref = q.get("criterion_reference") or q.get("criterion")

                if question_text:
                    all_questions.append(
                        schemas.FeasibilityQuestion(
                            text=question_text,
                            section=question_section,
                            type=question_type,
                            source="external",
                            criterion_reference=criterion_ref,
                            display_order=q.get("display_order", 0),
                            id=None,
                        )
                    )
    except Exception as e:
        logger.warning("External feasibility MongoDB unavailable: %s", e)

    return study, all_questions

