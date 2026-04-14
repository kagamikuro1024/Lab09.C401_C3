"""
rag_answer.py — Sprint 2 + Sprint 3: Retrieval & Grounded Answer
================================================================
Sprint 2 (60 phút): Baseline RAG
  - Dense retrieval từ ChromaDB
  - Grounded answer function với prompt ép citation
  - Trả lời được ít nhất 3 câu hỏi mẫu, output có source

Sprint 3 (60 phút): Tuning tối thiểu
  - Thêm hybrid retrieval (dense + sparse/BM25)
  - Hoặc thêm rerank (cross-encoder)
  - Hoặc thử query transformation (expansion, decomposition, HyDE)
  - Tạo bảng so sánh baseline vs variant

Definition of Done Sprint 2:
  ✓ rag_answer("SLA ticket P1?") trả về câu trả lời có citation
  ✓ rag_answer("Câu hỏi không có trong docs") trả về "Không đủ dữ liệu"

Definition of Done Sprint 3:
  ✓ Có ít nhất 1 variant (hybrid / rerank / query transform) chạy được
  ✓ Giải thích được tại sao chọn biến đó để tune
"""

import os
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CẤU HÌNH
# =============================================================================

TOP_K_SEARCH = 10    # Số chunk lấy từ vector store trước rerank (search rộng)
TOP_K_SELECT = 3     # Số chunk gửi vào prompt sau rerank/select (top-3 sweet spot)

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


# =============================================================================
# RETRIEVAL — DENSE (Vector Search)
# =============================================================================

def retrieve_dense(query: str, top_k: int = TOP_K_SEARCH) -> List[Dict[str, Any]]:
    """
    Dense retrieval: tìm kiếm theo embedding similarity trong ChromaDB.

    Args:
        query: Câu hỏi của người dùng
        top_k: Số chunk tối đa trả về

    Returns:
        List các dict, mỗi dict là một chunk với:
          - "text": nội dung chunk
          - "metadata": metadata (source, section, effective_date, ...)
          - "score": cosine similarity score
    """
    try:
        import chromadb
        from index import get_embedding, CHROMA_DB_DIR
    except ImportError as e:
        raise ImportError(f"Cần import: {e}")

    try:
        client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        collection = client.get_collection("rag_lab")
        
        # Embed query bằng cùng model indexing
        query_embedding = get_embedding(query)
        
        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        # Convert results to our format
        # Note: distances trong ChromaDB cosine = 1 - similarity
        # Score = 1 - distance
        chunks = []
        for i, (doc, meta, distance) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )):
            score = 1 - distance  # Convert distance to similarity
            chunks.append({
                "text": doc,
                "metadata": meta,
                "score": score,
            })
        
        return chunks
    
    except Exception as e:
        print(f"Lỗi trong retrieve_dense: {e}")
        return []


# =============================================================================
# RETRIEVAL — SPARSE / BM25 (Keyword Search)
# Dùng cho Sprint 3 Variant hoặc kết hợp Hybrid
# =============================================================================

# Global BM25 index (cache for performance)
_bm25_index = None
_bm25_chunks = None


def _simple_tokenize(text: str) -> List[str]:
    """
    Simple but effective Vietnamese tokenization with stopword filtering.
    """
    import re
    
    # Danh sách stop words tiếng Việt mở rộng (Aggressive stop words for IT context)
    VI_STOPWORDS = {
        "là", "gì", "và", "của", "cho", "trong", "được", "người", "việc", "khi",
        "tại", "với", "các", "những", "một", "có", "này", "đó", "về", "lại",
        "ra", "nào", "lên", "vào", "như", "đã", "đang", "cũng", "vì", "nên",
        "mà", "thì", "nếu", "hay", "cách", "xử", "lý", "theo", "tới", "từ",
        "lỗi", "bị", "để", "sau", "tất", "cả", "mọi", "hơn", "vẫn", "đang",
        "cần", "phải", "nói", "biết", "làm", "đưa", "với", "cho", "theo", "tới"
    }

    text = text.lower()
    # Keep alphanumeric, keep "-" and "_" (for error codes, etc)
    tokens = re.findall(r'\w[\w\-]*', text)
    
    # Filter stopwords but keep tokens that look like error codes (containing numbers or "-")
    filtered_tokens = [
        t for t in tokens 
        if t not in VI_STOPWORDS or any(char.isdigit() or char == '-' for char in t)
    ]
    
    return filtered_tokens if filtered_tokens else tokens


