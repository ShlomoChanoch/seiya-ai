import os
import re
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document

PDF_PATH = "data/documento.pdf"
DB_PATH = "vectorstore/faiss_index"

def process_document():
    print("1. Carregando o documento...")
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()

    print("2. Dividindo o texto por seções mantendo os metadados...")
    documents = []
    
    for page in docs:
        # Regex ajustado com grupo não-capturante (?:...)
        sections = re.split(
            r"\n(?=\d+(?:\.\d+)*\.\s)",
            page.page_content
        )
        
        for section in sections:
            section = section.strip()
            if section:
                # Transforma cada trecho num objeto Document mantendo o metadata da página
                documents.append(
                    Document(
                        page_content=section,
                        metadata=page.metadata
                    )
                )

    print(f"3. Gerando embeddings locais para {len(documents)} trechos e salvando o índice...")
    embeddings = FastEmbedEmbeddings()
    
    # Passa a lista de objetos Document
    vectorstore = FAISS.from_documents(documents, embeddings)
    vectorstore.save_local(DB_PATH)
    
    print("Sucesso! Banco de conhecimento criado em 'vectorstore/faiss_index'.")

if __name__ == "__main__":
    process_document()