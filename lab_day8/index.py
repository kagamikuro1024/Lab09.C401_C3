"""
index.py — Sprint 1: Build RAG Index
====================================
Mục tiêu Sprint 1 (60 phút):
  - Đọc và preprocess tài liệu từ data/docs/
  - Chunk tài liệu theo cấu trúc tự nhiên (heading/section)
  - Gắn metadata: source, section, department, effective_date, access
  - Embed và lưu vào vector store (ChromaDB)

Definition of Done Sprint 1:
  ✓ Script chạy được và index đủ docs
  ✓ Có ít nhất 3 metadata fields hữu ích cho retrieval
  ✓ Có thể kiểm tra chunk bằng list_chunks()
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CẤU HÌNH
# =============================================================================

DOCS_DIR = Path(__file__).parent / "data" / "docs"
CHROMA_DB_DIR = Path(__file__).parent / "chroma_db"

# TODO Sprint 1: Điều chỉnh chunk size và overlap theo quyết định của nhóm
# Gợi ý từ slide: chunk 300-500 tokens, overlap 50-80 tokens
CHUNK_SIZE = 400       # tokens (ước lượng bằng số ký tự / 4)
CHUNK_OVERLAP = 80     # tokens overlap giữa các chunk


# =============================================================================
# STEP 1: PREPROCESS
# Làm sạch text trước khi chunk và embed
# =============================================================================

def preprocess_document(raw_text: str, filepath: str) -> Dict[str, Any]:
    """
    Preprocess một tài liệu: extract metadata từ header và làm sạch nội dung.

    Format đầu file:
      TIÊU ĐỀ
      Source: ...
      Department: ...
      Effective Date: ...
      Access: ...
      
      === SECTION 1 ===
      ...
    """
    lines = raw_text.strip().split("\n")
    metadata = {
        "source": Path(filepath).name,  # Fallback: filename
        "section": "",
        "department": "unknown",
        "effective_date": "unknown",
        "access": "internal",
    }
    content_lines = []
    header_done = False

    for line in lines:
        if not header_done:
            # Parse metadata từ dòng "Key: Value"
            if line.startswith("Source:"):
                metadata["source"] = line.replace("Source:", "").strip()
            elif line.startswith("Department:"):
                metadata["department"] = line.replace("Department:", "").strip()
            elif line.startswith("Effective Date:"):
                metadata["effective_date"] = line.replace("Effective Date:", "").strip()
            elif line.startswith("Access:"):
                metadata["access"] = line.replace("Access:", "").strip()
            elif line.startswith("==="):
                # Gặp section heading đầu tiên → kết thúc header
                header_done = True
                content_lines.append(line)
            elif line.strip() == "" or (line.isupper() and len(line) > 3):
                # Bỏ tiêu đề và dòng trống header
                continue
        else:
            content_lines.append(line)

    cleaned_text = "\n".join(content_lines)
    # Chuẩn hóa dòng trống: max 2 dòng liên tiếp
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return {
        "text": cleaned_text,
        "metadata": metadata,
    }


# =============================================================================
# STEP 2: CHUNK
# Chia tài liệu thành các đoạn nhỏ theo cấu trúc tự nhiên
# =============================================================================

def chunk_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Chunk một tài liệu đã preprocess thành danh sách các chunk nhỏ.
    Cắt theo section heading trước, rồi split section dài thành multiple chunks.
    Mỗi chunk giữ đầy đủ metadata.
    """
    text = doc["text"]
    base_metadata = doc["metadata"].copy()
    chunks = []

    # Split theo heading pattern "=== ... ==="
    sections = re.split(r"(===.*?===)", text)

    current_section = "General"
    current_section_text = ""

    for part in sections:
        if re.match(r"^===.*?===$", part.strip()):
            # Lưu section trước
            if current_section_text.strip():
                section_chunks = _split_by_size(
                    current_section_text.strip(),
                    base_metadata=base_metadata,
                    section=current_section,
                )
                chunks.extend(section_chunks)
            # Bắt đầu section mới
            current_section = part.strip("= ").strip()
            current_section_text = ""
        else:
            current_section_text += part

    # Lưu section cuối cùng
    if current_section_text.strip():
        section_chunks = _split_by_size(
            current_section_text.strip(),
            base_metadata=base_metadata,
            section=current_section,
        )
        chunks.extend(section_chunks)

    return chunks


