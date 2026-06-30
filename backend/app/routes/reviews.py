"""Per-document review/accept + dashboard stats."""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import document_store, review_store

router = APIRouter(tags=["reviews"])

Category = Literal["tables", "text", "pii", "layout"]


class AcceptRequest(BaseModel):
    document_id: str
    page_index: int
    solution: str
    run_id: str


@router.post("/reviews/accept")
def accept(req: AcceptRequest):
    try:
        meta = document_store.get_document_meta(req.document_id)
    except FileNotFoundError:
        raise HTTPException(404, f"document not found: {req.document_id}")
    rec = review_store.accept_page(
        document_id=req.document_id,
        filename=meta["filename"],
        page_index=req.page_index,
        solution=req.solution,
        run_id=req.run_id,
    )
    return rec


class RevokeRequest(BaseModel):
    document_id: str
    page_index: int


@router.post("/reviews/revoke")
def revoke(req: RevokeRequest):
    rec = review_store.revoke_page(document_id=req.document_id, page_index=req.page_index)
    if rec is None:
        raise HTTPException(404, f"no review for {req.document_id}")
    return rec


class AcceptCategoryRequest(BaseModel):
    document_id: str
    page_index: int
    category: Category
    solution: str
    run_id: str
    order: Optional[int] = None
    comment: str = ""


@router.post("/reviews/accept-category")
def accept_category(req: AcceptCategoryRequest):
    try:
        meta = document_store.get_document_meta(req.document_id)
    except FileNotFoundError:
        raise HTTPException(404, f"document not found: {req.document_id}")
    return review_store.accept_category(
        document_id=req.document_id,
        filename=meta["filename"],
        page_index=req.page_index,
        category=req.category,
        solution=req.solution,
        run_id=req.run_id,
        order=req.order,
        comment=req.comment,
    )


class ReorderCategoryRequest(BaseModel):
    document_id: str
    page_index: int
    category: Category
    ordered_solutions: List[str]


@router.post("/reviews/reorder-category")
def reorder_category(req: ReorderCategoryRequest):
    rec = review_store.reorder_category(
        document_id=req.document_id,
        page_index=req.page_index,
        category=req.category,
        ordered_solutions=req.ordered_solutions,
    )
    if rec is None:
        raise HTTPException(404, f"no review for {req.document_id}")
    return rec


class CommentCategoryRequest(BaseModel):
    document_id: str
    page_index: int
    category: Category
    solution: str
    comment: str


@router.post("/reviews/comment-category")
def comment_category(req: CommentCategoryRequest):
    rec = review_store.comment_category(
        document_id=req.document_id,
        page_index=req.page_index,
        category=req.category,
        solution=req.solution,
        comment=req.comment,
    )
    if rec is None:
        raise HTTPException(404, f"no review for {req.document_id} (or solution not accepted)")
    return rec


class RevokeCategoryRequest(BaseModel):
    document_id: str
    page_index: int
    category: Category
    solution: Optional[str] = None


@router.post("/reviews/revoke-category")
def revoke_category(req: RevokeCategoryRequest):
    rec = review_store.revoke_category(
        document_id=req.document_id,
        page_index=req.page_index,
        category=req.category,
        solution=req.solution,
    )
    if rec is None:
        raise HTTPException(404, f"no review for {req.document_id}")
    return rec


class RejectCategoryRequest(BaseModel):
    document_id: str
    filename: str = ""
    page_index: int
    category: Category
    solution: str
    run_id: str
    reason: str = ""


class UnrejectCategoryRequest(BaseModel):
    document_id: str
    page_index: int
    category: Category
    solution: str


@router.post("/reviews/reject-category")
def reject_category(req: RejectCategoryRequest):
    return review_store.reject_category(
        document_id=req.document_id,
        filename=req.filename,
        page_index=req.page_index,
        category=req.category,
        solution=req.solution,
        run_id=req.run_id,
        reason=req.reason,
    )


@router.post("/reviews/unreject-category")
def unreject_category(req: UnrejectCategoryRequest):
    rec = review_store.unreject_category(
        document_id=req.document_id,
        page_index=req.page_index,
        category=req.category,
        solution=req.solution,
    )
    if rec is None:
        raise HTTPException(404, f"no review for {req.document_id}")
    return rec


# Specific sub-paths first (path-converter is greedy)


@router.get("/reviews/composite/{document_id:path}")
def get_composite(document_id: str):
    return review_store.compose(document_id)


@router.get("/reviews/{document_id:path}")
def get_review(document_id: str):
    rec = review_store.load(document_id)
    if rec is None:
        return {"document_id": document_id, "pages": {}}
    return rec


@router.get("/reviews")
def list_all():
    return {"reviews": review_store.list_reviews()}


@router.get("/stats")
def stats():
    return review_store.stats()
