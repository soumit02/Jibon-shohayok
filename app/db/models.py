from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary,
                        String, Text, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserProfile(Base):
    """Long-term memory: facts the assistant should remember about the user."""
    __tablename__ = "user_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    family_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. salaried / business
    preferences: Mapped[str] = mapped_column(Text, default="{}")               # JSON text
    memory_summary: Mapped[str] = mapped_column(Text, default="")              # short summary passed to the LLM


class Document(Base):
    """Structured fields extracted from an uploaded file (+ the original file)."""
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))        # passport / driving_license / nid / insurance / bill / other
    title: Mapped[str] = mapped_column(String(160))
    holder_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    doc_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(80))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)    # small files only (limit upload size in the API)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # user verified the extracted values
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="in_app")   # in_app / email
    status: Mapped[str] = mapped_column(String(20), default="pending")   # pending / sent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedPlan(Base):
    __tablename__ = "saved_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    request_text: Mapped[str] = mapped_column(Text)
    plan_text: Mapped[str] = mapped_column(Text)
    estimated_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))             # user / assistant
    content: Mapped[str] = mapped_column(Text)
    crew: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TravelCost(Base):
    """Hand-maintained cost table used by the Trip Planner / Budget Estimator (never the LLM's memory)."""
    __tablename__ = "travel_costs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route: Mapped[str] = mapped_column(String(120), index=True)   # e.g. Dhaka-Sylhet
    mode: Mapped[str] = mapped_column(String(40))                 # bus / train / launch / hotel / food
    cost_bdt: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