def _split_by_size(
    text: str,
    base_metadata: Dict,
    section: str,
    chunk_chars: int = CHUNK_SIZE * 4,
    overlap_chars: int = CHUNK_OVERLAP * 4,
) -> List[Dict[str, Any]]:
    """
    Helper: Split text dài thành chunks với overlap.
    Ưu tiên cắt tại paragraph boundary (\n\n) để tránh cắt giữa câu.
    """
    if len(text) <= chunk_chars:
        # Toàn bộ section vừa một chunk
        return [{
            "text": text,
            "metadata": {**base_metadata, "section": section},
        }]

    # Split theo paragraph
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_length = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for "\n\n"
        
        # Nếu paragraph quá dài, split it
        if para_len > chunk_chars:
            # Nếu chunk hiện tại có nội dung, lưu lại trước
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "metadata": {**base_metadata, "section": section},
                })
                current_chunk = []
                current_length = 0
            
            # Split paragraph dài thành chuỗi con
            sub_chunks = _split_long_paragraph(para, chunk_chars)
            for i, sub_chunk in enumerate(sub_chunks):
                if i > 0 and chunks:
                    # Thêm overlap từ chunk trước
                    prev_chunk_text = chunks[-1]["text"]
                    overlap = prev_chunk_text[-overlap_chars:] if len(prev_chunk_text) > overlap_chars else prev_chunk_text
                    sub_chunk = overlap + "\n\n" + sub_chunk
                chunks.append({
                    "text": sub_chunk,
                    "metadata": {**base_metadata, "section": section},
                })
        else:
            # Thêm paragraph vào chunk hiện tại
            if current_length + para_len > chunk_chars and current_chunk:
                # Chunk hiện tại đủ rồi, lưu và bắt đầu chunk mới
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "metadata": {**base_metadata, "section": section},
                })
                # Thêm overlap
                overlap = chunk_text[-overlap_chars:] if len(chunk_text) > overlap_chars else chunk_text
                current_chunk = [overlap, para] if overlap else [para]
                current_length = len(overlap) + 2 + para_len
            else:
                current_chunk.append(para)
                current_length += para_len

    # Lưu chunk cuối cùng
    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        chunks.append({
            "text": chunk_text,
            "metadata": {**base_metadata, "section": section},
        })

    return chunks


def _split_long_paragraph(
    text: str,
    max_chars: int,
) -> List[str]:
    """
    Helper: Split một paragraph dài thành chuỗi con (dựa vào dấu câu).
    """
    if len(text) <= max_chars:
        return [text]
    
    # Split theo dấu chấm
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = []
    current_len = 0
    
    for sent in sentences:
        sent_len = len(sent) + 1  # +1 for space
        if current_len + sent_len > max_chars and current:
            chunks.append(" ".join(current))
            current = [sent]
            current_len = sent_len
        else:
            current.append(sent)
            current_len += sent_len
    
    if current:
        chunks.append(" ".join(current))
    
    return chunks


# =============================================================================
# STEP 3: EMBED + STORE
# Embed các chunk và lưu vào ChromaDB
# =============================================================================

# Global OpenAI client (load once)
_openai_client = None

def get_embedding(text: str) -> List[float]:
    """
    Tạo embedding vector cho một đoạn text.
    Dùng OpenAI API (cần OPENAI_API_KEY trong .env).
    """
    global _openai_client
    if _openai_client is None:
        print("  [init] Loading OpenAI client...")
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY không tìm thấy trong .env")
            _openai_client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError(
                "Cần cài: pip install openai\n"
                "Hoặc: pip install -r requirements.txt"
            )
    
    try:
        response = _openai_client.embeddings.create(
            input=text,
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Lỗi khi embed: {e}")
        raise


def build_index(docs_dir: Path = DOCS_DIR, db_dir: Path = CHROMA_DB_DIR) -> None:
    """
    Pipeline hoàn chỉnh: đọc docs → preprocess → chunk → embed → store.
    """
    try:
        import chromadb
    except ImportError:
        raise ImportError(
            "Cần cài: pip install chromadb\n"
            "Hoặc: pip install -r requirements.txt"
        )

    print(f"\n=== BUILD INDEX ===")
    print(f"Docs dir: {docs_dir}")
    db_dir.mkdir(parents=True, exist_ok=True)

    # Khởi tạo ChromaDB
    client = chromadb.PersistentClient(path=str(db_dir))
    collection = client.get_or_create_collection(
        name="rag_lab",
        metadata={"hnsw:space": "cosine"}
    )

    total_chunks = 0
    doc_files = sorted(docs_dir.glob("*.txt"))

    if not doc_files:
        print(f"Lỗi: Không tìm thấy file .txt trong {docs_dir}")
        return

    print(f"Tìm thấy {len(doc_files)} files:")
    for filepath in doc_files:
        print(f"\n  Processing: {filepath.name}")
        try:
            raw_text = filepath.read_text(encoding="utf-8")
            doc = preprocess_document(raw_text, str(filepath))
            chunks = chunk_document(doc)

            print(f"    Metadata: {doc['metadata']}")
            print(f"    Chunks: {len(chunks)}")

            # Embed và upsert từng chunk
            for i, chunk in enumerate(chunks):
                chunk_id = f"{filepath.stem}_{i}"
                embedding = get_embedding(chunk["text"])
                
                collection.upsert(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk["text"]],
                    metadatas=[chunk["metadata"]],
                )
            
            total_chunks += len(chunks)
            print(f"    ✓ Upserted {len(chunks)} chunks")
        except Exception as e:
            print(f"    ✗ Lỗi: {e}")
            raise

    print(f"\n{'='*50}")
    print(f"✓ Hoàn thành! Index chứa {total_chunks} chunks")
    print(f"Lưu tại: {db_dir}")
    print(f"{'='*50}\n")