def _build_bm25_index() -> Tuple:
    """
    Build BM25 index từ tất cả chunks trong ChromaDB.
    Cache globally để không rebuild mỗi lần.
    improved tokenization để avoid noise retrieval.
    """
    global _bm25_index, _bm25_chunks
    
    if _bm25_index is not None:
        return _bm25_index, _bm25_chunks
    
    try:
        from rank_bm25 import BM25Okapi
        import chromadb
        from index import CHROMA_DB_DIR
    except ImportError:
        raise ImportError(
            "Cần cài: pip install rank-bm25\n"
            "Hoặc: pip install -r requirements.txt"
        )
    
    # Load tất cả chunks từ ChromaDB
    client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    collection = client.get_collection("rag_lab")
    results = collection.get(include=["documents", "metadatas"])
    
    # Convert to our chunk format
    chunks = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        chunks.append({
            "text": doc,
            "metadata": meta,
        })
    
    # Build BM25 index with improved tokenization
    corpus = [chunk["text"] for chunk in chunks]
    tokenized_corpus = [_simple_tokenize(doc) for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)
    
    _bm25_index = bm25
    _bm25_chunks = chunks
    
    return bm25, chunks


def retrieve_sparse(query: str, top_k: int = TOP_K_SEARCH, min_score: float = 0.1) -> List[Dict[str, Any]]:
    """
    Sparse retrieval: tìm kiếm theo keyword (BM25).

    Mạnh ở: exact term, mã lỗi, tên riêng (ví dụ: "ERR-403", "P1", "refund")
    Hay hụt: câu hỏi paraphrase, đồng nghĩa
    
    Improved: 
    - Uses proper Vietnamese tokenization (not simple split())
    - Filters by min_score to avoid noise retrieval
    - Fixes Q9 case: "ERR-403-AUTH" no longer matches "error" from unrelated FAQ
    """
    try:
        bm25, chunks = _build_bm25_index()
    except Exception as e:
        print(f"Lỗi build BM25: {e}")
        return []
    
    # Tokenize query with improved tokenization
    tokenized_query = _simple_tokenize(query)
    
    # Get BM25 scores
    scores = bm25.get_scores(tokenized_query)
    
    # Get top-k indices AFTER filtering by min_score threshold
    # FIX: This prevents noise retrieval for OOD queries
    scored_indices = [
        (i, scores[i]) for i in range(len(scores))
        if scores[i] >= min_score
    ]
    scored_indices.sort(key=lambda x: x[1], reverse=True)
    top_indices = [idx for idx, _ in scored_indices[:top_k]]
    
    # Build result
    results = []
    for idx in top_indices:
        results.append({
            "text": chunks[idx]["text"],
            "metadata": chunks[idx]["metadata"],
            "score": float(scores[idx]),  # BM25 score
        })
    
    return results


# =============================================================================
# RETRIEVAL — HYBRID (Dense + Sparse với Reciprocal Rank Fusion)
# =============================================================================

