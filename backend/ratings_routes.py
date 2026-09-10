"""Blind-rating API: collect demo votes, report blind tallies.

Stays blind by design: counts are X/Y/same only. Unblinding (X/Y -> A/B)
happens offline in scripts/tally_ratings.py via the gitignored key.
"""
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import config, ratings

router = APIRouter(prefix="/api/ratings")

STORE = ratings.RatingsStore(config.RATINGS_PATH)


class VoteRequest(BaseModel):
    rater: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=16)
    choice: Literal["X", "Y", "same"]


@router.post("/vote")
def vote(req: VoteRequest):
    try:
        return STORE.vote(req.rater, req.question, req.choice)
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})


@router.get("/tally")
def tally():
    return STORE.tally()


@router.post("/clear")
def clear():
    return {"cleared": STORE.clear()}
