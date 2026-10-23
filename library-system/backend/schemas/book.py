from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.library import BookFormat, CopyStatus


# ------------------------- Reference data ---------------------------------
class AuthorBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    bio: Optional[str] = None
    photo_url: Optional[str] = None


class AuthorCreate(AuthorBase):
    pass


class AuthorOut(AuthorBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = None
    color: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PublisherBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website: Optional[str] = None


class PublisherCreate(PublisherBase):
    pass


class PublisherOut(PublisherBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BranchBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    opening_hours: Optional[dict] = None


class BranchCreate(BranchBase):
    pass


class BranchOut(BranchBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool


# ------------------------------ Books -------------------------------------
class BookBase(BaseModel):
    isbn: Optional[str] = Field(default=None, max_length=20)
    title: str = Field(min_length=1, max_length=500)
    subtitle: Optional[str] = None
    description: Optional[str] = None
    author_id: Optional[int] = None
    publisher_id: Optional[int] = None
    category_id: Optional[int] = None
    publication_year: Optional[int] = Field(default=None, ge=1000, le=2100)
    language: str = "English"
    cover_image_url: Optional[str] = None
    book_format: BookFormat = BookFormat.HARDCOVER
    total_copies: int = Field(default=1, ge=0)
    available_copies: Optional[int] = Field(default=None, ge=0)
    price: float = Field(default=0, ge=0)
    replacement_cost: float = Field(default=25, ge=0)
    digital_file_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    isbn: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    author_id: Optional[int] = None
    publisher_id: Optional[int] = None
    category_id: Optional[int] = None
    publication_year: Optional[int] = None
    language: Optional[str] = None
    cover_image_url: Optional[str] = None
    book_format: Optional[BookFormat] = None
    total_copies: Optional[int] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    replacement_cost: Optional[float] = Field(default=None, ge=0)
    digital_file_url: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class BookOut(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    available_copies: int
    average_rating: float
    review_count: int
    is_active: bool
    created_at: datetime
    author: Optional[AuthorOut] = None
    publisher: Optional[PublisherOut] = None
    category: Optional[CategoryOut] = None


class BookListOut(BaseModel):
    items: List[BookOut]
    total: int
    page: int
    page_size: int
    pages: int


class CatalogSuggestionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    author_name: Optional[str] = Field(default=None, max_length=255)
    isbn: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = None


class CatalogSuggestionOut(BaseModel):
    category_id: Optional[int] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: str
    book_format: BookFormat = BookFormat.HARDCOVER
    confidence: int
    rationale: str


# --------------------------- Book copies ----------------------------------
class BookCopyCreate(BaseModel):
    barcode: Optional[str] = None
    branch_id: Optional[int] = None
    condition: str = "good"
    shelf_location: Optional[str] = None
    acquired_date: Optional[date] = None


class BookCopyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    branch_id: Optional[int] = None
    barcode: str
    status: CopyStatus
    condition: str
    shelf_location: Optional[str] = None
    acquired_date: Optional[date] = None


# ------------------------------ Reviews -----------------------------------
class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book_id: int
    member_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    member_name: Optional[str] = None
