# RAG Embedding Generation Function

A serverless Azure Function for processing documents stored in Azure Blob Storage, extracting text content, generating embeddings using Azure OpenAI, and storing them in Qdrant vector database for Retrieval Augmented Generation (RAG) systems.

## 📋 Features

- Process documents from Azure Blob Storage via URL
- Extract text from multiple file formats:
  - PDF documents (using PyMuPDF)
  - Excel files (XLSX, XLS)
  - CSV files
  - Text files
  - HTML documents
  - Images (using OCR with pytesseract)
  - Python and SQL files
- Text chunking with configurable size and overlap
- Embedding generation using Azure OpenAI
- Vector storage in Qdrant database
- RESTful API interface

## 🏗️ Architecture

The solution consists of:

1. **HTTP Trigger Function**: Accepts blob URLs via HTTP POST requests
2. **Text Extraction**: Processes documents based on file type
3. **Text Chunking**: Splits content into manageable chunks
4. **Embedding Generation**: Creates vector embeddings via Azure OpenAI
5. **Vector Storage**: Saves embeddings and metadata to Qdrant

```
┌─────────────┐    ┌───────────────┐    ┌────────────┐    ┌──────────────┐    ┌────────────┐
│ HTTP        │    │ Azure Blob    │    │ Text       │    │ Azure OpenAI │    │ Qdrant     │
│ Request     │───►│ Storage       │───►│ Processing │───►│ Embeddings   │───►│ Vector DB  │
└─────────────┘    └───────────────┘    └────────────┘    └──────────────┘    └────────────┘
```

## 🛠️ Prerequisites

- Python 3.8 or higher
- Azure Subscription
- Azure Storage Account
- Azure OpenAI deployment
- Qdrant vector database instance
- Azure Functions Core Tools (for local development)

## 📦 Installation

1. Clone this repository:

```bash
git clone <repository-url>
cd rag_embedding_generation_function
```

2. Create a virtual environment and install dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## ⚙️ Configuration

Create a local.settings.json file for local development:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "DefaultEndpointsProtocol=https;AccountName=YOUR_STORAGE_ACCOUNT;AccountKey=YOUR_STORAGE_KEY;EndpointSuffix=core.windows.net",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_OPENAI_API_KEY": "YOUR_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT": "text-embedding-3-large",
    "AZURE_OPENAI_TEXTEMBEDDER_API_VERSION": "2023-05-15",
    "AZURE_OPENAI_TEXTEMBEDDER_ENDPOINT": "https://YOUR_OPENAI_RESOURCE.openai.azure.com/",
    "QDRANT_COLLECTION": "default_collection",
    "QDRANT_URL": "https://YOUR_QDRANT_INSTANCE.qdrant.io",
    "QDRANT_API_KEY": "YOUR_QDRANT_API_KEY"
  }
}
```

For production deployment, configure these settings in your Azure Function App's Configuration.

## 🚀 Running Locally

Start the function app locally:

```bash
func start
```

The function will be available at: `http://localhost:7071/api/rag_embedding_generation_text_extraction`

## 📝 Usage

### API Endpoint

Send a POST request to the function with a JSON body containing a blob URL:

```bash
curl -X POST http://localhost:7071/api/rag_embedding_generation_text_extraction \
  -H "Content-Type: application/json" \
  -d '{
    "blob_url": "https://yourstorageaccount.blob.core.windows.net/container/document.pdf?sv=2022-11-02&ss=b&srt=sco&sp=r&se=2023-12-31T00:00:00Z&st=2023-01-01T00:00:00Z&spr=https&sig=YOURSASTOKEN"
  }'
```

### Response Format

Successful response:

```json
{
  "message": "Blob processed successfully",
  "filename": "document.pdf",
  "blob_url": "https://yourstorageaccount.blob.core.windows.net/container/document.pdf?sv=...",
  "chunks_count": 15,
  "first_chunk_preview": "This is the beginning of the document..."
}
```

## 🔐 Authentication Options

### Option 1: SAS Token (Recommended for Direct API Usage)

Include a SAS token in the blob URL:

```json
{
  "blob_url": "https://yourstorageaccount.blob.core.windows.net/container/document.pdf?sv=2022-11-02&ss=b&srt=sco&sp=r&se=2023-12-31T00:00:00Z&st=2023-01-01T00:00:00Z&spr=https&sig=YOURSASTOKEN"
}
```

### Option 2: Azure Managed Identity (Recommended for Production)

For secure production deployment, configure the function app to use managed identity:

1. Enable system-assigned managed identity for your function app
2. Grant the managed identity Storage Blob Data Reader access to your storage account
3. Update the download_blob_from_url function to use DefaultAzureCredential

### Option 3: Connection String

Use the storage account connection string stored in application settings.

## 📤 Deployment to Azure

1. Create an Azure Function App:

```bash
az functionapp create --resource-group YourResourceGroup --consumption-plan-location eastus \
  --runtime python --runtime-version 3.9 --functions-version 4 \
  --name YourFunctionAppName --storage-account YourStorageAccountName
```

2. Deploy the function app:

```bash
func azure functionapp publish YourFunctionAppName
```

3. Configure application settings in Azure Portal or using Azure CLI:

```bash
az functionapp config appsettings set --name YourFunctionAppName --resource-group YourResourceGroup \
  --settings "AZURE_OPENAI_API_KEY=your-key" "AZURE_OPENAI_DEPLOYMENT=text-embedding-3-large" ...
```

## ⚠️ Troubleshooting

### Authentication Errors

If you see "Server failed to authenticate the request" errors:

- Check that your SAS token is valid and has not expired
- Verify that the managed identity has appropriate permissions
- Ensure your storage connection string is correctly configured

### Missing Text Extraction

If text extraction fails:

- Check that the file format is supported
- Ensure required libraries are installed (e.g., pytesseract for OCR)
- Verify file encoding for text files

### Vector Store Errors

If Qdrant storage fails:

- Verify your Qdrant URL and API key
- Ensure the collection exists or configure to create automatically
- Check network connectivity to the Qdrant instance

## 📚 File Structure

```
rag_embedding_generation_function/
├── function_app.py             # Main function code
├── requirements.txt            # Python dependencies
├── host.json                   # Function host configuration
├── local.settings.json         # Local settings (not in repo)
└── README.md                   # Documentation
```

## 📢 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
