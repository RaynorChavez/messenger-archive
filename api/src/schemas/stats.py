from pydantic import BaseModel
from datetime import date
from typing import List


class ActivityDataPoint(BaseModel):
    """Single data point for activity graph."""
    date: date
    count: int


class StatsResponse(BaseModel):
    """Dashboard statistics."""
    total_messages: int
    total_threads: int
    total_people: int
    activity: List[ActivityDataPoint]
