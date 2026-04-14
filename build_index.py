import chromadb, os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client_db = chromadb.PersistentClient(path='./chroma_db')
col = client_db.get_or_create_collection('day09_docs', metadata={'hnsw:space': 'cosine'})
openai_client = OpenAI()

docs_dir = './data/docs'
all_files = os.listdir(docs_dir)
print(f'Found {len(all_files)} docs to index')

for fname in all_files:
    fpath = os.path.join(docs_dir, fname)
    with open(fpath, encoding='utf-8') as f:
        content = f.read()
    # Chunk: split theo paragraph (>50 chars)
    chunks = [p.strip() for p in content.split('\n\n') if len(p.strip()) > 50]
    print(f'Indexing {fname}: {len(chunks)} chunks')
    for j, chunk in enumerate(chunks):
        emb = openai_client.embeddings.create(input=chunk, model='text-embedding-3-small').data[0].embedding
        doc_id = f'{fname}_{j}'
        col.upsert(documents=[chunk], embeddings=[emb], ids=[doc_id], metadatas=[{'source': fname}])
    print(f'  Done: {fname}')
print('Index ready! Total docs:', col.count())
