import os
import logging
import azure.functions as func
from langchain_core.documents import Document
from azure.storage.blob import BlobClient

import uuid
import cgi
from azure.storage.blob import BlobServiceClient
import re

from io import BytesIO
import json

from lib.multi_file_type_text_extraction import extract_text_by_extension
from lib.initializer_embedding_model import get_embeddings_model
from lib.azure_blob_handler import download_blob_from_url, is_valid_azure_blob_url
from lib.vector_initialisation_chuncking import get_vector_store, chunk_text
from lib.auth import get_current_user, Security, HTTPException
from lib.upload_file import upload_file_async
from lib.extract_embed_processing import extract_and_embed_async

import asyncio

app = func.FunctionApp()

@app.route(route="rag_embedding_generation_file_upload", auth_level=func.AuthLevel.ANONYMOUS, methods=["POST"])
def rag_embedding_generation_file_upload(req: func.HttpRequest) -> func.HttpResponse:
    """
    Handles direct file uploads for RAG (Retrieval-Augmented Generation) embedding generation.
    This endpoint allows users to upload one or more files, which are then processed through the RAG pipeline.
    The uploaded files are stored in Azure Blob Storage, and their contents are extracted, chunked, and embedded
    into a vector store for later retrieval.
    Expected Request:
        - HTTP POST with multipart/form-data.
        - Fields:
            - file: The file(s) to upload (supports single or multiple files).
            - chat_id: The chat session identifier.
        - Header:
            - Authorization: Bearer token for user authentication.
    Workflow:
        1. Authenticates the user using the Authorization header.
        2. Parses multipart form data to extract files and chat_id.
        3. Uploads each file to Azure Blob Storage under a path organized by user_id and chat_id.
        4. Extracts text from each file based on its extension.
        5. Chunks the extracted text and stores the resulting documents in a vector store (e.g., Qdrant).
        6. Returns a JSON response with the status and metadata for each processed file.
    Returns:
        - 200 OK: On successful upload and processing, returns a list of results for each file, including:
            - filename: The blob storage path of the uploaded file.
            - user_id: The authenticated user's ID.
            - chat_id: The provided chat session ID.
            - blob_url: The public URL to the uploaded file in Azure Blob Storage.
            - chunks_count: Number of text chunks generated and stored.
            - first_chunk_preview: Preview of the first chunk of extracted text.
            - message: Success message.
        - 400 Bad Request: If required fields are missing or form data is invalid.
        - 401 Unauthorized: If the Authorization header is missing or invalid.
        - 500 Internal Server Error: For unexpected errors during processing.
    Notes:
        - The function supports both single and multiple file uploads.
        - File extraction and embedding are performed asynchronously for efficiency.
        - User authentication is mandatory; user_id is derived from the authenticated user, not the form.
        - Error handling is included for authentication, form parsing, blob storage, and vector store operations.
    Dependencies:
        - Azure Blob Storage SDK
        - Qdrant or compatible vector store
        - Custom functions: get_current_user, extract_text_by_extension, chunk_text, get_embeddings_model, get_vector_store
        - Python standard libraries: asyncio, cgi, logging, os, uuid, json, BytesIO
    """

    logging.info('Processing direct file upload for RAG embedding generation.')

    # Authenticate user
    try:
        # Extract the Authorization header
        auth_header = req.headers.get("Authorization")
        if not auth_header:
            return func.HttpResponse(
                json.dumps({"error": "Missing Authorization header"}),
                status_code=401,
                mimetype="application/json"
            )
        # Parse credentials for get_current_user
        
        user = get_current_user(auth_header)
    except HTTPException as e:
        return func.HttpResponse(
            json.dumps({"error": e.detail}),
            status_code=e.status_code,
            mimetype="application/json"
        )

    try:
        # Parse multipart form data
        try:
            environ = {'REQUEST_METHOD': 'POST'}
            environ.update(req.headers)
            fs = cgi.FieldStorage(
                fp=BytesIO(req.get_body()),
                environ=environ,
                headers=req.headers
            )
            fileitems = fs['file']
            user_id = user["user_id"]  # Use user_id from authenticated user
            chat_id = fs.getvalue('chat_id')
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": f"Invalid form data: {str(e)}. Must include file, user_id, and chat_id."}),
                status_code=400,
                mimetype="application/json"
            )

        # Support both single and multiple files
        if not isinstance(fileitems, list):
            fileitems = [fileitems]

        if not fileitems or not user_id or not chat_id:
            return func.HttpResponse(
                json.dumps({"error": "Missing file, user_id, or chat_id in request."}),
                status_code=400,
                mimetype="application/json"
            )

        connection_string = os.getenv("AZURE_BLOB_STORAGE_CONNECTION_STRING")
        container_name = os.getenv("UPLOAD_CONTAINER") or "uploads"
        if not connection_string:
            raise ValueError("Missing AZURE_BLOB_STORAGE_CONNECTION_STRING")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        try:
            container_client = blob_service_client.get_container_client(container_name)
            if not container_client.exists():
                container_client.create_container()
        except Exception as e:
            logging.error(f"Error ensuring blob container exists: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": f"Failed to ensure blob container exists: {str(e)}"}),
                status_code=500,
                mimetype="application/json"
            )

        # updated_filename = f"{user_id}/{chat_id}/{uuid.uuid4()}_{filename}"
        
        embeddings = get_embeddings_model()
        vector_store = get_vector_store(embeddings)
        results = []

        # # Asynchronous function to upload a file to Azure Blob Storage
        # async def upload_file_async(blob_service_client, container_name, updated_filename, file_bytes):
        #     loop = asyncio.get_event_loop()
        #     def sync_upload():
        #         try:
        #             # Upload the file to the specified blob container and path
        #             blob_client = blob_service_client.get_blob_client(container=container_name, blob=updated_filename)
        #             blob_client.upload_blob(file_bytes, overwrite=True)
        #             # Construct the public URL for the uploaded file
        #             file_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{updated_filename}"
        #             return {"success": True, "file_url": file_url}
        #         except Exception as e:
        #             return {"success": False, "error": f"Failed to upload file to blob storage: {str(e)}"}
        #         # Run the blocking upload operation in a thread pool executor
        #     return await loop.run_in_executor(None, sync_upload)

        # # Asynchronous function to extract text and embed it into the vector store
        # async def extract_and_embed_async(filename, file_bytes, vector_store, user_id, chat_id):
        #     loop = asyncio.get_event_loop()
        #     def sync_extract_and_embed():
        #     # Extract text from the file based on its extension
        #         extraction_result = extract_text_by_extension(filename, file_bytes)
        #         if "error" in extraction_result:
        #             return {"success": False, "error": extraction_result["error"]}
                
        #         content = extraction_result["text"]
        #         # Chunk the extracted text for embedding
                
        #         chunks = chunk_text(content)
        #         logging.info(f"Chunked {filename} into {len(chunks)} chunks.")
        #         try:
        #             # Create Document objects for each chunk and add them to the vector store
        #             docs = [
        #             Document(
        #                 page_content=chunk,
        #                 metadata={
        #                 "filename": filename,
        #                 "user_id": user_id,
        #                 "chat_id": chat_id,
        #                 "chunk_index": i
        #                 }
        #             )
        #             for i, chunk in enumerate(chunks)
        #             ]
                    
        #             vector_store.add_documents(docs)
        #             logging.info(f"Stored {len(docs)} chunks for {filename} in Qdrant vector store.")
        #             return {
        #             "success": True,
        #             "chunks_count": len(chunks),
        #             "first_chunk_preview": chunks[0][:100] + "..." if chunks else ""
        #             }
        #         except Exception as e:
        #             logging.warning(f"Could not add {filename} to Qdrant: {e}")
        #             return {
        #             "success": False,
        #             "error": f"Failed to store in vector database: {str(e)}",
        #             "text_extracted": True
        #             }
        #     # Run the blocking extraction and embedding in a thread pool executor
        #     return await loop.run_in_executor(None, sync_extract_and_embed)

        # Asynchronous function to process a single file: upload and embed in parallel
        async def process_file(fileitem):
            filename = fileitem.filename
            file_bytes = fileitem.file.read()
            # Generate a unique path for the uploaded file
            updated_filename = f"{user_id}/{chat_id}/{uuid.uuid4()}_{filename}"

            # Start upload and embedding tasks concurrently for this file
            upload_task = asyncio.create_task(
            upload_file_async(blob_service_client, container_name, updated_filename, file_bytes)
            )
            extract_embed_task = asyncio.create_task(
                extract_and_embed_async(filename, file_bytes, vector_store, user_id, chat_id)
            )

            # Wait for both upload and embedding to complete in parallel
            upload_result, extract_embed_result = await asyncio.gather(upload_task, extract_embed_task)

            # Collect results and error handling for this file
            result = {
            "filename": updated_filename,
            "user_id": user_id,
            "chat_id": chat_id,
            }
            if upload_result.get("file_url"):
                result["blob_url"] = upload_result["file_url"]
            if not upload_result["success"]:
                result["error"] = upload_result["error"]
            if not extract_embed_result["success"]:
                result["error"] = extract_embed_result["error"]
            if "text_extracted" in extract_embed_result:
                result["text_extracted"] = True
            if extract_embed_result.get("chunks_count") is not None:
                result["chunks_count"] = extract_embed_result["chunks_count"]
            if extract_embed_result.get("first_chunk_preview") is not None:
                result["first_chunk_preview"] = extract_embed_result["first_chunk_preview"]
            if upload_result.get("success") and extract_embed_result.get("success"):
                result["message"] = "File uploaded and processed successfully"
            return result

        # Main async function to process all files in parallel
        async def main_async():
            # Create a list of tasks for all files and run them concurrently
            tasks = [process_file(fileitem) for fileitem in fileitems]
            return await asyncio.gather(*tasks)

        try:
            # Create and run a new event loop for asynchronous processing
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Run the main async function to process all files in parallel
            results = loop.run_until_complete(main_async())
            loop.close()
            # Return the results as a JSON response
            return func.HttpResponse(
            json.dumps(results),
            status_code=200,
            mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Error processing file upload: {str(e)}")
            return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
            )
    except Exception as e:
        logging.error(f"Error processing file upload: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )