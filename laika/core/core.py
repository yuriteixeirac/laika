from watchdog.observers import Observer
from dotenv import load_dotenv
from queue import Queue, Empty
import os, threading
from laika.core.services.database import Database
from laika.core.services.vectorizer import Vectorizer
from laika.core.services.event_handler import LaikaEventHandler
from laika.core.models import File
from pathlib import Path

load_dotenv()


def consume_queue(queue: Queue[File], vec: Vectorizer, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            file_data = queue.get(timeout=1)
            vec.embed_document(file_data)
        except Empty:
            continue


def main() -> None:
    # Debouncing logic for embedding
    queue: Queue[File] = Queue()
    debounce_timers: dict[str, threading.Timer] = {}

    # Database classes
    ROOT = Path().resolve()

    database = Database(ROOT / 'laika/core/data' / 'sqlite3.db')
    vectorizer = Vectorizer()

    # Watchdog implementation
    observer = Observer()
    handler = LaikaEventHandler(
        database=database,
        vectorizer=vectorizer,
        debounce_timers=debounce_timers,
        queue=queue
    )

    print(ROOT / 'notes')
    observer.schedule(handler, os.getenv('MONITORED_FOLDER', ROOT / 'notes/'), recursive=True) # type: ignore
    observer.start()

    # Thread for consuming the debouncing queue
    stop_event = threading.Event()
    queue_thread = threading.Thread(
        target=consume_queue,
        args=(queue, vectorizer, stop_event,),
        daemon=True
    )
    queue_thread.start()

    print('APPLICATION STARTUP FINISHED.')

    # Forced stop
    while True:
        if input() == 'q': break

    stop_event.set()

    observer.stop()
    observer.join()

    queue_thread.join()


if __name__ == '__main__':
    main()
