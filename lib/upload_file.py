import asyncio
import os
import logging
from azure.storage.blob import BlobServiceClient

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


# Asynchronous function to upload a file to Azure Blob Storage
async def upload_file_async(blob_service_client, container_name, updated_filename, file_bytes):
    loop = asyncio.get_event_loop()
    def sync_upload():
        try:
            # Upload the file to the specified blob container and path
            blob_client = blob_service_client.get_blob_client(container=container_name, blob=updated_filename)
            blob_client.upload_blob(file_bytes, overwrite=True)
            # Construct the public URL for the uploaded file
            file_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{updated_filename}"
            return {"success": True, "file_url": file_url}
        except Exception as e:
            return {"success": False, "error": f"Failed to upload file to blob storage: {str(e)}"}
    # Run the blocking upload operation in a thread pool executor
    return await loop.run_in_executor(None, sync_upload)