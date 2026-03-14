from watchdog.observers import Observer
from dotenv import load_dotenv
import os, threading
from queue import Queue, Empty
from services.database import Database
from services.vectorizer import Vectorizer
from services.event_handler import LaikaEventHandler
from services.models import File

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
    database = Database()
    vectorizer = Vectorizer()

    # Watchdog implementation
    observer = Observer()
    handler = LaikaEventHandler(
        database=database,
        vectorizer=vectorizer,
        debounce_timers=debounce_timers,
        queue=queue
    )

    observer.schedule(handler, os.getenv('MONITORED_FOLDER', '/notes/'))
    observer.start()

    # Thread for consuming the debouncing queue
    stop_event = threading.Event()
    queue_thread = threading.Thread(
        target=consume_queue,
        args=(queue, vectorizer, stop_event,),
        daemon=True
    )
    queue_thread.start()

    # Forced stop
    while True:
        if input() == 'q': break

    stop_event.set()

    observer.stop()
    observer.join()

    queue_thread.join()


if __name__ == '__main__':
    main()
