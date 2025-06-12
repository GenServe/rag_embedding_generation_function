import os
import re
import logging
from azure.storage.blob import BlobServiceClient

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