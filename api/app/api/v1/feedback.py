"""Feedback and analytics endpoints."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.job import Job
from app.models.application import Application, ApplicationStatus
from app.models.feedback import Feedback
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    AnalyticsDashboard,
)

router = APIRouter()


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    feedback_data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create feedback for a cover letter or application."""
    feedback = Feedback(
        user_id=current_user.id,
        application_id=feedback_data.application_id,
        cover_letter_id=feedback_data.cover_letter_id,
        feedback_type=feedback_data.feedback_type,
        rating=feedback_data.rating,
        comment=feedback_data.comment,
        original_text=feedback_data.original_text,
        edited_text=feedback_data.edited_text,
        was_helpful=feedback_data.was_helpful,
        would_use_again=feedback_data.would_use_again,
    )

    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return feedback


@router.get("", response_model=List[FeedbackResponse])
async def list_feedback(
    feedback_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's feedback entries."""
    query = select(Feedback).where(Feedback.user_id == current_user.id)

    if feedback_type:
        query = query.where(Feedback.feedback_type == feedback_type)

    query = query.order_by(Feedback.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    feedback_entries = result.scalars().all()

    return feedback_entries


@router.get("/analytics/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive analytics dashboard."""
    # Get all applications
    result = await db.execute(
        select(Application).where(Application.user_id == current_user.id)
    )
    applications = result.scalars().all()

    total = len(applications)
    if total == 0:
        return AnalyticsDashboard(
            total_applications=0,
            response_rate=0.0,
            interview_rate=0.0,
            hire_rate=0.0,
            top_skills=[],
            top_industries=[],
            weekly_applications=[],
            insights=[],
        )

    submitted = [a for a in applications if a.status != ApplicationStatus.DRAFT]
    submitted_count = len(submitted)

    # Response stats
    responded = [a for a in submitted if a.status in [
        ApplicationStatus.RESPONDED,
        ApplicationStatus.INTERVIEWED,
        ApplicationStatus.HIRED,
    ]]
    interviewed = [a for a in submitted if a.status in [
        ApplicationStatus.INTERVIEWED,
        ApplicationStatus.HIRED,
    ]]
    hired = [a for a in submitted if a.status == ApplicationStatus.HIRED]

    response_rate = (len(responded) / submitted_count * 100) if submitted_count > 0 else 0.0
    interview_rate = (len(interviewed) / submitted_count * 100) if submitted_count > 0 else 0.0
    hire_rate = (len(hired) / submitted_count * 100) if submitted_count > 0 else 0.0

    # Average match score
    job_ids = [a.job_id for a in applications]
    avg_match_score = None
    if job_ids:
        result = await db.execute(
            select(func.avg(Job.match_score)).where(Job.id.in_(job_ids))
        )
        avg_match_score = result.scalar()

    # Average time to response
    avg_time_to_response = None
    response_times = []
    for app in responded:
        if app.submitted_at and app.responded_at:
            days = (app.responded_at - app.submitted_at).days
            response_times.append(days)
    if response_times:
        avg_time_to_response = sum(response_times) / len(response_times)

    # Get jobs for skill analysis
    result = await db.execute(
        select(Job).where(Job.id.in_(job_ids))
    )
    jobs = {j.id: j for j in result.scalars().all()}

    # Skill success analysis
    skill_outcomes = defaultdict(lambda: {"applied": 0, "responded": 0, "hired": 0})
    for app in submitted:
        job = jobs.get(app.job_id)
        if job and job.skills_required:
            for skill in job.skills_required:
                skill_outcomes[skill]["applied"] += 1
                if app.status in [
                    ApplicationStatus.RESPONDED,
                    ApplicationStatus.INTERVIEWED,
                    ApplicationStatus.HIRED,
                ]:
                    skill_outcomes[skill]["responded"] += 1
                if app.status == ApplicationStatus.HIRED:
                    skill_outcomes[skill]["hired"] += 1

    # Top skills by success rate (min 3 applications)
    top_skills = []
    for skill, outcomes in skill_outcomes.items():
        if outcomes["applied"] >= 3:
            success_rate = (outcomes["responded"] / outcomes["applied"]) * 100
            top_skills.append({
                "skill": skill,
                "success_rate": round(success_rate, 1),
                "applications": outcomes["applied"],
            })
    top_skills = sorted(top_skills, key=lambda x: x["success_rate"], reverse=True)[:5]

    # Weekly application trend (last 8 weeks)
    weekly_applications = []
    now = datetime.now(timezone.utc)
    for weeks_ago in range(7, -1, -1):
        week_start = now - timedelta(weeks=weeks_ago + 1)
        week_end = now - timedelta(weeks=weeks_ago)

        week_apps = [a for a in applications if week_start <= a.created_at < week_end]
        week_responses = [a for a in week_apps if a.status in [
            ApplicationStatus.RESPONDED,
            ApplicationStatus.INTERVIEWED,
            ApplicationStatus.HIRED,
        ]]

        weekly_applications.append({
            "week": week_start.strftime("%Y-%m-%d"),
            "applications": len(week_apps),
            "responses": len(week_responses),
        })

    # Generate insights
    insights = []

    if avg_match_score and avg_match_score > 70:
        insights.append({
            "type": "positive",
            "message": f"You're applying to well-matched jobs (avg score: {avg_match_score:.0f}%)",
            "confidence": 0.9,
        })

    if response_rate > 20:
        insights.append({
            "type": "positive",
            "message": f"Your response rate of {response_rate:.0f}% is above average",
            "confidence": 0.85,
        })
    elif response_rate < 10 and submitted_count > 5:
        insights.append({
            "type": "improvement",
            "message": "Consider customizing cover letters more for each job",
            "confidence": 0.7,
        })

    if top_skills and top_skills[0]["success_rate"] > 50:
        insights.append({
            "type": "positive",
            "message": f"Jobs requiring '{top_skills[0]['skill']}' have high success rate",
            "confidence": 0.8,
        })

    if avg_time_to_response and avg_time_to_response < 3:
        insights.append({
            "type": "positive",
            "message": f"Clients typically respond within {avg_time_to_response:.0f} days",
            "confidence": 0.75,
        })

    return AnalyticsDashboard(
        total_applications=total,
        response_rate=round(response_rate, 1),
        interview_rate=round(interview_rate, 1),
        hire_rate=round(hire_rate, 1),
        avg_match_score=round(avg_match_score, 1) if avg_match_score else None,
        avg_time_to_response_days=round(avg_time_to_response, 1) if avg_time_to_response else None,
        top_skills=top_skills,
        top_industries=[],  # Would need industry tracking on jobs
        weekly_applications=weekly_applications,
        insights=insights,
    )
