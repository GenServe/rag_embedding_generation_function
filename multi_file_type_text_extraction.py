from io import BytesIO
import fitz
import pandas as pd
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
import json


def extract_text_by_extension(filename: str, file_bytes: bytes) -> dict:
    ext = filename.lower().split('.')[-1]
    if not filename:
        return {"error": "Filename is missing in the uploaded file."}
    try:
        if ext == "pdf":
            pdf_file_like = BytesIO(file_bytes)
            doc = fitz.open(stream=pdf_file_like, filetype="pdf")
            return {"text": "\n".join([page.get_text() for page in doc])} # type: ignore
        elif ext in ("xlsx", "xls"):
            excel_file_like = BytesIO(file_bytes)
            df = pd.read_excel(excel_file_like)
            return {"text": df.to_csv(index=False)}
        elif ext == "csv":
            csv_file_like = BytesIO(file_bytes)
            df = pd.read_csv(csv_file_like)
            return {"text": df.to_csv(index=False)}
        elif ext == "txt":
            return {"text": file_bytes.decode("utf-8")}
        elif ext == "html":
            soup = BeautifulSoup(file_bytes, "html.parser")
            return {"text": soup.get_text(separator="\n")}
        elif ext == "py":
            return {"text": file_bytes.decode("utf-8")}
        elif ext == "sql":
            return {"text": file_bytes.decode("utf-8")}
        elif ext in ("jpg", "jpeg", "png", "bmp", "tiff"):
            image = Image.open(BytesIO(file_bytes))
            text = pytesseract.image_to_string(image)
            return {"text": text}
        else:
            return {"error": f"Unsupported file extension: .{ext}"}
    except Exception as e:
        return {"error": str(e)}