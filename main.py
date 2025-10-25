from fastapi import FastAPI, Depends, HTTPException, status, Query
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
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


@app.get("/trees", response_model=List[FamilyTreeResponse])
async def get_user_trees(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FamilyTree).where(FamilyTree.user_id == current_user.id)
    )
    trees = result.scalars().all()

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


@app.get("/trees/{tree_id}/persons", response_model=List[PersonResponse])
async def get_tree_persons(
    tree_id: UUID,
    include_relationships: bool = Query(
        False, description="Включить базовую информацию о связях"
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить всех людей в дереве (опционально с базовой информацией о связях)"""

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

    person_responses = []
    for person in persons:
        person_data = PersonResponse.from_orm(person)

        if include_relationships:
            relationships_count = await db.execute(
                select(func.count(Relationship.id)).where(
                    Relationship.person_id == person.id
                )
            )
            person_data.relationships = [{"count": relationships_count.scalar()}]

        person_responses.append(person_data)

    return person_responses


@app.post("/trees/{tree_id}/persons", response_model=PersonResponse)
async def create_person(
    tree_id: UUID,
    person_data: PersonCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
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


@app.get("/trees/{tree_id}/full", response_model=TreeWithPersonsResponse)
async def get_full_tree(
    tree_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить полное дерево со всеми людьми и их связями"""
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

    tree_data = FamilyTreeResponse.from_orm(tree)

    persons_with_relationships = await get_tree_persons_with_relationships(
        tree_id, current_user, db
    )

    return TreeWithPersonsResponse(
        **tree_data.dict(), persons=persons_with_relationships
    )


@app.post("/trees/{tree_id}/relationships", response_model=RelationshipResponse)
async def create_relationship(
    tree_id: UUID,
    relationship_data: RelationshipCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
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


@app.post(
    "/trees/{tree_id}/relationships/batch", response_model=List[RelationshipResponse]
)
async def create_relationships_batch(
    tree_id: UUID,
    relationships_data: List[RelationshipCreate],
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать несколько связей за один запрос"""
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

    created_relationships = []

    for rel_data in relationships_data:
        person_result = await db.execute(
            select(Person).where(
                (Person.id == rel_data.person_id) & (Person.tree_id == tree_id)
            )
        )
        related_person_result = await db.execute(
            select(Person).where(
                (Person.id == rel_data.related_person_id) & (Person.tree_id == tree_id)
            )
        )

        if (
            not person_result.scalar_one_or_none()
            or not related_person_result.scalar_one_or_none()
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"One or both persons not found in this tree: {rel_data.person_id}, {rel_data.related_person_id}",
            )

        relationship = Relationship(tree_id=tree_id, **rel_data.dict())

        db.add(relationship)
        created_relationships.append(relationship)

    await db.commit()

    for rel in created_relationships:
        await db.refresh(rel)

    return [RelationshipResponse.from_orm(rel) for rel in created_relationships]


@app.get(
    "/trees/{tree_id}/persons-with-relationships",
    response_model=List[PersonWithRelationships],
)
async def get_tree_persons_with_relationships(
    tree_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить всех людей в дереве с их связями"""
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

    result = await db.execute(
        select(Relationship).where(Relationship.tree_id == tree_id)
    )
    relationships = result.scalars().all()

    persons_dict = {
        person.id: PersonWithRelationships.from_orm(person) for person in persons
    }

    for person in persons_dict.values():
        person.parents = []
        person.children = []
        person.spouses = []
        person.siblings = []

    for rel in relationships:
        person = persons_dict.get(rel.person_id)
        related_person = persons_dict.get(rel.related_person_id)

        if person and related_person:
            if rel.relationship_type == RelationshipType.PARENT:
                person.children.append(related_person)
            elif rel.relationship_type == RelationshipType.CHILD:
                person.parents.append(related_person)
            elif rel.relationship_type == RelationshipType.SPOUSE:
                person.spouses.append(related_person)
            elif rel.relationship_type == RelationshipType.SIBLING:
                person.siblings.append(related_person)

    return list(persons_dict.values())


@app.get(
    "/persons/{person_id}/relationships", response_model=Dict[str, List[PersonResponse]]
)
async def get_person_relationships(
    person_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Получить все связи конкретного человека"""
    result = await db.execute(
        select(Person)
        .join(FamilyTree)
        .where((Person.id == person_id) & (FamilyTree.user_id == current_user.id))
    )
    person = result.scalar_one_or_none()

    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person not found or access denied",
        )

    result = await db.execute(
        select(Relationship, Person)
        .join(Person, Relationship.related_person_id == Person.id)
        .where(Relationship.person_id == person_id)
    )
    relationships_data = result.all()

    relationships = {"parents": [], "children": [], "spouses": [], "siblings": []}

    for rel, related_person in relationships_data:
        if rel.relationship_type == RelationshipType.PARENT:
            relationships["parents"].append(PersonResponse.from_orm(related_person))
        elif rel.relationship_type == RelationshipType.CHILD:
            relationships["children"].append(PersonResponse.from_orm(related_person))
        elif rel.relationship_type == RelationshipType.SPOUSE:
            relationships["spouses"].append(PersonResponse.from_orm(related_person))
        elif rel.relationship_type == RelationshipType.SIBLING:
            relationships["siblings"].append(PersonResponse.from_orm(related_person))

    return relationships


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
