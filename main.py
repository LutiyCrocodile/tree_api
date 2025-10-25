# main.py
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
import uuid

from database import get_db, create_tables

from auth import (
    get_current_active_user,
    authenticate_user,
    create_access_token,
    get_password_hash,
)
from models import User, FamilyTree, Person, Relationship, MediaFile, TreeShare
from schemas import *


async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Family Tree API", version="1.0.0", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#
# @app.on_event("startup")
# async def startup_event():
#     await create_tables()


# Auth endpoints
@app.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Проверка существующего пользователя
    result = await db.execute(
        select(User).where(
            (User.username == user_data.username) | (User.email == user_data.email)
        )
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )

    # Создание пользователя
    hashed_password = get_password_hash(user_data.password)
    user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Создание токена
    access_token = create_access_token(data={"sub": user.username})

    return Token(
        access_token=access_token, token_type="bearer", user=UserResponse.from_orm(user)
    )


@app.post("/auth/login", response_model=Token)
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub": user.username})

    return Token(
        access_token=access_token, token_type="bearer", user=UserResponse.from_orm(user)
    )


# Family Tree endpoints
@app.get("/trees", response_model=List[FamilyTreeResponse])
async def get_user_trees(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FamilyTree).where(FamilyTree.user_id == current_user.id)
    )
    trees = result.scalars().all()

    # Добавляем количество людей в каждом дереве
    trees_with_count = []
    for tree in trees:
        person_count_result = await db.execute(
            select(func.count(Person.id)).where(Person.tree_id == tree.id)
        )
        person_count = person_count_result.scalar()

        tree_data = FamilyTreeResponse.from_orm(tree)
        tree_data.person_count = person_count
        trees_with_count.append(tree_data)

    return trees_with_count


@app.post("/trees", response_model=FamilyTreeResponse)
async def create_tree(
    tree_data: FamilyTreeCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    tree = FamilyTree(
        user_id=current_user.id, name=tree_data.name, description=tree_data.description
    )

    db.add(tree)
    await db.commit()
    await db.refresh(tree)

    return FamilyTreeResponse.from_orm(tree)


# Person endpoints
@app.get("/trees/{tree_id}/persons", response_model=List[PersonResponse])
async def get_tree_persons(
    tree_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Проверка прав доступа к дереву
    result = await db.execute(
        select(FamilyTree).where(
            (FamilyTree.id == tree_id) & (FamilyTree.user_id == current_user.id)
        )
    )
    tree = result.scalar_one_or_none()

    if not tree:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tree not found or access denied",
        )

    result = await db.execute(select(Person).where(Person.tree_id == tree_id))
    persons = result.scalars().all()

    return [PersonResponse.from_orm(person) for person in persons]


@app.post("/trees/{tree_id}/persons", response_model=PersonResponse)
async def create_person(
    tree_id: UUID,
    person_data: PersonCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Проверка прав доступа к дереву
    result = await db.execute(
        select(FamilyTree).where(
            (FamilyTree.id == tree_id) & (FamilyTree.user_id == current_user.id)
        )
    )
    tree = result.scalar_one_or_none()

    if not tree:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tree not found or access denied",
        )

    person = Person(tree_id=tree_id, **person_data.dict())

    db.add(person)
    await db.commit()
    await db.refresh(person)

    return PersonResponse.from_orm(person)


# Relationship endpoints
@app.post("/trees/{tree_id}/relationships", response_model=RelationshipResponse)
async def create_relationship(
    tree_id: UUID,
    relationship_data: RelationshipCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Проверка прав доступа и существования людей
    result = await db.execute(
        select(FamilyTree).where(
            (FamilyTree.id == tree_id) & (FamilyTree.user_id == current_user.id)
        )
    )
    tree = result.scalar_one_or_none()

    if not tree:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tree not found or access denied",
        )

    # Проверка что оба человека существуют в этом дереве
    person_result = await db.execute(
        select(Person).where(
            (Person.id == relationship_data.person_id) & (Person.tree_id == tree_id)
        )
    )
    related_person_result = await db.execute(
        select(Person).where(
            (Person.id == relationship_data.related_person_id)
            & (Person.tree_id == tree_id)
        )
    )

    if (
        not person_result.scalar_one_or_none()
        or not related_person_result.scalar_one_or_none()
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both persons not found in this tree",
        )

    relationship = Relationship(tree_id=tree_id, **relationship_data.dict())

    db.add(relationship)
    await db.commit()
    await db.refresh(relationship)

    return RelationshipResponse.from_orm(relationship)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
