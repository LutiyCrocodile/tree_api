import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Text,
    Date,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Integer,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class GenderEnum(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class RelationshipTypeEnum(str, enum.Enum):
    PARENT = "parent"
    CHILD = "child"
    SPOUSE = "spouse"
    SIBLING = "sibling"


class AccessLevelEnum(str, enum.Enum):
    VIEW = "view"
    EDIT = "edit"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    family_trees = relationship(
        "FamilyTree", back_populates="user", cascade="all, delete-orphan"
    )
    shared_trees = relationship(
        "TreeShare", foreign_keys="TreeShare.user_id", back_populates="user"
    )
    given_shares = relationship(
        "TreeShare", foreign_keys="TreeShare.shared_by", back_populates="sharer"
    )


class FamilyTree(Base):
    __tablename__ = "family_trees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="family_trees")
    persons = relationship(
        "Person", back_populates="tree", cascade="all, delete-orphan"
    )
    relationships = relationship(
        "Relationship", back_populates="tree", cascade="all, delete-orphan"
    )
    media_files = relationship(
        "MediaFile", back_populates="tree", cascade="all, delete-orphan"
    )
    shares = relationship(
        "TreeShare", back_populates="tree", cascade="all, delete-orphan"
    )


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tree_id = Column(
        UUID(as_uuid=True),
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50))
    middle_name = Column(String(50))
    birth_date = Column(Date)
    death_date = Column(Date)
    gender = Column(SQLEnum(GenderEnum), nullable=False)
    photo_url = Column(String(500))
    bio = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tree = relationship("FamilyTree", back_populates="persons")

    relationships_as_person = relationship(
        "Relationship",
        foreign_keys="Relationship.person_id",
        back_populates="person",
        cascade="all, delete-orphan",
    )

    relationships_as_related = relationship(
        "Relationship",
        foreign_keys="Relationship.related_person_id",
        back_populates="related_person",
        cascade="all, delete-orphan",
    )

    media_files = relationship(
        "MediaFile", back_populates="person", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "death_date IS NULL OR death_date >= birth_date",
            name="check_dates_validity",
        ),
    )


class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tree_id = Column(
        UUID(as_uuid=True),
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    related_person_id = Column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type = Column(SQLEnum(RelationshipTypeEnum), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tree = relationship("FamilyTree", back_populates="relationships")
    person = relationship(
        "Person", foreign_keys=[person_id], back_populates="relationships_as_person"
    )
    related_person = relationship(
        "Person",
        foreign_keys=[related_person_id],
        back_populates="relationships_as_related",
    )

    __table_args__ = (
        CheckConstraint(
            "person_id != related_person_id", name="check_no_self_relationship"
        ),
    )


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tree_id = Column(
        UUID(as_uuid=True),
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("persons.id", ondelete="SET NULL")
    )
    file_url = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    tree = relationship("FamilyTree", back_populates="media_files")
    person = relationship("Person", back_populates="media_files")


class TreeShare(Base):
    __tablename__ = "tree_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tree_id = Column(
        UUID(as_uuid=True),
        ForeignKey("family_trees.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    shared_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    access_level = Column(SQLEnum(AccessLevelEnum), default=AccessLevelEnum.VIEW)
    shared_at = Column(DateTime(timezone=True), server_default=func.now())

    tree = relationship("FamilyTree", back_populates="shares")
    user = relationship("User", foreign_keys=[user_id], back_populates="shared_trees")
    sharer = relationship(
        "User", foreign_keys=[shared_by], back_populates="given_shares"
    )

    __table_args__ = (
        CheckConstraint("user_id != shared_by", name="check_no_self_share"),
    )
