import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any
from loguru import logger

class BM25Memory:
    """Pure Python Okapi BM25 Semantic Search for RAG without external dependencies.
    Provides highly optimized sparse vector retrieval, fully replacing C++ Vector DBs.
    """
    
    # Standard BM25 hyperparameters
    K1 = 1.5
    B = 0.75

    # Phase 3: Speed Optimization - RAM Cache
    _CACHE: Dict[Path, Dict[str, Any]] = {}

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.db_path = workspace / "memory" / "bm25_db.json"
        
        # In-memory indices
        self.documents: Dict[str, str] = {}
        self.metadata: Dict[str, dict] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.term_freqs: Dict[str, Counter] = {}
        self.doc_freqs: Counter = Counter()
        self.avg_doc_length: float = 0.0
        
        self.load()

    def _tokenize(self, text: str) -> List[str]:
        """Simple and fast regex-based tokenizer."""
        text = text.lower()
        # Remove markdown symbols and punctuation, keep alphanumeric words
        words = re.findall(r'\b\w+\b', text)
        return words

    def _recalculate_stats(self):
        """Update average document length and doc frequencies."""
        total_len = sum(self.doc_lengths.values())
        N = len(self.documents)
        self.avg_doc_length = total_len / N if N > 0 else 0.0
        
        self.doc_freqs.clear()
        for tfs in self.term_freqs.values():
            for term in tfs.keys():
                self.doc_freqs[term] += 1

    def add_memory(self, doc_id: str, content: str, meta: Dict[str, Any] = None):
        """Add a document to the BM25 index."""
        try:
            tokens = self._tokenize(content)
            if not tokens:
                return
                
            self.documents[doc_id] = content
            self.metadata[doc_id] = meta or {}
            self.doc_lengths[doc_id] = len(tokens)
            self.term_freqs[doc_id] = Counter(tokens)
            
            self._recalculate_stats()
            self.save()
            logger.info(f"BM25 Memory indexed: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to add BM25 memory {doc_id}: {e}")

    def search(self, query: str, top_k: int = 3) -> List[str]:
        """Rank documents using Okapi BM25 formula."""
        if not self.documents:
            return []
            
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: Dict[str, float] = {doc_id: 0.0 for doc_id in self.documents}
        N = len(self.documents)
        
        for term in query_tokens:
            if term not in self.doc_freqs:
                continue
                
            # Inverse Document Frequency (IDF) with BM25 smoothing
            df = self.doc_freqs[term]
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            
            for doc_id, tf_counter in self.term_freqs.items():
                if term in tf_counter:
                    tf = tf_counter[term]
                    doc_len = self.doc_lengths[doc_id]
                    
                    # Term Frequency (TF) normalization
                    norm_tf = (tf * (self.K1 + 1)) / (tf + self.K1 * (1 - self.B + self.B * (doc_len / self.avg_doc_length)))
                    scores[doc_id] += idf * norm_tf

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        
        # Filter out 0 score results
        results = [self.documents[doc_id] for doc_id, score in ranked if score > 0]
        return results[:top_k]

    def save(self):
        """Persist index to disk."""
        try:
            data = {
                "documents": self.documents,
                "metadata": self.metadata,
                "doc_lengths": self.doc_lengths,
                # Convert Counters to standard dicts for JSON serialization
                "term_freqs": {k: dict(v) for k, v in self.term_freqs.items()},
            }
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save BM25 memory: {e}")

    def load(self):
        """Load index from disk."""
        if not self.db_path.exists():
            return
            
        try:
            import os
            mtime = os.path.getmtime(self.db_path)
            
            # Use RAM cache if file hasn't changed
            cache_entry = self._CACHE.get(self.db_path)
            if cache_entry and cache_entry["mtime"] == mtime:
                self.documents = cache_entry["documents"].copy()
                self.metadata = cache_entry["metadata"].copy()
                self.doc_lengths = cache_entry["doc_lengths"].copy()
                self.term_freqs = {k: Counter(v) for k, v in cache_entry["term_freqs"].items()}
                self._recalculate_stats()
                return

            content = self.db_path.read_text(encoding="utf-8")
            data = json.loads(content)
            self.documents = data.get("documents", {})
            self.metadata = data.get("metadata", {})
            self.doc_lengths = data.get("doc_lengths", {})
            
            tf_data = data.get("term_freqs", {})
            self.term_freqs = {k: Counter(v) for k, v in tf_data.items()}
            
            self._recalculate_stats()
            
            # Update RAM cache
            self._CACHE[self.db_path] = {
                "mtime": mtime,
                "documents": self.documents.copy(),
                "metadata": self.metadata.copy(),
                "doc_lengths": self.doc_lengths.copy(),
                "term_freqs": {k: dict(v) for k, v in self.term_freqs.items()}
            }
            
            logger.info(f"Loaded {len(self.documents)} BM25 memories into RAM cache.")
        except Exception as e:
            logger.error(f"Failed to load BM25 memory: {e}")

    def clear(self):
        """Clear all memories."""
        self.documents.clear()
        self.metadata.clear()
        self.doc_lengths.clear()
        self.term_freqs.clear()
        self.doc_freqs.clear()
        self.avg_doc_length = 0.0
        if self.db_path.exists():
            self.db_path.unlink()
        logger.info("Cleared all BM25 memories.")
