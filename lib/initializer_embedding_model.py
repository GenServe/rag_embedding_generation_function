import os
import logging
from pydantic import SecretStr
from langchain_openai import AzureOpenAIEmbeddings

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
            deployment=deployment,  # type: ignore
            api_version=api_version,
            azure_endpoint=endpoint
        )
    except Exception as e:
        logging.error(f"Error initializing AzureOpenAIEmbeddings: {e}")
        raise