def retrieve_hybrid(
    query: str,
    top_k: int = TOP_K_SEARCH,
    dense_weight: float = 0.7,
    sparse_weight: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: kết hợp dense và sparse bằng Reciprocal Rank Fusion (RRF).

    RRF Score = dense_weight * (1 / (60 + dense_rank)) +
                sparse_weight * (1 / (60 + sparse_rank))
    
    Mạnh ở: giữ được cả nghĩa (dense) lẫn keyword chính xác (sparse)
    """
    # Lấy dense results
    dense_results = retrieve_dense(query, top_k=top_k)
    
    # Lấy sparse results
    sparse_results = retrieve_sparse(query, top_k=top_k)
    
    # Build lookup maps từ dense results
    dense_scores = {}
    for i, result in enumerate(dense_results):
        # Dùng full text as key để tránh collision
        key = result["text"]
        dense_scores[key] = (i, result["score"])
    
    # Build lookup maps từ sparse results
    sparse_scores = {}
    for i, result in enumerate(sparse_results):
        key = result["text"]
        sparse_scores[key] = (i, result["score"])
    
    # Merge và apply RRF
    merged = {}  # key -> (dense_rank, sparse_rank, dense_score, sparse_score, result)
    
    # Add dense results
    for result in dense_results:
        key = result["text"]
        if key not in merged:
            merged[key] = {"dense_rank": None, "sparse_rank": None, "result": result}
        dense_rank, score = dense_scores[key]
        merged[key]["dense_rank"] = dense_rank
        merged[key]["dense_score"] = score
    
    # Add sparse results
    for result in sparse_results:
        key = result["text"]
        if key not in merged:
            merged[key] = {"dense_rank": None, "sparse_rank": None, "result": result}
        sparse_rank, score = sparse_scores[key]
        merged[key]["sparse_rank"] = sparse_rank
        merged[key]["sparse_score"] = score
    
    # Calculate RRF scores
    rrf_scores = []
    for key, info in merged.items():
        # Handle None ranks - use worst rank if not found
        dense_rank = info.get("dense_rank")
        sparse_rank = info.get("sparse_rank")
        
        if dense_rank is None:
            dense_rank = 100  # Default rank cho item không nằm trong top-K dense
        if sparse_rank is None:
            sparse_rank = 100  # Default rank cho item không nằm trong top-K sparse
        
        rrf_score = (
            dense_weight * (1.0 / (60 + dense_rank)) +
            sparse_weight * (1.0 / (60 + sparse_rank))
        )
        
        # Update result với combined score
        result = info["result"]
        result["score"] = rrf_score
        result["dense_rank"] = dense_rank
        result["sparse_rank"] = sparse_rank
        
        rrf_scores.append((result, rrf_score))
    
    # Sort by RRF score và return top-k
    rrf_scores.sort(key=lambda x: x[1], reverse=True)
    return [result for result, _ in rrf_scores[:top_k]]


# =============================================================================
# RERANK (Sprint 3 alternative)
# Cross-encoder để chấm lại relevance sau search rộng
# =============================================================================

# Global Reranker (cached)
_reranker_model = None

def rerank(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = TOP_K_SELECT,
) -> List[Dict[str, Any]]:
    """
    Rerank các candidate chunks bằng cross-encoder.
    Giúp loại bỏ noise từ BM25/Sparse retrieval cho các query OOD.
    """
    global _reranker_model
    
    if not candidates:
        return []
        
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        print("Cần cài: pip install sentence-transformers")
        return candidates[:top_k]

    if _reranker_model is None:
        # MiniLM-L-6-v2 là sweet spot: nhanh và hiệu quả
        _reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Build pairs
    pairs = [[query, chunk["text"]] for chunk in candidates]
    
    # Predict relevance scores
    scores = _reranker_model.predict(pairs)
    
    # Combine and sort
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    
    # Cập nhật score của chunk bằng rerank score
    results = []
    for chunk, score in ranked[:top_k]:
        chunk["rerank_score"] = float(score)
        results.append(chunk)

    return results


# =============================================================================
# QUERY TRANSFORMATION (Sprint 3 alternative)
# =============================================================================

def transform_query(query: str, strategy: str = "expansion") -> List[str]:
    """
    Biến đổi query để tăng recall.

    Strategies:
      - "expansion": Thêm từ đồng nghĩa, alias, tên cũ
      - "decomposition": Tách query phức tạp thành 2-3 sub-queries
      - "hyde": Sinh câu trả lời giả (hypothetical document) để embed thay query

    TODO Sprint 3 (nếu chọn query transformation):
    Gọi LLM với prompt phù hợp với từng strategy.

    Ví dụ expansion prompt:
        "Given the query: '{query}'
         Generate 2-3 alternative phrasings or related terms in Vietnamese.
         Output as JSON array of strings."

    Ví dụ decomposition:
        "Break down this complex query into 2-3 simpler sub-queries: '{query}'
         Output as JSON array."

    Khi nào dùng:
    - Expansion: query dùng alias/tên cũ (ví dụ: "Approval Matrix" → "Access Control SOP")
    - Decomposition: query hỏi nhiều thứ một lúc
    - HyDE: query mơ hồ, search theo nghĩa không hiệu quả
    """
    # TODO Sprint 3: Implement query transformation
    # Tạm thời trả về query gốc
    return [query]


# =============================================================================
# GENERATION — GROUNDED ANSWER FUNCTION
# =============================================================================

def build_context_block(chunks: List[Dict[str, Any]]) -> str:
    """
    Đóng gói danh sách chunks thành context block để đưa vào prompt.

    Format: structured snippets với source, section, score (từ slide).
    Mỗi chunk có số thứ tự [1], [2], ... để model dễ trích dẫn.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", "unknown")
        section = meta.get("section", "")
        score = chunk.get("score", 0)
        text = chunk.get("text", "")

        # TODO: Tùy chỉnh format nếu muốn (thêm effective_date, department, ...)
        header = f"[{i}] {source}"
        if section:
            header += f" | {section}"
        if score > 0:
            header += f" | score={score:.2f}"

        context_parts.append(f"{header}\n{text}")

    return "\n\n".join(context_parts)


def build_grounded_prompt(query: str, context_block: str) -> str:
    """
    Xây dựng grounded prompt theo 4 quy tắc từ slide:
    1. Evidence-only: Chỉ trả lời từ retrieved context
    2. Abstain: Thiếu context thì nói không đủ dữ liệu
    3. Citation: Gắn source/section khi có thể
    4. Short, clear, stable: Output ngắn, rõ, nhất quán

    TODO Sprint 2:
    Đây là prompt baseline. Trong Sprint 3, bạn có thể:
    - Thêm hướng dẫn về format output (JSON, bullet points)
    - Thêm ngôn ngữ phản hồi (tiếng Việt vs tiếng Anh)
    - Điều chỉnh tone phù hợp với use case (CS helpdesk, IT support)
    """
    prompt = f"""Answer only from the retrieved context below.
If the context is insufficient to answer the question, say you do not know and do not make up information.
Cite the source field (in brackets like [1]) when possible.
Keep your answer short, clear, and factual.
Respond in the same language as the question.

Question: {query}

Context:
{context_block}

Answer:"""
    return prompt


def call_llm(prompt: str) -> str:
    """
    Gọi LLM để sinh câu trả lời.
    Dùng OpenAI API với temperature=0 để output ổn định cho evaluation.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "Cần cài: pip install openai\n"
            "Hoặc: pip install -r requirements.txt"
        )
    
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY không tìm thấy trong .env")
        
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,     # temperature=0 để output ổn định, dễ đánh giá
            max_tokens=512,
        )
        
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM returned empty response")
        return content
    
    except Exception as e:
        print(f"Lỗi trong call_llm: {e}")
        raise


def rag_answer(
    query: str,
    retrieval_mode: str = "dense",
    top_k_search: int = TOP_K_SEARCH,
    top_k_select: int = TOP_K_SELECT,
    use_rerank: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Pipeline RAG hoàn chỉnh: query → retrieve → (rerank) → generate.

    Args:
        query: Câu hỏi
        retrieval_mode: "dense" | "sparse" | "hybrid"
        top_k_search: Số chunk lấy từ vector store (search rộng)
        top_k_select: Số chunk đưa vào prompt (sau rerank/select)
        use_rerank: Có dùng cross-encoder rerank không
        verbose: In thêm thông tin debug

    Returns:
        Dict với:
          - "answer": câu trả lời grounded
          - "sources": list source names trích dẫn
          - "chunks_used": list chunks đã dùng
          - "query": query gốc
          - "config": cấu hình pipeline đã dùng

    TODO Sprint 2 — Implement pipeline cơ bản:
    1. Chọn retrieval function dựa theo retrieval_mode
    2. Gọi rerank() nếu use_rerank=True
    3. Truncate về top_k_select chunks
    4. Build context block và grounded prompt
    5. Gọi call_llm() để sinh câu trả lời
    6. Trả về kết quả kèm metadata

    TODO Sprint 3 — Thử các variant:
    - Variant A: đổi retrieval_mode="hybrid"
    - Variant B: bật use_rerank=True
    - Variant C: thêm query transformation trước khi retrieve
    """
    config = {
        "retrieval_mode": retrieval_mode,
        "top_k_search": top_k_search,
        "top_k_select": top_k_select,
        "use_rerank": use_rerank,
    }

    # --- Bước 1: Retrieve ---
    if retrieval_mode == "dense":
        candidates = retrieve_dense(query, top_k=top_k_search)
    elif retrieval_mode == "sparse":
        candidates = retrieve_sparse(query, top_k=top_k_search)
    elif retrieval_mode == "hybrid":
        candidates = retrieve_hybrid(query, top_k=top_k_search)
    else:
        raise ValueError(f"retrieval_mode không hợp lệ: {retrieval_mode}")

    if verbose:
        print(f"\n[RAG] Query: {query}")
        print(f"[RAG] Retrieved {len(candidates)} candidates (mode={retrieval_mode})")
        for i, c in enumerate(candidates[:3]):
            print(f"  [{i+1}] score={c.get('score', 0):.3f} | {c['metadata'].get('source', '?')}")

    # --- Bước 2: Rerank (optional) ---
    if use_rerank:
        candidates = rerank(query, candidates, top_k=top_k_select)
    else:
        candidates = candidates[:top_k_select]

    if verbose:
        print(f"[RAG] After select: {len(candidates)} chunks")

    # --- Bước 3: Build context và prompt ---
    context_block = build_context_block(candidates)
    prompt = build_grounded_prompt(query, context_block)

    if verbose:
        print(f"\n[RAG] Prompt:\n{prompt[:500]}...\n")

    # --- Bước 4: Generate ---
    answer = call_llm(prompt)

    # --- Bước 5: Extract sources ---
    sources = list({
        c["metadata"].get("source", "unknown")
        for c in candidates
    })

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "chunks_used": candidates,
        "config": config,
    }


