from textual.widget import Widget
from textual.widgets import ListItem, Label
from textual.containers import Vertical
from textual.message import Message
from typing import Iterable
from datetime import date
from laika.core.models import File


class FileCard(ListItem):
    def __init__(self, path: str, last_updated: date, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.path = path
        self.last_updated = last_updated
        self.classes = 'file-card'

    
    def compose(self) -> Iterable[Widget]:
        yield Vertical(
            Label(self.path),
            Label(str(self.last_updated)),
        )
