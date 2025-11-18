# schemas.py (cuplikan)
from typing import Optional, List
from pydantic import BaseModel

class Filters(BaseModel):
    trans_choice: Optional[str] = None
    brand: Optional[str] = None
    fuels: Optional[List[str]] = None   

class RecommendRequest(BaseModel):
    budget: float
    topn: Optional[int] = 6
    needs: Optional[List[str]] = None   
    filters: Optional[Filters] = None
