from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from uuid import UUID
import enum


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class RelationshipType(str, enum.Enum):
    PARENT = "parent"
    CHILD = "child"
    SPOUSE = "spouse"
    SIBLING = "sibling"


class AccessLevel(str, enum.Enum):
    VIEW = "view"
    EDIT = "edit"


class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: str


class UserCreate(UserBase):
    password: str

    @validator("password")
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class FamilyTreeBase(BaseModel):
    name: str
    description: Optional[str] = None


class FamilyTreeCreate(FamilyTreeBase):
    pass


class FamilyTreeResponse(FamilyTreeBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    person_count: Optional[int] = None

    class Config:
        from_attributes = True


class PersonBase(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    birth_date: Optional[date] = None
    death_date: Optional[date] = None
    gender: Gender
    bio: Optional[str] = None

    class Config:
        use_enum_values = True


class PersonCreate(PersonBase):
    pass


class PersonUpdate(PersonBase):
    first_name: Optional[str] = None
    gender: Optional[Gender] = None

    class Config:
        use_enum_values = True


class PersonResponse(PersonBase):
    id: UUID
    tree_id: UUID
    photo_url: Optional[str] = None
    created_at: datetime
    relationships: List[Dict[str, Any]] = list()

    class Config:
        from_attributes = True
        use_enum_values = True


class RelationshipBase(BaseModel):
    person_id: UUID
    related_person_id: UUID
    relationship_type: RelationshipType

    class Config:
        use_enum_values = True


class RelationshipCreate(RelationshipBase):
    pass


class RelationshipResponse(RelationshipBase):
    id: UUID
    tree_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
        use_enum_values = True


class MediaFileBase(BaseModel):
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None


class MediaFileCreate(MediaFileBase):
    person_id: Optional[UUID] = None


class MediaFileResponse(MediaFileBase):
    id: UUID
    tree_id: UUID
    person_id: Optional[UUID]
    file_url: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class TreeShareBase(BaseModel):
    user_id: UUID
    access_level: AccessLevel

    class Config:
        use_enum_values = True


class TreeShareCreate(TreeShareBase):
    pass


class TreeShareResponse(TreeShareBase):
    id: UUID
    tree_id: UUID
    shared_by: UUID
    shared_at: datetime

    class Config:
        from_attributes = True
        use_enum_values = True


class PersonWithRelationships(PersonResponse):
    parents: List["PersonResponse"] = list()
    children: List["PersonResponse"] = list()
    spouses: List["PersonResponse"] = list()
    siblings: List["PersonResponse"] = list()


class FamilyTreeWithPersons(FamilyTreeResponse):
    persons: List[PersonWithRelationships] = list()


class UserWithTrees(UserResponse):
    family_trees: List[FamilyTreeResponse] = list()


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class TokenData(BaseModel):
    username: Optional[str] = None


class RelationshipInfo(BaseModel):
    relationship_type: RelationshipType
    related_person: "PersonResponse"


class PersonWithRelationships(PersonResponse):
    parents: List["PersonResponse"] = []
    children: List["PersonResponse"] = []
    spouses: List["PersonResponse"] = []
    siblings: List["PersonResponse"] = []


class TreeWithPersonsResponse(FamilyTreeResponse):
    persons: List[PersonWithRelationships] = []


RelationshipInfo.update_forward_refs()
PersonWithRelationships.update_forward_refs()
