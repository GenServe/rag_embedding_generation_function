import asyncio
import logging
from langchain_core.documents import Document

from lib.multi_file_type_text_extraction import extract_text_by_extension  # Adjust the import path as needed
from lib.vector_initialisation_chuncking import get_vector_store, chunk_text


# Asynchronous function to extract text and embed it into the vector store
async def extract_and_embed_async(filename, file_bytes, vector_store, user_id, chat_id):
    loop = asyncio.get_event_loop()
    def sync_extract_and_embed():
        # Extract text from the file based on its extension
        extraction_result = extract_text_by_extension(filename, file_bytes)
        if "error" in extraction_result:
            return {"success": False, "error": extraction_result["error"]}
        content = extraction_result["text"]
        # Chunk the extracted text for embedding
        chunks = chunk_text(content)
        logging.info(f"Chunked {filename} into {len(chunks)} chunks.")
        try:
            # Create Document objects for each chunk and add them to the vector store
            docs = [
                Document(
                    page_content=chunk,
                    metadata={
                        "filename": filename,
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "chunk_index": i
                    }
                )
                for i, chunk in enumerate(chunks)
            ]
            try:
                vector_store.add_documents(docs)
            except Exception as e:
                logging.error(f"Error adding documents to vector store for {filename}: {e}")
                return {
                    "success": False,
                    "error": f"Error adding documents to vector store: {str(e)}",
                    "text_extracted": True
                }
            logging.info(f"Stored {len(docs)} chunks for {filename} in Qdrant vector store.")
            return {
                "success": True,
                "chunks_count": len(chunks),
                "first_chunk_preview": chunks[0][:100] + "..." if chunks else ""
            }
        except Exception as e:
            logging.warning(f"Could not add {filename} to Qdrant: {e}")
            return {
                "success": False,
                "error": f"Failed to store in vector database: {str(e)}",
                "text_extracted": True
            }
    # Run the blocking extraction and embedding in a thread pool executor
    return await loop.run_in_executor(None, sync_extract_and_embed)
