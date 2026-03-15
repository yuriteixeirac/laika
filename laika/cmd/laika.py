from textual.app import App
from textual.widgets import ListView, Markdown
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from pathlib import Path
from typing import Iterable
from laika.cmd.widgets import SearchBar, FileCard
from laika.core.services import Vectorizer, Database


class LaikaApp(App):
    def __init__(self, database: Database, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__database = database
        self.__cards = []


    CSS_PATH = 'style/laika.tcss'


    def compose(self) -> Iterable:
        self.theme = 'catppuccin-mocha'

        yield SearchBar(
            vectorizer=Vectorizer()
        )

        # Standard view
        with open('README.md', 'r') as f:
            content = f.read()

        self.markdown_display = Markdown(content)
        yield Horizontal(
            ListView(*self.__cards),
            VerticalScroll(
                self.markdown_display
            ),
            id='main-view',
        )
    

    def on_search_bar_results(self, message: Message):
        list_view = self.query_one(ListView)
        list_view.clear()

        for id in message.ids: # type: ignore
            file = self.__database.get_file_by_id(id)
            list_view.mount(
                FileCard(
                    path=file.path, last_updated=file.last_updated
                )
            )
    
    
    def on_list_view_selected(self, message):
        path = message.item.path
        with open(path, 'r') as f:
            self.markdown_display.update(f.read())


def main() -> None:
    BASE_DIR = Path().resolve()
    app = LaikaApp(
        database=Database(
            BASE_DIR / 'laika/core/data/sqlite3.db'
        )
    )

    app.run()
