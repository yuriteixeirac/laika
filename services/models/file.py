from dataclasses import dataclass
from datetime import datetime
from typing import Tuple, Any, Self

@dataclass
class File:
    path: str
    hash: str | None
    id: int | None = None
    last_updated: datetime = datetime.now()
    created_at: datetime = datetime.now()


    def was_changed(self, outer_hash: str) -> bool:
        return outer_hash == self.hash
    

    @staticmethod
    def make_from(row: Tuple[int, str, str, datetime, datetime]):
        return File(
            id=row[0], 
            path=row[1],
            hash=row[2],
            created_at=row[3],
            last_updated=row[4]
        )
