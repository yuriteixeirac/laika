from textual.containers import Horizontal
from textual.widgets import Input, Button
from textual.widget import Widget
from textual.message import Message
from textual import on
from typing import Iterable
from laika.core.services import Vectorizer


class SearchBar(Widget):
    class Results(Message):
        def __init__(self, ids: list[int]) -> None:
            self.ids = ids
            super().__init__()


    def __init__(self, vectorizer: Vectorizer, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.vectorizer = vectorizer


    def compose(self) -> Iterable[Widget]:
        yield Horizontal(
            Input(placeholder='Insert your query here.', id='search-input'),
            Button(id='search-button', label='SEARCH')
        )


    @on(Button.Pressed, '#search-button')
    def gather_documents(self) -> None:
        query = self.query_one('#search-input').value # type: ignore
        ids, _ = self.vectorizer.query_files(query)
        
        self.post_message(self.Results(ids))
