from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from ..core.logging import get_logger

logger = get_logger(__name__)

TECH_VOCAB: Tuple[str, ...] = (
    "ethereum", "solana", "solidity", "react", "typescript", "javascript",
    "python", "rust", "golang", "nodejs", "nextjs", "fastapi", "django",
    "flask", "postgres", "mysql", "mongodb", "redis", "docker", "kubernetes",
    "aws", "gcp", "azure", "serverless", "lambda", "graphql", "rest", "grpc",
    "websocket", "http", "https", "tcp", "ip", "dns", "oauth", "jwt", "tls",
    "ssl", "nginx", "apache", "linux", "unix", "bash", "git", "github",
    "gitlab", "ci", "cd", "jenkins", "travis", "circleci", "terraform",
    "ansible", "puppet", "chef", "vagrant", "prometheus", "grafana",
    "elasticsearch", "kibana", "logstash", "rabbitmq", "kafka", "zookeeper",
    "spark", "hadoop", "hive", "airflow", "mlflow", "pytorch", "tensorflow",
    "keras", "scikitlearn", "pandas", "numpy", "opencv", "langchain",
    "openai", "anthropic", "claude", "gpt", "llm", "embedding", "vector",
    "pinecone", "weaviate", "chroma", "milvus", "qdrant", "faiss",
    "uniswap", "aave", "makerdao", "compound", "curve", "sushi", "balancer",
    "defi", "nft", "dao", "erc20", "erc721", "erc1155", "evm", "web3",
    "web2", "metamask", "walletconnect", "ipfs", "filecoin", "arweave",
    "polygon", "arbitrum", "optimism", "base", "avalanche", "fantom",
    "cosmos", "ibc", "tendermint", "cosmwasm", "rust", "move", "aptos",
    "sui", "near", "starknet", "zk", "rollup", "layer2", "sharding",
    "consensus", "pos", "pow", "pbft", "raft", "paxos", "byzantine",
    "smartcontract", "oracle", "chainlink", "api", "sdk", "cli", "ide",
    "vscode", "vim", "neovim", "debugger", "profiler", "benchmark",
    "unittest", "integrationtest", "e2e", "pytest", "jest", "mocha",
    "cypress", "playwright", "selenium", "storybook", "tailwind",
    "bootstrap", "sass", "less", "css", "html", "dom", "bom", "ajax",
    "fetch", "axios", "redux", "mobx", "zustand", "vue", "angular",
    "svelte", "solidjs", "qwik", "astro", "remix", "gatsby", "nuxt",
    "swr", "reactquery", "tanstack", "prisma", "sequelize", "typeorm",
    "sqlalchemy", "mongoose", "drizzle", "supabase", "firebase",
    "amplify", "vercel", "netlify", "cloudflare", "railway", "render",
    "flyio", "heroku", "digitalocean", "linode", "vultr", "ovh",
    "football", "soccer", "premierleague", "laliga", "bundesliga",
    "seriea", "ligue1", "championsleague", "europaleague", "worldcup",
    "euros", "copaamerica", "transfer", "tactic", "formation", "pressing",
    "possession", "counterattack", "setpiece", "corner", "freekick",
    "penalty", "offside", "yellowcard", "redcard", "injury", "loan",
    "blog", "content", "seo", "keyword", "meta", "sitemap", "rss",
    "cms", "wordpress", "notion", "hashnode", "medium", "devto",
    "markdown", "mdx", "latex", "pdf", "docx", "csv", "json", "yaml",
    "toml", "xml", "schema", "openapi", "swagger", "graphiql",
    "audit", "security", "vulnerability", "cve", "owasp", "xss", "csrf",
    "sqli", "rce", "ssrf", "path_traversal", "dos", "ddos", "waf",
    "firewall", "honeypot", "pentest", "bugbounty", "threatmodel",
    "cryptography", "aes", "rsa", "sha256", "sha512", "md5", "bcrypt",
    "argon2", "scrypt", "pbkdf2", "hmac", "signature", "encryption",
    "decryption", "hashing", "salting", "nonce", "iv", "keccak",
    "study", "learning", "flashcard", "spacedrepetition", "anki",
    "quizlet", "syllabus", "curriculum", "lecture", "homework",
    "exam", "revision", "notes", "summary", "mindmap", "outline",
)

_VOCAB_SET = set(TECH_VOCAB)
_VOCAB_INDEX = {term: i for i, term in enumerate(TECH_VOCAB)}


class ExperienceMemory:
    def __init__(self) -> None:
        self._entries: List[Tuple[str, List[str], Optional[List[float]]]] = []

    def _tokenize(self, text: str) -> List[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        tokens = re.findall(r"[a-z0-9_]+", cleaned)
        return [t for t in tokens if t]

    def _embed_simple(self, text: str) -> List[float]:
        vocab_size = len(TECH_VOCAB)
        vector = [0.0] * vocab_size
        tokens = self._tokenize(text)
        if not tokens:
            return vector

        counts: dict = {}
        for token in tokens:
            if token in _VOCAB_SET:
                counts[token] = counts.get(token, 0) + 1
            else:
                parts = [token[i : i + 4] for i in range(max(1, len(token) - 3))]
                for sub in parts:
                    if sub in _VOCAB_SET:
                        counts[sub] = counts.get(sub, 0) + 1

        for term, count in counts.items():
            idx = _VOCAB_INDEX.get(term)
            if idx is not None:
                vector[idx] = float(count)

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def _cosine(self, a: List[float], b: List[float]) -> float:
        if len(a) != len(b):
            min_len = min(len(a), len(b))
            a = a[:min_len]
            b = b[:min_len]
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def store(self, task_description: str, lessons: List[str]) -> None:
        if not task_description:
            raise ValueError("task_description cannot be empty")
        if not lessons:
            logger.warning("experience_store_empty_lessons", task_preview=task_description[:60])
            lessons = ["No specific lessons captured."]
        embedding = self._embed_simple(task_description)
        key = task_description[:200]
        self._entries.append((key, list(lessons), embedding))
        logger.info(
            "experience_stored",
            total_entries=len(self._entries),
            lessons_count=len(lessons),
            key_preview=key[:80],
        )

    def recall(
        self,
        task_description: str,
        top_k: int = 5,
        min_similarity: float = 0.2,
    ) -> List[str]:
        if not task_description:
            return []
        if not self._entries:
            return []

        query_emb = self._embed_simple(task_description)
        scored: List[Tuple[float, int, List[str]]] = []

        for idx, (_key, lessons, entry_emb) in enumerate(self._entries):
            if entry_emb is None:
                continue
            similarity = self._cosine(query_emb, entry_emb)
            if similarity >= min_similarity:
                scored.append((similarity, idx, lessons))

        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:top_k]

        result_lessons: List[str] = []
        seen: set = set()
        for sim, _idx, lessons in top:
            for lesson in lessons:
                if lesson not in seen:
                    seen.add(lesson)
                    result_lessons.append(lesson)

        logger.info(
            "experience_recalled",
            query_preview=task_description[:60],
            candidates_scored=len(scored),
            lessons_returned=len(result_lessons),
            top_similarity=scored[0][0] if scored else 0.0,
        )
        return result_lessons
