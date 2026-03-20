from chromadb.utils.embedding_functions import register_embedding_function
from chromadb import EmbeddingFunction, Embeddings, Documents
from sentence_transformers import SentenceTransformer
import os, dotenv

dotenv.load_dotenv()


@register_embedding_function
class LaikaEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model: str = os.getenv('LAIKA_EMBEDDING_MODEL', '')) -> None:
        if not model:
            raise Exception('Embedding model was not detected.')
        self.model = SentenceTransformer(model)

    
    def __call__(self, input: Documents) -> Embeddings:
        return self.model.encode(input).tolist()
