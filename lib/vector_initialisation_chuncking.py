import os
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore



def get_vector_store(embeddings):
    return QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        collection_name=os.getenv("QDRANT_COLLECTION") or "default_collection",
        url=os.getenv("QDRANT_URL"),
        prefer_grpc=True,
        api_key=os.getenv("QDRANT_API_KEY")
    )

# MAKE ENV VARIBALES FOR  chunck_size and chunk_overlap
def chunk_text(text):
    chunk_size = int(os.getenv("CHUNK_SIZE", 2000))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", 200))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    return splitter.split_text(text)