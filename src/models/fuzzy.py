from pydantic import BaseModel


class FuzzySearchResult(BaseModel):
    indentifier: str
    text: str
    score: float
    match_type: str
