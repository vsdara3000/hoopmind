from sentence_transformers import SentenceTransformer

# loads once when module is first imported, cached for all subsequent calls
_model = None

def get_model():
    global _model
    if _model is None:
        print("Loading embedding model...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Embedding model loaded.")
    return _model

def embed(text: str) -> list[float]:
    return get_model().encode(text).tolist()