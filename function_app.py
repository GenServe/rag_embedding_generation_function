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

app = func.FunctionApp()

@app.route(route="rag_embedding_generation_file_upload", auth_level=func.AuthLevel.ANONYMOUS, methods=["POST"])
def rag_embedding_generation_file_upload(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint to upload a file directly with user_id and chat_id, then process through the RAG pipeline.
    Expects multipart/form-data with fields: file, user_id, chat_id
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
            user_id = fs.getvalue('user_id')
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

        embeddings = get_embeddings_model()
        vector_store = get_vector_store(embeddings)
        results = []

        for fileitem in fileitems:
            filename = fileitem.filename
            file_bytes = fileitem.file.read()
            updated_filename = f"{user_id}/{chat_id}/{uuid.uuid4()}_{filename}"
            try:
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=updated_filename)
                blob_client.upload_blob(file_bytes, overwrite=True)
                file_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{updated_filename}"
            except Exception as e:
                logging.error(f"Error uploading blob: {str(e)}")
                results.append({
                    "filename": filename,
                    "error": f"Failed to upload file to blob storage: {str(e)}"
                })
                continue

            extraction_result = extract_text_by_extension(filename, file_bytes)
            if "error" in extraction_result:
                results.append({
                    "filename": filename,
                    "error": extraction_result["error"]
                })
                continue

            content = extraction_result["text"]
            chunks = chunk_text(content)
            logging.info(f"Chunked {filename} into {len(chunks)} chunks.")

            try:
                docs = [
                    Document(
                        page_content=chunk,
                        metadata={
                            "filename": filename,
                            "blob_url": file_url,
                            "user_id": user_id,
                            "chat_id": chat_id,
                            "chunk_index": i
                        }
                    )
                    for i, chunk in enumerate(chunks)
                ]
                vector_store.add_documents(docs)
                logging.info(f"Stored {len(docs)} chunks for {filename} in Qdrant vector store.")
                results.append({
                    "message": "File uploaded and processed successfully",
                    "filename": updated_filename,
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "blob_url": file_url,
                    "chunks_count": len(chunks),
                    "first_chunk_preview": chunks[0][:100] + "..." if chunks else ""
                })
            except Exception as e:
                logging.warning(f"Could not add {filename} to Qdrant: {e}")
                results.append({
                    "filename": filename,
                    "error": f"Failed to store in vector database: {str(e)}",
                    "text_extracted": True
                })

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