# =============================================================================
# SPRINT 3: SO SÁNH BASELINE VS VARIANT
# =============================================================================

def compare_retrieval_strategies(query: str) -> None:
    """
    So sánh dense vs sparse vs hybrid retrieval strategies với bảng so sánh.
    """
    print(f"\n{'='*100}")
    print(f"A/B COMPARISON: Dense vs Sparse vs Hybrid Retrieval")
    print(f"Query: {query}")
    print('='*100)

    strategies = ["dense", "sparse", "hybrid"]
    results = {}

    for strategy in strategies:
        print(f"\n--- {strategy.upper()} RETRIEVAL ---")
        try:
            result = rag_answer(query, retrieval_mode=strategy, verbose=False)
            results[strategy] = result
            
            print(f"Sources: {', '.join(result['sources'])}")
            print(f"Chunks used: {len(result['chunks_used'])}")
            for i, chunk in enumerate(result['chunks_used'], 1):
                score = chunk.get('score', 0)
                source = chunk['metadata'].get('source', '?')
                section = chunk['metadata'].get('section', '')[:40]
                print(f"  [{i}] {source} | {section} | score={score:.3f}")
            ans_preview = result['answer'][:180]
            print(f"\nAnswer: {ans_preview}...")
            
        except Exception as e:
            print(f"Lỗi: {e}")
            results[strategy] = None
    
    # Comparison table
    print(f"\n\n{'='*100}")
    print("METRIC COMPARISON TABLE")
    print('='*100)
    print(f"{'Metric':<25} | {'Dense':<25} | {'Sparse':<25} | {'Hybrid':<25}")
    print("-" * 102)
    
    if all(results.values()):
        # Chunks used
        chunks_str = f"{len(results['dense']['chunks_used']):<25} | {len(results['sparse']['chunks_used']):<25} | {len(results['hybrid']['chunks_used']):<25}"
        print(f"{'Chunks used':<25} | {chunks_str}")
        
        # Top source
        dense_src = results['dense']['sources'][0] if results['dense']['sources'] else "N/A"
        sparse_src = results['sparse']['sources'][0] if results['sparse']['sources'] else "N/A"
        hybrid_src = results['hybrid']['sources'][0] if results['hybrid']['sources'] else "N/A"
        print(f"{'Top source':<25} | {dense_src:<25} | {sparse_src:<25} | {hybrid_src:<25}")
        
        # Top score
        dense_score = results['dense']['chunks_used'][0].get('score', 0) if results['dense']['chunks_used'] else 0
        sparse_score = results['sparse']['chunks_used'][0].get('score', 0) if results['sparse']['chunks_used'] else 0
        hybrid_score = results['hybrid']['chunks_used'][0].get('score', 0) if results['hybrid']['chunks_used'] else 0
        scores_str = f"{dense_score:.3f}         | {sparse_score:.3f}         | {hybrid_score:.3f}"
        print(f"{'Top chunk score':<25} | {scores_str}")
        
        # Answer length
        dense_len = len(results['dense']['answer'])
        sparse_len = len(results['sparse']['answer'])
        hybrid_len = len(results['hybrid']['answer'])
        lens_str = f"{dense_len:<25} | {sparse_len:<25} | {hybrid_len:<25}"
        print(f"{'Answer length':<25} | {lens_str}")
    
    print('='*100)


