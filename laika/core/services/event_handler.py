from watchdog.events import *
import threading
from queue import Queue
from pathlib import Path
from src.core.services import Database, Vectorizer
from src.core.models import File


class LaikaEventHandler(RegexMatchingEventHandler):
    def __init__(
            self,
            database: Database,
            vectorizer: Vectorizer,
            debounce_timers: dict[str, threading.Timer],
            queue: Queue[File],
            **kwargs
        ):
        super().__init__(**kwargs)

        self._ignore_directories = True
        self._ignore_regexes = [re.compile(pattern) for pattern in
            [
                r'.*/\..*', # Dotfiles
                r'.*/?[0-9]+', # Numeric files
                r'.*/?.*\.sw[p-x]', # Vim swap files
                r'.*?/?.*~', # Til files
            ]
        ]

        self.database = database
        self.vectorizer = vectorizer

        self.debounce_timers = debounce_timers
        self.queue = queue


    def __setup_folder(self) -> None:
        """
            When setup in an already existing folder,
            setup rows and embeddings for each file
        """
        ...


    def on_created(self, event) -> None:
        """
            On file creation, inserts metadata in database
            and checks content for embedding in vector database
        """
        print(f'ARQUIVO CRIADO: {event.src_path}')

        path = Path(event.src_path)     # type: ignore

        file = self.database.upsert_file(path)
        if file.hash is not None:
            self.__add_to_debouncer(path)

        return super().on_created(event)


    def on_moved(self, event) -> None:
        """
            When a file is moved, its path is updated in the database
            and in the timers hashmap, unless the destination
            is out of results in a removal of its metadata
        """
        print(f'ARQUIVO MOVIDO DE {event.src_path} PARA {event.dest_path}')

        source, destination = Path(event.src_path), Path(event.dest_path)   # type: ignore

        if not str(destination).startswith(os.getenv('MONITORING_FOLDER', '')):
            self.database.delete_file(source)
            del self.debounce_timers[str(source)]

            return super().on_moved(event)

        self.database.update_path(source, destination)

        # If old file name had a timer set up
        # updates it with the new path and a
        # reference to the timeout it left behind
        if self.debounce_timers.get(str(source)):
            self.__replace_path_at_bouncer(source, destination)

        return super().on_moved(event)


    def on_modified(self, event) -> None:
        print(f'ARQUIVO MODIFICADO: {event.src_path}')
        
        path = Path(event.src_path)     # type: ignore

        file = self.database.upsert_file(path)
        if file.hash is not None:
            self.__add_to_debouncer(path)

        return super().on_modified(event)
    

    def on_deleted(self, event) -> None:
        print(f'ARQUIVO DELETADO {event.src_path}')

        path = Path(event.src_path) # type: ignore
        if self.debounce_timers.get(str(path)):
            del self.debounce_timers[str(path)]

        file_id = self.database.delete_file(path)
        self.vectorizer.delete_vectors(file_id)

        return super().on_deleted(event)
    

    def __add_to_debouncer(self, path: Path | str) -> None:
        file_data = self.database.get_file_by_path(path)
        timer = threading.Timer(
            interval=15.0, function=self.queue.put, args=(file_data,)
        )

        self.debounce_timers[str(path)] = timer
        timer.start()


    def __replace_path_at_bouncer(self, source: Path | str, destination: Path | str) -> None:
        timer = self.debounce_timers[str(source)]
        del self.debounce_timers[str(source)]

        self.debounce_timers[str(destination)] = timer
        timer.start()
