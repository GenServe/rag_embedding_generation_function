import os
import logging
import azure.functions as func
from langchain_openai import AzureOpenAIEmbeddings
from pydantic import SecretStr
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from azure.storage.blob import BlobClient

import uuid
import cgi
from azure.storage.blob import BlobServiceClient
import re

from io import BytesIO
import fitz
import pandas as pd
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
import json
from lib.multi_file_type_text_extraction import extract_text_by_extension
from lib.initializer_embedding_model import get_embeddings_model

app = func.FunctionApp()


def get_vector_store(embeddings):
    return QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        collection_name=os.getenv("QDRANT_COLLECTION") or "default_collection",
        url=os.getenv("QDRANT_URL"),
        prefer_grpc=True,
        api_key=os.getenv("QDRANT_API_KEY")
    )

# MAKE ENV VARIBALES FOR  chunck_size and chunk_overlap
def chunk_text(text, chunk_size=2000, chunk_overlap=200):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    return splitter.split_text(text)

def is_valid_azure_blob_url(url):
    """Validate if the URL is likely an Azure Blob Storage URL"""
    # Basic pattern for Azure blob URLs
    pattern = r'^https?://[a-zA-Z0-9]+\.blob\.core\.windows\.net/[a-zA-Z0-9\-]+/.+$'
    return re.match(pattern, url) is not None

def download_blob_from_url(blob_url):
    """Download blob content from a URL"""
    try:
        from azure.storage.blob import BlobServiceClient
        
        # Get connection string from app settings
        connection_string = os.getenv("AzureWebJobsStorage")
        if not connection_string:
            raise ValueError("Missing AzureWebJobsStorage connection string")
            
        # Parse URL to get container and blob name
        parts = blob_url.replace('https://', '').split('/')
        container = parts[1]
        blob_name = '/'.join(parts[2:])
        
        # Create blob client from connection string
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client(container)
        blob_client = container_client.get_blob_client(blob_name)
        
        blob_data = blob_client.download_blob()
        
        return {
            "content": blob_data.readall(),
            "name": blob_url.split('/')[-1],
            "properties": blob_client.get_blob_properties()
        }
    except Exception as e:
        logging.error(f"Error downloading blob: {str(e)}")
        raise


@app.route(route="rag_embedding_generation_file_upload", auth_level=func.AuthLevel.ANONYMOUS, methods=["POST"])
def rag_embedding_generation_file_upload(req: func.HttpRequest) -> func.HttpResponse:
    """
    Endpoint to upload a file directly with user_id and chat_id, then process through the RAG pipeline.
    Expects multipart/form-data with fields: file, user_id, chat_id
    """

    logging.info('Processing direct file upload for RAG embedding generation.')

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
            fileitem = fs['file']
            user_id = fs.getvalue('user_id')
            chat_id = fs.getvalue('chat_id')
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": f"Invalid form data: {str(e)}. Must include file, user_id, and chat_id."}),
                status_code=400,
                mimetype="application/json"
            )

        if fileitem is None or not user_id or not chat_id:
            return func.HttpResponse(
                json.dumps({"error": "Missing file, user_id, or chat_id in request."}),
                status_code=400,
                mimetype="application/json"
            )

        filename = fileitem.filename
        file_bytes = fileitem.file.read()

        # Upload file to Azure Blob Storage with user_id and chat_id in path
        try:
            connection_string = os.getenv("AzureWebJobsStorage")
            container_name = os.getenv("UPLOAD_CONTAINER") or "uploads"
            if not connection_string:
                raise ValueError("Missing AzureWebJobsStorage connection string")

            updated_filename = f"{user_id}/{chat_id}/{uuid.uuid4()}_{filename}"
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            try:
                # Ensure the container exists
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
            try:
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=updated_filename)
                blob_client.upload_blob(file_bytes, overwrite=True)
            except Exception as e:
                logging.error(f"Error uploading blob: {str(e)}")
                return func.HttpResponse(
                    json.dumps({"error": f"Failed to upload file to blob storage: {str(e)}"}),
                    status_code=500,
                    mimetype="application/json"
                )
            file_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{updated_filename}"
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": f"Failed to upload file to blob storage: {str(e)}"}),
                status_code=500,
                mimetype="application/json"
            )

        # Extract text based on file type
        extraction_result = extract_text_by_extension(filename, file_bytes)
        if "error" in extraction_result:
            return func.HttpResponse(
                json.dumps({"error": extraction_result["error"]}),
                status_code=400,
                mimetype="application/json"
            )

        content = extraction_result["text"]

        # Chunk the text
        chunks = chunk_text(content)
        logging.info(f"Chunked into {len(chunks)} chunks.")

        # Get embeddings model
        embeddings = get_embeddings_model()

        # Store in Qdrant
        try:
            vector_store = get_vector_store(embeddings)
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
            logging.info(f"Stored {len(docs)} chunks in Qdrant vector store.")
        except Exception as e:
            logging.warning(f"Could not add to Qdrant: {e}")
            return func.HttpResponse(
                json.dumps({"error": f"Failed to store in vector database: {str(e)}", "text_extracted": True}),
                status_code=500,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps({
                "message": "File uploaded and processed successfully",
                "filename": updated_filename,
                "user_id": user_id,
                "chat_id": chat_id,
                "blob_url": file_url,
                "chunks_count": len(chunks),
                "first_chunk_preview": chunks[0][:100] + "..." if chunks else ""
            }),
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