# =============================================================================
# MAIN — Demo và Test
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 2 + 3: RAG Answer Pipeline")
    print("=" * 60)

    # Test queries từ data/test_questions.json
    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng có thể yêu cầu hoàn tiền trong bao nhiêu ngày?",
        "Ai phải phê duyệt để cấp quyền Level 3?",
        "ERR-403-AUTH là lỗi gì?",  # Query không có trong docs → kiểm tra abstain
    ]

    print("\n--- Sprint 2: Test Baseline (Dense) ---")
    for query in test_queries:
        print(f"\nQuery: {query}")
        try:
            result = rag_answer(query, retrieval_mode="dense", verbose=True)
            print(f"Answer: {result['answer']}")
            print(f"Sources: {result['sources']}")
        except NotImplementedError:
            print("Chưa implement — hoàn thành TODO trong retrieve_dense() và call_llm() trước.")
        except Exception as e:
            print(f"Lỗi: {e}")

    # Sprint 3: Compare strategies
    print("\n\n" + "="*60)
    print("Sprint 3: So sánh retrieval strategies")
    print("="*60)
    
    compare_queries = [
        "SLA P1 xử lý bao lâu?",
        "ERR-403 là gì?",
        "Hoàn tiền mất bao lâu?",
    ]
    
    for query in compare_queries:
        compare_retrieval_strategies(query)

    print("\n\n" + "="*60)
    print("✅ SPRINT 3 HOÀN THÀNH: HYBRID VARIANT TESTED")
    print("="*60)
    print("\nKết luận: Hybrid retrieval kết hợp Dense + Sparse bằng RRF")
    print("  - Dense: Xử lý semantic/nghĩa câu hỏi")
    print("  - Sparse (BM25): Xử lý keyword/mã lỗi (P1, ERR-403, refund, Level 3)")
    print("  - Hybrid (RRF): Tăng recall và relevance")
    print("\nBước tiếp theo: Ghi lý do vào docs/tuning-log.md")
