import os
import logging
import azure.functions as func
from langchain_openai import AzureOpenAIEmbeddings
from pydantic import SecretStr
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from azure.storage.blob import BlobClient
import re
# from azure.identity import DefaultAzureCredential

from io import BytesIO
import fitz
import pandas as pd
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
import json
from multi_file_type_text_extraction import extract_text_by_extension

app = func.FunctionApp()

def get_embeddings_model():
    try:
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "text-embedding-3-large")
        api_version = os.getenv("AZURE_OPENAI_TEXTEMBEDDER_API_VERSION")
        endpoint = os.getenv("AZURE_OPENAI_TEXTEMBEDDER_ENDPOINT")

        if not api_key:
            raise ValueError("Missing AZURE_OPENAI_API_KEY environment variable.")
        if not api_version:
            raise ValueError("Missing AZURE_OPENAI_TEXTEMBEDDER_API_VERSION environment variable.")
        if not endpoint:
            raise ValueError("Missing AZURE_OPENAI_TEXTEMBEDDER_ENDPOINT environment variable.")
        return AzureOpenAIEmbeddings(
            api_key=SecretStr(api_key),
            azure_deployment=deployment,
            api_version=api_version,
            azure_endpoint=endpoint
        )
        
    except Exception as e:
        logging.error(f"Error initializing AzureOpenAIEmbeddings: {e}")
        raise

def get_vector_store(embeddings):
    return QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        collection_name=os.getenv("QDRANT_COLLECTION") or "default_collection",
        url=os.getenv("QDRANT_URL"),
        prefer_grpc=True,
        api_key=os.getenv("QDRANT_API_KEY")
    )

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

@app.route(route="rag_embedding_generation_text_extraction", auth_level=func.AuthLevel.ANONYMOUS)
def rag_embedding_generation_text_extraction(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processing blob URL for RAG embedding generation.')
    
    try:
        # Parse request body
        try:
            req_body = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Request body must contain valid JSON"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Get blob URL from request
        blob_url = req_body.get('blob_url')
        if not blob_url:
            return func.HttpResponse(
                json.dumps({"error": "Please provide a blob_url in the request body"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate blob URL (basic check)
        if not is_valid_azure_blob_url(blob_url):
            return func.HttpResponse(
                json.dumps({"error": "Invalid Azure Blob Storage URL format"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Download the blob
        try:
            blob_data = download_blob_from_url(blob_url)
            file_bytes = blob_data["content"]
            filename = blob_data["name"]
        except Exception as e:
            return func.HttpResponse(
                json.dumps({"error": f"Failed to download blob: {str(e)}"}),
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
                        "blob_url": blob_url,
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
                "message": "Blob processed successfully",
                "filename": filename,
                "blob_url": blob_url,
                "chunks_count": len(chunks),
                "first_chunk_preview": chunks[0][:100] + "..." if chunks else ""
            }),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Error processing blob URL: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )