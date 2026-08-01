import os
import re
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from sentence_transformers import CrossEncoder

DB_PATH = "vectorstore/faiss_index"

GENERIC_KEYWORDS = [
    "sobre o que", "resuma", "resumo", "geral", "do que se trata", 
    "conteudo", "conteúdo", "overview", "summary", "what is this document about",
    "what is the document about", "about the document"
]


def format_docs(docs):
    seen = set()
    unique_docs = []
    for doc in docs:
        if doc.page_content not in seen:
            seen.add(doc.page_content)
            unique_docs.append(doc.page_content)
    return "\n\n---\n\n".join(unique_docs)


def clean_deepseek_output(text):
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return text.strip()


def custom_retriever_with_reranker(query, vectorstore, all_docs, reranker, fetch_k=15, top_k=3, debug=False):
    is_generic = any(kw in query.lower() for kw in GENERIC_KEYWORDS)
    
    # 1. Busca Inicial no FAISS
    raw_results = vectorstore.similarity_search(query, k=fetch_k)
    if not raw_results:
        return []

    # 2. Executa o Re-Ranker (Cross-Encoder)
    pairs = [[query, doc.page_content] for doc in raw_results]
    cross_scores = reranker.predict(pairs)
    
    # 3. Ordena os resultados do MAIOR score para o MENOR
    scored_docs = list(zip(raw_results, cross_scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)
    
    top_k_pairs = scored_docs[:top_k]
    final_docs = [doc for doc, _ in top_k_pairs]
    
    # 4. Print de Debug
    if debug:
        print("\n" + "="*30 + f" [RAG DEBUG: RE-RANKER | FETCH={fetch_k} | TOP={top_k}] " + "="*30)
        top_k_docs_set = set(id(doc) for doc in final_docs)
        
        for i, (doc, score) in enumerate(scored_docs, 1):
            page_num = doc.metadata.get("page", "N/A")
            
            if id(doc) in top_k_docs_set:
                status = f"PASSED (Top-{top_k})"
            else:
                status = "DISCARDED (Low Cross-Score)"
                
            print(f"--- RANK {i} | Cross-Score: {score:.4f} | Status: {status} (Page: {page_num}) ---")
            print(doc.page_content.strip()[:100].replace('\n', ' ') + "...")
            
        if is_generic:
            print("-" * 80)
            print("⚠️ [GENERIC OVERRIDE ACTIVE]: Pergunta genérica detectada.")
            print("O Re-Ranker avaliou os chunks acima, mas o agente usará 'all_docs[:2]' para resumir o documento.")
            
        print("="*80 + "\n")

    # 5. Tratamento para perguntas genéricas (resumo/overview)
    if is_generic:
        return all_docs[:2]
    
    return final_docs


def run_agent():
    load_dotenv()

    embeddings = FastEmbedEmbeddings()
    vectorstore = FAISS.load_local(DB_PATH, embeddings, allow_dangerous_deserialization=True)
    
    all_docs = list(vectorstore.docstore._dict.values())
    all_docs.sort(key=lambda x: x.metadata.get("page", 0))

    llm = Ollama(model="deepseek-r1:1.5b", temperature=0.6)
    
    print("Carregando o modelo Cross-Encoder Re-Ranker...")
    hf_token = os.getenv("HF_TOKEN")
    
    reranker = CrossEncoder(
        'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1',
        token=hf_token  # Passa o token do .env aqui
    )
    
    template = """You are an information extraction engine.

Your task is ONLY to extract the retrieved context.

Rules:

- Never explain.
- Never infer.
- Never use prior knowledge.
- Never complete missing information.
- Never define technical terms.
- Never use words that do not appear in the context.
- Only paraphrase.

If the extraction cannot be produced using only the retrieved context, output:

I could not find this information in the retrieved context.

Here are the answers to the questions based on the **Santo Pegasus Back-end Engineering Guide**:

<EXAMPLE>
Question: "What is this document about?"
Extraction:
This is the **Official Back-end Engineering Guide** for **Santo Pegasus Soluciones**. It serves as the definitive technical standard and reference manual for the company's software engineering team. The guide outlines the company's engineering philosophy, mandatory technical standards, and best practices for building and maintaining their backend systems.
Specifically, it covers Santo Pegasus's Core Philoshophy, its Design Principles, Tech Stack, Software Architecture, Advanced AI strategy, Security and Compliance standards, communication and stability patterns, guidelines for database migration and testing, and procedures for CI/CD and infrastructure.
In essence, it is a comprehensive blueprint that defines "how" engineering is done at Santo Pegasus Soluciones, ensuring that all developers build systems that are resilient, secure, maintainable, and aligned with the company's high standards.
</EXAMPLE>

<EXAMPLE>
Question: "What are the four pillars of Engineering Excellence at Santo Pegasus?"
Extraction:
1. **Technical Ownership:** Developers are responsible for the full lifecycle of their code, from design to production monitoring.
2. **Radical Simplicity** Solving complex problems with the minimal required code.
3. **Security by Design** Compliance and security begin with the first line of code.
4. **Continuous Evolution** Adopting "Kaizen" (constant improvement).
</EXAMPLE>

<EXAMPLE>
Question: "What Java version is the standard for new developments?"
Extraction: Java **17** and **21** are the standards for new developments.
</EXAMPLE>

<EXAMPLE>
Question: "According to the guide, what is the Single Responsibility Principle (SRP) and what was the problem with the legacy PaymentService?"
Extraction:
* **Definition:** A class should have one, and only one, reason to change.
* **Legacy Problem:** The legacy `PaymentService` violated SRP because it handled user validation, fee calculation, database persistence, and sending email receipts all inside a single class.
</EXAMPLE>

<EXAMPLE>
Question: "How does the guide suggest implementing the Open/Closed Principle using Java 17 features?"
Extraction:
By using **Sealed Interfaces** and **Records** to create closed domain hierarchies (e.g., `public sealed interface PaymentMethod permits Pix, Boleto, CreditCard`) combined with the Strategy Pattern to allow extending functionality without altering existing code.
</EXAMPLE>

<EXAMPLE>
Question: "What are the three layers of the Hexagonal Architecture described in the document?"
Extraction:
1. **Domain:** Pure Java containing business logic, entities, and domain rules, free of Spring or JPA annotations.
2. **Application:** Contains use cases and orchestrates business logic using ports.
3. **Infrastructure:** Contains implementation details and adapters (repositories, web clients, messaging).
</EXAMPLE>

<EXAMPLE>
Question: "What is the dependency rule in the Ports and Adapters architecture?"
Extraction: Dependencies must always point inward toward the **Domain**. The domain never knows about the database or external REST APIs.
</EXAMPLE>

<EXAMPLE>
Question: "What encryption standard is mandatory for data in transit?"
Extraction: **TLS 1.3** is mandatory for all communications in transit.
</EXAMPLE>

<EXAMPLE>
Question: "What must be done to production data in Homologation environments?"
Extraction: Production data must be forcibly **masked** or **anonymized**.
</EXAMPLE>

<EXAMPLE>
Question: "What is the recommended distribution of tests in the Santo Pegasus test pyramid?"
Extraction:
* **Unit Tests:** 70%
* **Integration Tests:** 20%
* **E2E / Contract Tests:** 10%
</EXAMPLE>

<EXAMPLE>
Question: "What deployment strategy is preferred for critical services?"
Extraction: **Blue-Green** deployment.
</EXAMPLE>

<EXAMPLE>
Question: "What is the Docker strategy used to create lightweight images?"
Extraction: **Multi-stage builds** (separating the build phase from the lightweight JRE runtime phase).
</EXAMPLE>

<EXAMPLE>
Question: "What are the approved messaging systems?"
Extraction: **RabbitMQ** or **AWS SQS**.
</EXAMPLE>

<EXAMPLE>
Question: "What vector database is used for the RAG pipeline?"
Extraction: **Qdrant**.
</EXAMPLE>

<EXAMPLE>
Question: "What is the name of the internal payment gateway?"
Extraction: **PegasusPay**.
</EXAMPLE>

<EXAMPLE>
Question: "What is the importance of idempotency at Santo Pegasus?"
Extraction: It guarantees that an operation can be safely repeated without creating unwanted side effects, which is vital for financial transactions and payment processing.
</EXAMPLE>

<EXAMPLE>
Question: "What metrics are used for alerting in Prometheus?"
Extraction: Alerts trigger when **P99 latency > 500ms** or when the **5xx error rate > 1%**.
</EXAMPLE>

<EXAMPLE>
Question: "What is the RAG chunking strategy used instead of fixed divisions?"
Extraction: **Semantic Chunking**, which uses paragraph analysis to maintain semantic context.
</EXAMPLE>

Context:
{context}

Question: {question}

Extraction:"""
    
    prompt = PromptTemplate.from_template(template)

    FETCH_K = 15
    TOP_K = 1

    print(f"\n--- Seiya IA (Re-Ranker Active | Fetch K: {FETCH_K} | Top K: {TOP_K}) ---")
    show_chunks_input = input("Deseja ativar a visualização dos chunks? (s/n): ").strip().lower()
    debug_mode = (show_chunks_input == 's')

    while True:
        pergunta = input("\nFaça uma pergunta sobre o documento (ou 'sair'): ")
        if pergunta.lower() in ['sair', 'exit']:
            break
                
        docs = custom_retriever_with_reranker(
            query=pergunta, 
            vectorstore=vectorstore, 
            all_docs=all_docs, 
            reranker=reranker, 
            fetch_k=FETCH_K,
            top_k=TOP_K,
            debug=debug_mode
        )
        
        if not docs:
            print("\n[Resposta do Agente]: I could not find relevant information in the document for this question.")
            continue

        print("O agente está analisando...")
        
        context_str = format_docs(docs)
        formatted_prompt = prompt.format(context=context_str, question=pergunta)

        print("=" * 80)
        print(context_str)
        print("=" * 80)
        
        raw_response = llm.invoke(formatted_prompt)
        resposta_final = clean_deepseek_output(raw_response)
        
        print(f"\n[Resposta do Agente]:\n{resposta_final}")

if __name__ == "__main__":
    run_agent()