# =============================================================================
# STEP 4: INSPECT / KIỂM TRA
# Dùng để debug và kiểm tra chất lượng index
# =============================================================================

def list_chunks(db_dir: Path = CHROMA_DB_DIR, n: int = 5) -> None:
    """
    In ra n chunk đầu tiên trong ChromaDB để kiểm tra chất lượng index.
    """
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(db_dir))
        collection = client.get_collection("rag_lab")
        results = collection.get(limit=n, include=["documents", "metadatas"])

        print(f"\n=== Top {n} chunks trong index ===")
        print(f"Tổng chunks: {collection.count()}\n")
        
        for i, (doc, meta) in enumerate(zip(results["documents"], results["metadatas"])):
            print(f"[Chunk {i+1}]")
            print(f"  Source: {meta.get('source', 'N/A')}")
            print(f"  Section: {meta.get('section', 'N/A')}")
            print(f"  Effective Date: {meta.get('effective_date', 'N/A')}")
            print(f"  Department: {meta.get('department', 'N/A')}")
            print(f"  Access: {meta.get('access', 'N/A')}")
            print(f"  Text ({len(doc)} chars): {doc[:150]}...")
            print()
    except Exception as e:
        print(f"\n✗ Lỗi: {e}")
        print("Hãy chạy build_index() trước.\n")


def inspect_metadata_coverage(db_dir: Path = CHROMA_DB_DIR) -> None:
    """
    Kiểm tra phân phối metadata trong toàn bộ index.
    """
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(db_dir))
        collection = client.get_collection("rag_lab")
        results = collection.get(include=["metadatas"])

        print(f"\n=== METADATA COVERAGE ===")
        print(f"Tổng chunks: {len(results['metadatas'])}\n")

        # Phân tích metadata
        departments = {}
        sources = {}
        missing_date = 0
        access_levels = {}
        
        for meta in results["metadatas"]:
            dept = meta.get("department", "unknown")
            source = meta.get("source", "unknown")
            access = meta.get("access", "unknown")
            
            departments[dept] = departments.get(dept, 0) + 1
            sources[source] = sources.get(source, 0) + 1
            access_levels[access] = access_levels.get(access, 0) + 1
            
            if meta.get("effective_date") in ("unknown", "", None):
                missing_date += 1

        print("Phân bố theo Department:")
        for dept, count in sorted(departments.items()):
            print(f"  {dept}: {count} chunks")
        
        print("\nPhân bố theo Source:")
        for source, count in sorted(sources.items()):
            print(f"  {source}: {count} chunks")
        
        print("\nPhân bố theo Access Level:")
        for access, count in sorted(access_levels.items()):
            print(f"  {access}: {count} chunks")
        
        print(f"\nMissing effective_date: {missing_date} chunks")
        
        if missing_date > 0:
            print("⚠️  Cảnh báo: Có chunks thiếu effective_date!")
        else:
            print("✓ Tất cả chunks có đủ metadata")
        print()

    except Exception as e:
        print(f"\n✗ Lỗi: {e}")
        print("Hãy chạy build_index() trước.\n")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Sprint 1: Build RAG Index")
    print("=" * 70)

    # Bước 1: Kiểm tra docs
    doc_files = list(DOCS_DIR.glob("*.txt"))
    print(f"\nBước 1: Kiểm tra tài liệu")
    print(f"Tìm thấy {len(doc_files)} files trong {DOCS_DIR}:")
    for f in sorted(doc_files):
        size = f.stat().st_size
        print(f"  ✓ {f.name} ({size} bytes)")

    # Bước 2: Test preprocess + chunking
    print("\nBước 2: Test preprocess + chunking")
    for filepath in sorted(doc_files)[:1]:  # Test file đầu tiên
        print(f"\nTest file: {filepath.name}")
        raw = filepath.read_text(encoding="utf-8")
        doc = preprocess_document(raw, str(filepath))
        chunks = chunk_document(doc)
        
        print(f"  Metadata: {doc['metadata']}")
        print(f"  Tổng text len: {len(doc['text'])} chars")
        print(f"  Tổng chunks: {len(chunks)}")
        
        for i, chunk in enumerate(chunks[:3]):
            print(f"\n  [Chunk {i+1}]")
            print(f"    Section: {chunk['metadata']['section']}")
            print(f"    Length: {len(chunk['text'])} chars")
            print(f"    Text: {chunk['text'][:100]}...")

    # Bước 3: Build full index
    print("\n\nBước 3: Build index hoàn chỉnh")
    try:
        build_index()
        
        # Bước 4: Inspect index
        print("\nBước 4: Kiểm tra index quality")
        list_chunks(n=3)
        inspect_metadata_coverage()
        
        print("\n✅ SPRINT 1 HOÀN THÀNH!")
        print("Bước tiếp theo: Implement retrieval functions trong rag_answer.py")
        
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
