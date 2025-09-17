import os
import sqlite3
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

def build_faiss_index(index_name, data_list):
    """
    Builds a FAISS index from a list of scraped data and saves it
    to a folder named after the index_name.
    """
    index_path = index_name

    if not data_list:
        print(f"No data provided for index: {index_name}")
        return

    print(f"Rebuilding FAISS index for: {index_name}...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    # Get content from the provided data list
    docs = [item['content'] for item in data_list]

    chunks = []
    for doc in docs:
        chunks.extend(splitter.split_text(doc))
    
    if not chunks:
        print(f"No text chunks generated for index: {index_name}")
        return

    documents = [Document(page_content=chunk) for chunk in chunks]

    vectorstore = FAISS.from_documents(documents, embeddings)
    vectorstore.save_local(index_path)
    print(f"FAISS index rebuilt and saved to: {index_path}")

def combine_retrieved_chunks(chunks):
    """Joins the page_content of retrieved documents."""
    return "\n".join(chunk.page_content for chunk in chunks)