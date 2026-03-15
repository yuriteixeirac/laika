import chromadb
from laika.core.models import File
from laika.core.utils import LaikaEmbeddingFunction

class Vectorizer:
    def __init__(self) -> None:
        self.__client = chromadb.HttpClient()
        self.__collection = self.__client.get_or_create_collection(
            'files', embedding_function=LaikaEmbeddingFunction()
        )


    def embed_document(self, file_metadata: File):
        with open(file_metadata.path, 'r') as f:
            content = f.read()

        self.__collection.upsert(
            ids=[str(file_metadata.id)], documents=[content]
        )
    

    def query_files(self, query: str) -> tuple[list[int], list[str]]:
        results = self.__collection.query(
            query_texts=[query],
            include=['documents']
        )

        return results['ids'][0], results['documents'][0] # type: ignore


    def delete_vectors(self, id: int) -> None:
        self.__collection.delete(ids=[str(id)])
    