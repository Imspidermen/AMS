from datetime import date, datetime, timedelta
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.core.security import hash_password, opaque_hash
from app.core.timezone import (
    CampusRangeEnd,
    CampusRangeStart,
    as_utc,
    campus_date,
    to_campus,
    utc_now,
    utc_offset_label,
)
from app.db.session import get_db
from app.models.entities import (
    AcademicYear,
    AppSetting,
    Attendance,
    AuditEvent,
    ClassSession,
    Course,
    CorrectionRequest,
    Department,
    Enrollment,
    FaceEnrollment,
    Location,
    Notification,
    Section,
    Semester,
    Student,
    Teacher,
    TeacherAssignment,
    User,
    UserSession,
    VerificationAttempt,
)
from app.services.audit import audit
from app.services.corrections import resolve_correction

router = APIRouter(prefix="/admin", tags=["administration"])
admin_only = require_roles("admin")


class DepartmentInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=30)


class StudentInput(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    student_number: str = Field(min_length=1, max_length=60)
    department_id: str
    program: str = Field(default="", max_length=160)
    semester_id: str | None = None


class TeacherInput(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    employee_number: str = Field(min_length=1, max_length=60)
    department_id: str


class StudentUpdateInput(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    student_number: str | None = Field(default=None, min_length=1, max_length=60)
    department_id: str | None = None
    program: str | None = Field(default=None, max_length=160)
    semester_id: str | None = None
    enrollment_status: str | None = None

    @field_validator("enrollment_status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in {"active", "inactive", "withdrawn", "graduated"}:
            raise ValueError("Invalid student enrollment status")
        return value


class TeacherUpdateInput(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    employee_number: str | None = Field(default=None, min_length=1, max_length=60)
    department_id: str | None = None


class AcademicYearInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    starts_on: date
    ends_on: date
    active: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if self.ends_on <= self.starts_on:
            raise ValueError("Academic year end must follow its start")
        return self


class SemesterInput(BaseModel):
    academic_year_id: str
    name: str = Field(min_length=2, max_length=80)
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def validate_range(self):
        if self.ends_on <= self.starts_on:
            raise ValueError("Semester end must follow its start")
        return self


class CourseInput(BaseModel):
    department_id: str
    semester_id: str | None = None
    course_code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=2000)
    attendance_threshold: float | None = Field(default=None, ge=0, le=100)


class SectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class EnrollmentInput(BaseModel):
    student_id: str
    course_id: str
    section_id: str | None = None


class AssignmentInput(BaseModel):
    teacher_id: str
    course_id: str
    section_id: str | None = None


class LocationInput(BaseModel):
    department_id: str
    name: str = Field(min_length=2, max_length=160)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=100, gt=0, le=5000)
    max_accuracy_m: float = Field(default=100, gt=0, le=1000)
    active: bool = True


class SessionInput(BaseModel):
    course_id: str
    section_id: str | None = None
    location_id: str
    title: str = Field(default="Class session", min_length=2, max_length=180)
    starts_at: datetime
    ends_at: datetime
    grace_minutes: int = Field(default=10, ge=0, le=180)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Schedule timestamps must include a timezone (use ISO-8601 with Z or offset)")
        return as_utc(value)

    @model_validator(mode="after")
    def validate_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Session end must follow its start")
        return self


class UserStatusInput(BaseModel):
    active: bool


class CoursePatchInput(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    attendance_threshold: float | None = Field(default=None, ge=0, le=100)
    active: bool | None = None


class GlobalSettingsInput(BaseModel):
    low_attendance_threshold: float = Field(ge=0, le=100)


class CorrectionInput(BaseModel):
    student_id: str
    session_id: str
    status: str
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator("status")
    @classmethod
    def status_allowed(cls, value: str):
        if value not in {"present", "late", "absent", "excused"}:
            raise ValueError("Status must be present, late, absent, or excused")
        return value


def _handle_integrity(db: Session, message: str):
    db.rollback()
    raise HTTPException(status_code=409, detail=message)


def _invite_user(db: Session, email: str, full_name: str, role: str, actor: User) -> tuple[User, str]:
    raw_token = secrets.token_urlsafe(36)
    user = User(
        email=str(email).strip().lower(),
        full_name=full_name.strip(),
        role=role,
        password_hash=None,
        activation_hash=opaque_hash(raw_token),
        activation_expires_at=utc_now() + timedelta(days=7),
        active=True,
    )
    db.add(user)
    db.flush()
    return user, raw_token


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return {
        "students": db.query(Student).count(),
        "teachers": db.query(Teacher).count(),
        "courses": db.query(Course).filter(Course.active.is_(True)).count(),
        "upcoming_sessions": db.query(ClassSession).filter(
            ClassSession.starts_at >= utc_now(), ClassSession.cancelled.is_(False)
        ).count(),
        "pending_corrections": db.query(CorrectionRequest).filter(CorrectionRequest.status == "pending").count(),
        "failed_verifications": db.query(VerificationAttempt).filter(
            VerificationAttempt.status == "rejected"
        ).count(),
    }


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [
        {"id": x.id, "name": x.name, "code": x.code, "active": x.active}
        for x in db.query(Department).order_by(Department.name).all()
    ]


@router.post("/departments", status_code=201)
def create_department(payload: DepartmentInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    item = Department(name=payload.name.strip(), code=payload.code.strip().upper())
    db.add(item)
    try:
        db.flush()
        audit(db, actor.id, "department.created", "department", item.id)
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Department name and code must be unique")
    return {"id": item.id, "name": item.name, "code": item.code, "active": item.active}


@router.get("/academic-years")
def list_academic_years(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [{"id": x.id, "name": x.name, "starts_on": x.starts_on, "ends_on": x.ends_on, "active": x.active}
            for x in db.query(AcademicYear).order_by(AcademicYear.name.desc()).all()]


@router.post("/academic-years", status_code=201)
def create_academic_year(payload: AcademicYearInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if payload.active:
        db.query(AcademicYear).update({AcademicYear.active: False})
    item = AcademicYear(name=payload.name.strip(), starts_on=payload.starts_on.isoformat(),
                        ends_on=payload.ends_on.isoformat(), active=payload.active)
    db.add(item)
    try:
        db.flush()
        audit(db, actor.id, "academic_year.created", "academic_year", item.id)
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Academic year name must be unique")
    return {"id": item.id, "name": item.name, "starts_on": item.starts_on, "ends_on": item.ends_on, "active": item.active}


@router.get("/semesters")
def list_semesters(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [{"id": x.id, "academic_year_id": x.academic_year_id, "name": x.name,
             "starts_on": x.starts_on, "ends_on": x.ends_on}
            for x in db.query(Semester).order_by(Semester.starts_on.desc()).all()]


@router.post("/semesters", status_code=201)
def create_semester(payload: SemesterInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not db.get(AcademicYear, payload.academic_year_id):
        raise HTTPException(404, "Academic year not found")
    item = Semester(academic_year_id=payload.academic_year_id, name=payload.name.strip(),
                    starts_on=payload.starts_on.isoformat(), ends_on=payload.ends_on.isoformat())
    db.add(item)
    try:
        db.flush()
        audit(db, actor.id, "semester.created", "semester", item.id)
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Semester name must be unique within its academic year")
    return {"id": item.id, "academic_year_id": item.academic_year_id, "name": item.name,
            "starts_on": item.starts_on, "ends_on": item.ends_on}


@router.get("/courses")
def list_courses(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [course_view(course) for course in db.query(Course).order_by(Course.course_code).all()]


@router.post("/courses", status_code=201)
def create_course(payload: CourseInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not db.get(Department, payload.department_id):
        raise HTTPException(404, "Department not found")
    if payload.semester_id and not db.get(Semester, payload.semester_id):
        raise HTTPException(404, "Semester not found")
    values = payload.model_dump()
    if values["attendance_threshold"] is None:
        configured = db.get(AppSetting, "low_attendance_threshold")
        values["attendance_threshold"] = float(configured.value) if configured else settings.low_attendance_threshold
    values["course_code"] = payload.course_code.strip().upper()
    values["name"] = payload.name.strip()
    item = Course(**values)
    db.add(item)
    try:
        db.flush()
        audit(db, actor.id, "course.created", "course", item.id)
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Course code must be unique")
    return course_view(item)


@router.patch("/courses/{course_id}")
def patch_course(course_id: str, payload: CoursePatchInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    item = db.get(Course, course_id)
    if not item:
        raise HTTPException(404, "Course not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    audit(db, actor.id, "course.updated", "course", item.id, {"fields": sorted(changes)})
    db.commit()
    return course_view(item)


@router.get("/sections")
def list_sections(course_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(Section)
    if course_id:
        query = query.filter(Section.course_id == course_id)
    return [{"id": x.id, "course_id": x.course_id, "name": x.name} for x in query.order_by(Section.name).all()]


@router.post("/courses/{course_id}/sections", status_code=201)
def create_section(course_id: str, payload: SectionInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not db.get(Course, course_id):
        raise HTTPException(404, "Course not found")
    item = Section(course_id=course_id, name=payload.name.strip())
    db.add(item)
    try:
        db.flush()
        audit(db, actor.id, "section.created", "section", item.id)
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Section name must be unique in the course")
    return {"id": item.id, "course_id": item.course_id, "name": item.name}


@router.get("/students")
def list_students(q: str | None = None, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(Student, User).join(User, User.id == Student.user_id)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter((Student.student_number.ilike(pattern)) | (User.full_name.ilike(pattern)) | (User.email.ilike(pattern)))
    rows = query.order_by(Student.student_number).offset(offset).limit(limit).all()
    return {"items": [student_view(db, student, user) for student, user in rows], "limit": limit, "offset": offset}


@router.post("/students", status_code=201)
def create_student(payload: StudentInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not db.get(Department, payload.department_id):
        raise HTTPException(404, "Department not found")
    if payload.semester_id and not db.get(Semester, payload.semester_id):
        raise HTTPException(404, "Semester not found")
    try:
        user, token = _invite_user(db, payload.email, payload.full_name, "student", actor)
        student = Student(user_id=user.id, student_number=payload.student_number.strip(),
                          department_id=payload.department_id, program=payload.program.strip(), semester_id=payload.semester_id)
        db.add(student)
        db.flush()
        audit(db, actor.id, "student.created", "student", student.id, {"student_number": student.student_number})
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Email or student number is already registered")
    return {"id": student.id, "user_id": user.id, "student_number": student.student_number,
            "activation_token": token, "activation_path": f"/activate?token={token}", "expires_in_days": 7}


@router.patch("/students/{student_id}")
def update_student(student_id: str, payload: StudentUpdateInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    user = db.get(User, student.user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "department_id" in changes and changes["department_id"] and not db.get(Department, changes["department_id"]):
        raise HTTPException(404, "Department not found")
    if "semester_id" in changes and changes["semester_id"] and not db.get(Semester, changes["semester_id"]):
        raise HTTPException(404, "Semester not found")
    try:
        for key, value in changes.items():
            if key in {"email", "full_name"}:
                setattr(user, key, str(value).strip().lower() if key == "email" else value.strip())
            elif key == "student_number":
                student.student_number = value.strip()
            elif key == "program":
                student.program = value.strip()
            else:
                setattr(student, key, value)
        student.updated_at = utc_now()
        audit(db, actor.id, "student.updated", "student", student.id, {"fields": sorted(changes)})
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Email or student number is already registered")
    return student_view(db, student, user)


@router.get("/teachers")
def list_teachers(q: str | None = None, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(Teacher, User).join(User, User.id == Teacher.user_id)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter((Teacher.employee_number.ilike(pattern)) | (User.full_name.ilike(pattern)) | (User.email.ilike(pattern)))
    rows = query.order_by(Teacher.employee_number).offset(offset).limit(limit).all()
    return {"items": [teacher_view(teacher, user) for teacher, user in rows], "limit": limit, "offset": offset}


@router.post("/teachers", status_code=201)
def create_teacher(payload: TeacherInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not db.get(Department, payload.department_id):
        raise HTTPException(404, "Department not found")
    try:
        user, token = _invite_user(db, payload.email, payload.full_name, "teacher", actor)
        teacher = Teacher(user_id=user.id, employee_number=payload.employee_number.strip(), department_id=payload.department_id)
        db.add(teacher)
        db.flush()
        audit(db, actor.id, "teacher.created", "teacher", teacher.id, {"employee_number": teacher.employee_number})
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Email or employee number is already registered")
    return {"id": teacher.id, "user_id": user.id, "employee_number": teacher.employee_number,
            "activation_token": token, "activation_path": f"/activate?token={token}", "expires_in_days": 7}


@router.patch("/teachers/{teacher_id}")
def update_teacher(teacher_id: str, payload: TeacherUpdateInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(404, "Teacher not found")
    user = db.get(User, teacher.user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "department_id" in changes and changes["department_id"] and not db.get(Department, changes["department_id"]):
        raise HTTPException(404, "Department not found")
    try:
        for key, value in changes.items():
            if key in {"email", "full_name"}:
                setattr(user, key, str(value).strip().lower() if key == "email" else value.strip())
            elif key == "employee_number":
                teacher.employee_number = value.strip()
            else:
                setattr(teacher, key, value)
        audit(db, actor.id, "teacher.updated", "teacher", teacher.id, {"fields": sorted(changes)})
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Email or employee number is already registered")
    return teacher_view(teacher, user)


@router.post("/enrollments", status_code=201)
def create_enrollment(payload: EnrollmentInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    student, course = db.get(Student, payload.student_id), db.get(Course, payload.course_id)
    if not student or not course:
        raise HTTPException(404, "Student or course not found")
    if student.department_id != course.department_id:
        raise HTTPException(422, "Student and course must belong to the same department")
    if payload.section_id:
        section = db.get(Section, payload.section_id)
        if not section or section.course_id != course.id:
            raise HTTPException(422, "Section does not belong to this course")
    enrollment = Enrollment(student_id=student.id, course_id=course.id, section_id=payload.section_id)
    db.add(enrollment)
    try:
        db.flush()
        audit(db, actor.id, "student.enrolled", "enrollment", enrollment.id,
              {"student_id": student.id, "course_id": course.id, "section_id": payload.section_id})
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Student is already enrolled in this course")
    return {"id": enrollment.id, "student_id": enrollment.student_id, "course_id": enrollment.course_id,
            "section_id": enrollment.section_id, "active": enrollment.active}


@router.get("/enrollments")
def list_enrollments(course_id: str | None = None, student_id: str | None = None,
                     db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(Enrollment)
    if course_id:
        query = query.filter(Enrollment.course_id == course_id)
    if student_id:
        query = query.filter(Enrollment.student_id == student_id)
    return [{"id": x.id, "student_id": x.student_id, "course_id": x.course_id,
             "section_id": x.section_id, "active": x.active} for x in query.all()]


@router.post("/teacher-assignments", status_code=201)
def create_assignment(payload: AssignmentInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    teacher, course = db.get(Teacher, payload.teacher_id), db.get(Course, payload.course_id)
    if not teacher or not course:
        raise HTTPException(404, "Teacher or course not found")
    if teacher.department_id != course.department_id:
        raise HTTPException(422, "Teacher and course must belong to the same department")
    if payload.section_id:
        section = db.get(Section, payload.section_id)
        if not section or section.course_id != course.id:
            raise HTTPException(422, "Section does not belong to this course")
    item = TeacherAssignment(teacher_id=teacher.id, course_id=course.id, section_id=payload.section_id)
    db.add(item)
    try:
        db.flush()
        audit(db, actor.id, "teacher.assigned", "teacher_assignment", item.id,
              {"teacher_id": teacher.id, "course_id": course.id, "section_id": payload.section_id})
        db.commit()
    except IntegrityError:
        _handle_integrity(db, "Teacher is already assigned to this course and section")
    return {"id": item.id, "teacher_id": item.teacher_id, "course_id": item.course_id, "section_id": item.section_id}


@router.get("/teacher-assignments")
def list_assignments(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [{"id": x.id, "teacher_id": x.teacher_id, "course_id": x.course_id, "section_id": x.section_id}
            for x in db.query(TeacherAssignment).all()]


@router.get("/locations")
def list_locations(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return [location_view(x) for x in db.query(Location).order_by(Location.name).all()]


@router.post("/locations", status_code=201)
def create_location(payload: LocationInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not db.get(Department, payload.department_id):
        raise HTTPException(404, "Department not found")
    values = payload.model_dump()
    values["name"] = payload.name.strip()
    item = Location(**values)
    db.add(item)
    db.flush()
    audit(db, actor.id, "location.created", "location", item.id,
          {"department_id": item.department_id, "radius_m": item.radius_m, "max_accuracy_m": item.max_accuracy_m})
    db.commit()
    return location_view(item)


@router.patch("/locations/{location_id}")
def patch_location(location_id: str, payload: LocationInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    item = db.get(Location, location_id)
    if not item:
        raise HTTPException(404, "Location not found")
    if not db.get(Department, payload.department_id):
        raise HTTPException(404, "Department not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    audit(db, actor.id, "location.updated", "location", item.id,
          {"radius_m": item.radius_m, "max_accuracy_m": item.max_accuracy_m})
    db.commit()
    return location_view(item)


@router.get("/sessions")
def list_sessions(course_id: str | None = None, from_date: datetime | None = None, to_date: datetime | None = None,
                 limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(ClassSession)
    if course_id:
        query = query.filter(ClassSession.course_id == course_id)
    if from_date:
        query = query.filter(ClassSession.starts_at >= from_date)
    if to_date:
        query = query.filter(ClassSession.starts_at <= to_date)
    total = query.count()
    rows = query.order_by(ClassSession.starts_at.desc()).offset(offset).limit(limit).all()
    return {"items": [session_view(db, x) for x in rows], "limit": limit, "offset": offset, "total": total}


@router.post("/sessions", status_code=201)
def create_session(payload: SessionInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    course, location = db.get(Course, payload.course_id), db.get(Location, payload.location_id)
    if not course or not location:
        raise HTTPException(404, "Course or location not found")
    if course.department_id != location.department_id:
        raise HTTPException(422, "Classroom location must belong to the course department")
    if payload.section_id:
        section = db.get(Section, payload.section_id)
        if not section or section.course_id != course.id:
            raise HTTPException(422, "Section does not belong to this course")
    item = ClassSession(**payload.model_dump(), created_by=actor.id)
    db.add(item)
    db.flush()
    audit(db, actor.id, "session.created", "class_session", item.id,
          {"course_id": item.course_id, "starts_at": to_campus(item.starts_at).isoformat()})
    db.commit()
    return session_view(db, item)


@router.post("/sessions/{session_id}/cancel")
def cancel_session(session_id: str, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    item = db.get(ClassSession, session_id)
    if not item:
        raise HTTPException(404, "Session not found")
    if db.query(Attendance).filter(Attendance.session_id == item.id).count():
        raise HTTPException(409, "A session with recorded attendance cannot be cancelled; use an audited correction")
    item.cancelled = True
    audit(db, actor.id, "session.cancelled", "class_session", item.id)
    db.commit()
    return session_view(db, item)


@router.post("/sessions/{session_id}/finalize")
def finalize_session(session_id: str, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    item = db.get(ClassSession, session_id)
    if not item:
        raise HTTPException(404, "Session not found")
    if item.cancelled:
        raise HTTPException(409, "Cancelled sessions cannot be finalized")
    if as_utc(item.ends_at) + timedelta(minutes=item.grace_minutes) > utc_now():
        raise HTTPException(409, "Session grace period has not ended")
    if item.finalized_at:
        return {"session_id": item.id, "created_absences": 0, "already_finalized": True}
    query = db.query(Enrollment).filter(Enrollment.course_id == item.course_id, Enrollment.active.is_(True))
    if item.section_id:
        query = query.filter(Enrollment.section_id == item.section_id)
    enrollments = query.all()
    present_ids = {row.student_id for row in db.query(Attendance.student_id).filter(Attendance.session_id == item.id).all()}
    created = 0
    for enrollment in enrollments:
        if enrollment.student_id not in present_ids:
            db.add(Attendance(student_id=enrollment.student_id, session_id=item.id, status="absent", marked_at=utc_now(),
                              correction_reason="Automatically finalized after session close"))
            created += 1
    item.finalized_at = utc_now()
    audit(db, actor.id, "session.finalized", "class_session", item.id, {"created_absences": created})
    db.commit()
    return {"session_id": item.id, "created_absences": created, "already_finalized": False}


@router.get("/attendance")
def list_attendance(course_id: str | None = None, session_id: str | None = None, student_id: str | None = None,
                   state: Literal["present", "late", "absent", "excused"] | None = Query(None, alias="status"),
                   start: CampusRangeStart | None = None, end: CampusRangeEnd | None = None,
                   limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(Attendance, Student, User, ClassSession, Course).join(Student, Student.id == Attendance.student_id)
    query = query.join(User, User.id == Student.user_id).join(ClassSession, ClassSession.id == Attendance.session_id)
    query = query.join(Course, Course.id == ClassSession.course_id)
    if course_id:
        query = query.filter(Course.id == course_id)
    if session_id:
        query = query.filter(ClassSession.id == session_id)
    if student_id:
        query = query.filter(Student.id == student_id)
    if state:
        query = query.filter(Attendance.status == state)
    if start:
        query = query.filter(Attendance.marked_at >= start)
    if end:
        # Exclusive campus-time bound so that a bare `end=YYYY-MM-DD` includes 23:59 IST of that day.
        query = query.filter(Attendance.marked_at < end)
    total = query.count()
    rows = query.order_by(Attendance.marked_at.desc()).offset(offset).limit(limit).all()
    return {"items": [attendance_view(att, student, user, session, course) for att, student, user, session, course in rows],
            "total": total, "limit": limit, "offset": offset}


@router.post("/attendance/correct", status_code=201)
def manual_correction(payload: CorrectionInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    student, session = db.get(Student, payload.student_id), db.get(ClassSession, payload.session_id)
    if not student or not session:
        raise HTTPException(404, "Student or class session not found")
    if not db.query(Enrollment).filter(Enrollment.student_id == student.id, Enrollment.course_id == session.course_id,
                                        Enrollment.active.is_(True)).first():
        raise HTTPException(422, "Student is not enrolled in this course")
    existing = db.query(Attendance).filter(Attendance.student_id == student.id, Attendance.session_id == session.id).first()
    old_status = existing.status if existing else None
    if existing:
        existing.status = payload.status
        existing.correction_reason = payload.reason.strip()
        existing.updated_by = actor.id
        existing.updated_at = utc_now()
    else:
        existing = Attendance(student_id=student.id, session_id=session.id, status=payload.status,
                              marked_at=utc_now(), correction_reason=payload.reason.strip(), updated_by=actor.id)
        db.add(existing)
    audit(db, actor.id, "attendance.corrected", "attendance", existing.id,
          {"student_id": student.id, "session_id": session.id, "from": old_status, "to": payload.status,
           "reason": payload.reason.strip()})
    db.commit()
    return {"id": existing.id, "status": existing.status, "student_id": existing.student_id, "session_id": existing.session_id}


@router.get("/verification-attempts")
def list_verification_attempts(status_filter: str | None = Query(None, alias="status"),
                              limit: int = Query(100, ge=1, le=300), offset: int = Query(0, ge=0),
                              db: Session = Depends(get_db), _: User = Depends(admin_only)):
    query = db.query(VerificationAttempt)
    if status_filter:
        query = query.filter(VerificationAttempt.status == status_filter)
    return {"items": [{"id": x.id, "user_id": x.user_id, "session_id": x.session_id, "status": x.status,
                       "reason": x.reason, "distance_m": x.distance_m, "accuracy_m": x.reported_accuracy_m,
                       "created_at": to_campus(x.created_at),
                       "created_on_ist": campus_date(x.created_at)} for x in query.order_by(VerificationAttempt.created_at.desc()).offset(offset).limit(limit).all()]}


@router.get("/corrections")
def list_corrections(status_filter: str = Query("pending", alias="status"), db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = db.query(CorrectionRequest).filter(CorrectionRequest.status == status_filter).order_by(CorrectionRequest.created_at.desc()).limit(300).all()
    return [correction_view(db, row) for row in rows]


@router.post("/corrections/{request_id}/resolve")
def resolve_correction(request_id: str, payload: "CorrectionDecision", actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    item = db.get(CorrectionRequest, request_id)
    if not item:
        raise HTTPException(404, "Correction request not found")
    return resolve_correction(db, item, actor, payload.approved, payload.decision_reason)


class CorrectionDecision(BaseModel):
    approved: bool
    decision_reason: str = Field(min_length=3, max_length=1000)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    row = db.get(AppSetting, "low_attendance_threshold")
    return {"low_attendance_threshold": float(row.value) if row else 75.0,
            "campus_timezone": settings.campus_timezone,
            "campus_utc_offset": utc_offset_label()}


@router.put("/settings")
def update_settings(payload: GlobalSettingsInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    row = db.get(AppSetting, "low_attendance_threshold")
    if not row:
        row = AppSetting(key="low_attendance_threshold", value=str(payload.low_attendance_threshold), updated_by=actor.id)
        db.add(row)
    else:
        row.value = str(payload.low_attendance_threshold)
        row.updated_by = actor.id
    audit(db, actor.id, "settings.updated", "app_settings", "low_attendance_threshold",
          {"low_attendance_threshold": payload.low_attendance_threshold})
    db.commit()
    return {"low_attendance_threshold": payload.low_attendance_threshold}


@router.post("/users/{user_id}/password-reset")
def issue_password_reset(user_id: str, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(404, "Active user not found")
    token = secrets.token_urlsafe(36)
    user.activation_hash = opaque_hash(token)
    user.activation_expires_at = utc_now() + timedelta(hours=24)
    db.query(UserSession).filter_by(user_id=user.id).delete(synchronize_session=False)
    audit(db, actor.id, "user.password_reset_issued", "user", user.id)
    db.commit()
    return {"activation_token": token, "activation_path": f"/activate?token={token}", "expires_in_hours": 24}


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: str, payload: UserStatusInput, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == actor.id and not payload.active:
        raise HTTPException(422, "You cannot deactivate your own administrator account")
    user.active = payload.active
    audit(db, actor.id, "user.status_changed", "user", user.id, {"active": payload.active})
    db.commit()
    return {"id": user.id, "active": user.active}


@router.delete("/students/{student_id}/face-template", status_code=204)
def delete_face_template(student_id: str, actor: User = Depends(admin_only), db: Session = Depends(get_db)):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    profile = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    if profile:
        db.delete(profile)
        audit(db, actor.id, "face_template.deleted", "face_enrollment", profile.id, {"student_id": student.id})
        db.commit()
    return None


@router.get("/audit")
def list_audit(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()
    return [{"id": x.id, "actor_user_id": x.actor_user_id, "action": x.action, "entity_type": x.entity_type,
             "entity_id": x.entity_id, "details": x.details, "created_at": to_campus(x.created_at),
             "created_on_ist": campus_date(x.created_at)} for x in rows]


def course_view(course: Course) -> dict:
    return {"id": course.id, "department_id": course.department_id, "semester_id": course.semester_id,
            "course_code": course.course_code, "name": course.name, "description": course.description,
            "attendance_threshold": course.attendance_threshold, "active": course.active}


def student_view(db: Session, student: Student, user: User) -> dict:
    department = db.get(Department, student.department_id)
    face = db.query(FaceEnrollment).filter(FaceEnrollment.student_id == student.id).first()
    return {"id": student.id, "user_id": user.id, "student_number": student.student_number,
            "full_name": user.full_name, "email": user.email, "department_id": student.department_id,
            "department_name": department.name if department else None, "program": student.program,
            "semester_id": student.semester_id, "enrollment_status": student.enrollment_status,
            "active": user.active, "activated": user.password_hash is not None, "face_enrolled": face is not None}


def teacher_view(teacher: Teacher, user: User) -> dict:
    return {"id": teacher.id, "user_id": user.id, "employee_number": teacher.employee_number,
            "full_name": user.full_name, "email": user.email, "department_id": teacher.department_id,
            "active": user.active, "activated": user.password_hash is not None}


def location_view(location: Location) -> dict:
    return {"id": location.id, "department_id": location.department_id, "name": location.name,
            "latitude": location.latitude, "longitude": location.longitude, "radius_m": location.radius_m,
            "max_accuracy_m": location.max_accuracy_m, "active": location.active}


def session_view(db: Session, session: ClassSession) -> dict:
    course, location = db.get(Course, session.course_id), db.get(Location, session.location_id)
    return {"id": session.id, "course_id": session.course_id, "course_code": course.course_code if course else None,
            "course_name": course.name if course else None, "section_id": session.section_id,
            "location_id": session.location_id, "location_name": location.name if location else None,
            "title": session.title, "starts_at": to_campus(session.starts_at), "ends_at": to_campus(session.ends_at),
            "starts_on_ist": campus_date(session.starts_at), "grace_minutes": session.grace_minutes,
            "cancelled": session.cancelled, "finalized": session.finalized_at is not None}


def attendance_view(attendance: Attendance, student: Student, user: User, session: ClassSession, course: Course) -> dict:
    return {"id": attendance.id, "student_id": student.id, "student_number": student.student_number,
            "student_name": user.full_name, "session_id": session.id, "course_id": course.id,
            "course_code": course.course_code, "course_name": course.name, "status": attendance.status,
            "marked_at": to_campus(attendance.marked_at),
            "marked_on_ist": campus_date(attendance.marked_at), "reason": attendance.correction_reason,
            "updated_by": attendance.updated_by}


def correction_view(db: Session, item: CorrectionRequest) -> dict:
    student = db.get(Student, item.student_id)
    user = db.get(User, student.user_id) if student else None
    session = db.get(ClassSession, item.session_id)
    course = db.get(Course, session.course_id) if session else None
    submitter = db.get(User, item.submitted_by)
    return {"id": item.id, "student_id": item.student_id, "student_number": student.student_number if student else None,
            "student_name": user.full_name if user else None, "session_id": item.session_id,
            "course_name": course.name if course else None, "requested_status": item.requested_status,
            "reason": item.reason, "status": item.status, "submitted_by": submitter.full_name if submitter else None,
            "decision_reason": item.decision_reason, "created_at": to_campus(item.created_at)}
