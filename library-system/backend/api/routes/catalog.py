from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import staff_required
from database.session import get_db
from models.library import Author, Branch, Category, Publisher
from models.user import User
from schemas.book import (
    AuthorCreate,
    AuthorOut,
    BranchCreate,
    BranchOut,
    CategoryCreate,
    CategoryOut,
    PublisherCreate,
    PublisherOut,
)

router = APIRouter(prefix="/catalog", tags=["Catalog reference data"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)).all())


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    payload: CategoryCreate,
    _: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Category:
    if db.scalar(select(Category).where(Category.name == payload.name)):
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/authors", response_model=list[AuthorOut])
def list_authors(db: Session = Depends(get_db)) -> list[Author]:
    return list(db.scalars(select(Author).order_by(Author.name)).all())


@router.post(
    "/authors", response_model=AuthorOut, status_code=status.HTTP_201_CREATED
)
def create_author(
    payload: AuthorCreate,
    _: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Author:
    author = Author(**payload.model_dump())
    db.add(author)
    db.commit()
    db.refresh(author)
    return author


@router.get("/publishers", response_model=list[PublisherOut])
def list_publishers(db: Session = Depends(get_db)) -> list[Publisher]:
    return list(db.scalars(select(Publisher).order_by(Publisher.name)).all())


@router.post(
    "/publishers", response_model=PublisherOut, status_code=status.HTTP_201_CREATED
)
def create_publisher(
    payload: PublisherCreate,
    _: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Publisher:
    if db.scalar(select(Publisher).where(Publisher.name == payload.name)):
        raise HTTPException(status_code=409, detail="Publisher already exists")
    publisher = Publisher(**payload.model_dump())
    db.add(publisher)
    db.commit()
    db.refresh(publisher)
    return publisher


@router.get("/branches", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)) -> list[Branch]:
    return list(db.scalars(select(Branch).order_by(Branch.name)).all())


@router.post(
    "/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED
)
def create_branch(
    payload: BranchCreate,
    _: User = Depends(staff_required),
    db: Session = Depends(get_db),
) -> Branch:
    branch = Branch(**payload.model_dump())
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch
