# -*- coding: utf-8 -*-
"""
MilvusClient — Parent-Child 双层向量检索引擎
==============================================

基于 pymilvus (v2.3+) 的工业级封装，实现赛题要求的 Parent-Child 双层映射策略：

  - Child Collection (子块层):  小粒度文本切片 (250-500 tokens)，使用稠密向量
    进行高性能 Top-K 语义召回，命中相关片段。
  - Parent Collection (父块层): 大粒度文本切片 (1000-2000 tokens)，存储完整
    学术上下文。子块召回到的 parent_id 用于反查父块，将完整上下文注入大模型
    Prompt，从根本上消除信息碎片化引起的幻觉。

功能矩阵：
  1. Collection 生命周期管理 (create / drop / flush / compact)
  2. Embedding 生成接口 (可插拔：讯飞星火 Embedding / OpenAI / 本地 ONNX)
  3. 子块批量插入 + 父块关联写入
  4. 子块向量检索 → Parent Lookup → 完整上下文返回
  5. 混合检索支持 (Dense Vector + Scalar Filtering by difficulty/category)
  6. 检索去重与动态 Top-K 截断

依赖声明：
  本模块使用 pymilvus 官方 SDK，遵循 Apache 2.0 开源协议。
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 配置模型
# ============================================================================

class MilvusConfig(BaseModel):
    """Milvus 连接与 Collection 配置。"""

    # 连接
    host: str = Field(default="localhost", description="Milvus 服务主机地址")
    port: int = Field(default=19530, ge=1, le=65535, description="Milvus gRPC 端口")
    alias: str = Field(default="default", description="Milvus 连接别名")

    # Collection 名称
    child_collection_name: str = Field(default="edu_child_chunks", description="子块 Collection 名称")
    parent_collection_name: str = Field(default="edu_parent_chunks", description="父块 Collection 名称")

    # 向量维度（取决于 Embedding 模型输出）
    embedding_dim: int = Field(default=1536, ge=64, le=8192, description="向量维度")

    # 索引
    index_type: str = Field(default="IVF_FLAT", description="向量索引类型")
    metric_type: str = Field(default="IP", description="相似度度量: IP / L2 / COSINE")
    nlist: int = Field(default=1024, ge=1, description="IVF 聚类中心数量")

    # 搜索
    default_top_k: int = Field(default=10, ge=1, le=100, description="默认 Top-K 检索数量")
    search_nprobe: int = Field(default=32, ge=1, description="搜索时探测的聚类数")

    # 父块合并
    max_parents_per_query: int = Field(default=5, ge=1, le=20, description="每次查询返回的最大父块数")


# ============================================================================
# 数据模型
# ============================================================================

class ParentChunk(BaseModel):
    """父块 — 大粒度完整学术上下文。"""

    parent_id: str = Field(..., min_length=1, description="父块唯一 ID")
    node_id: str = Field(..., description="关联的知识点 ID (Neo4j)")
    content: str = Field(..., description="完整学术文本 (1000-2000 tokens)")
    title: str = Field(default="", description="文档/章节标题")
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    category: str = Field(default="concept")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    child_ids: List[str] = Field(default_factory=list, description="关联的子块 ID 列表")


class ChildChunk(BaseModel):
    """子块 — 小粒度高召回文本切片。"""

    child_id: str = Field(..., min_length=1, description="子块唯一 ID")
    parent_id: str = Field(..., description="关联的父块 ID")
    node_id: str = Field(..., description="关联的知识点 ID (Neo4j)")
    content: str = Field(..., description="文本切片 (250-500 tokens)")
    embedding: Optional[List[float]] = Field(default=None, description="向量嵌入")
    chunk_index: int = Field(default=0, ge=0, description="在原文档中的切片序号")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """单条向量检索命中记录。"""

    child_id: str = Field(..., description="命中的子块 ID")
    parent_id: str = Field(..., description="关联的父块 ID")
    node_id: str = Field(..., description="关联的知识点 ID")
    score: float = Field(..., description="相似度分数")
    child_content: str = Field(default="", description="子块文本片段")
    child_chunk_index: int = Field(default=0, description="切片序号")


class ChunkSearchResult(BaseModel):
    """完整的向量检索结果 — 子块召回 + 父块上下文合并。"""

    query: str = Field(default="", description="原始查询文本")
    child_hits: List[SearchResult] = Field(default_factory=list, description="子块命中列表")
    parent_contexts: List[ParentChunk] = Field(
        default_factory=list,
        description="去重后的父块完整上下文列表"
    )
    total_child_hits: int = Field(default=0, description="原始子块命中总数（去重前）")
    search_latency_ms: float = Field(default=0.0, description="检索耗时（毫秒）")


# ============================================================================
# Milvus 客户端
# ============================================================================

class MilvusClient:
    """Milvus 向量数据库客户端 — Parent-Child 双层检索。

    检索流程:
      1. 在 Child Collection 中进行稠密向量 Top-K 搜索
      2. 收集命中子块的 parent_id 集合（去重）
      3. 通过 parent_id 在 Parent Collection 中获取完整上下文
      4. 返回 ChunkSearchResult（子块命中 + 父块上下文）

    使用示例:
        >>> config = MilvusConfig()
        >>> client = MilvusClient(config)
        >>> client.connect()
        >>> client.create_collections()
        >>> # 插入父块
        >>> parent = ParentChunk(parent_id="P1", node_id="N1", content="...")
        >>> client.insert_parent(parent)
        >>> # 插入子块
        >>> child = ChildChunk(child_id="C1", parent_id="P1", node_id="N1", content="...")
        >>> client.insert_child(child)
        >>> # 检索
        >>> result = client.search("什么是反向传播？")
        >>> for ctx in result.parent_contexts:
        ...     print(ctx.content)
    """

    # ------------------------------------------------------------------
    # 构造与生命周期
    # ------------------------------------------------------------------

    def __init__(self, config: Optional[MilvusConfig] = None) -> None:
        self._config = config or MilvusConfig()
        self._connected: bool = False
        # pymilvus 对象延迟初始化
        self._milvus: Any = None
        # Embedding 函数（可注入）
        self._embed_fn: Optional[Callable[[str], List[float]]] = None
        self._batch_embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None

    @property
    def config(self) -> MilvusConfig:
        return self._config

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """建立与 Milvus 的 gRPC 连接。"""
        try:
            from pymilvus import connections
        except ImportError:
            raise ImportError("pymilvus 未安装。请执行: pip install pymilvus")
        connections.connect(
            alias=self._config.alias,
            host=self._config.host,
            port=self._config.port,
        )
        self._connected = True

    def disconnect(self) -> None:
        """断开与 Milvus 的连接。"""
        if self._connected:
            try:
                from pymilvus import connections
                connections.disconnect(self._config.alias)
            except Exception:
                pass
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("MilvusClient 未连接。请先调用 connect()。")

    # ------------------------------------------------------------------
    # Embedding 函数注入
    # ------------------------------------------------------------------

    def set_embedding_function(
        self,
        embed_fn: Callable[[str], List[float]],
        batch_embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None,
    ) -> None:
        """注入文本向量化函数（适配各类 Embedding 模型）。

        Args:
            embed_fn: 单文本 → 向量（List[float]）。
            batch_embed_fn: 批量文本 → 向量列表。
        """
        self._embed_fn = embed_fn
        self._batch_embed_fn = batch_embed_fn

    def embed_text(self, text: str) -> List[float]:
        """对单段文本生成向量嵌入。"""
        if self._embed_fn is None:
            raise RuntimeError("Embedding 函数未注入。请先调用 set_embedding_function()。")
        return self._embed_fn(text)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量文本向量化。"""
        if self._batch_embed_fn is not None:
            return self._batch_embed_fn(texts)
        if self._embed_fn is not None:
            return [self._embed_fn(t) for t in texts]
        raise RuntimeError("Embedding 函数未注入。请先调用 set_embedding_function()。")

    # ------------------------------------------------------------------
    # Collection 生命周期
    # ------------------------------------------------------------------

    def create_collections(self) -> None:
        """创建 Child 和 Parent 两个 Collection。

        Child Collection Schema:
          - child_id (VARCHAR, primary)
          - parent_id (VARCHAR)
          - node_id (VARCHAR)
          - content (VARCHAR)
          - chunk_index (INT64)
          - embedding (FLOAT_VECTOR)

        Parent Collection Schema:
          - parent_id (VARCHAR, primary)
          - node_id (VARCHAR)
          - content (VARCHAR)
          - title (VARCHAR)
          - difficulty (FLOAT)
          - category (VARCHAR)
        """
        self._ensure_connected()
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType

        cfg = self._config

        # ---- Child Collection ----
        child_fields = [
            FieldSchema(name="child_id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="node_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="chunk_index", dtype=DataType.INT64),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=cfg.embedding_dim),
        ]
        child_schema = CollectionSchema(child_fields, description="EduAgent Child Chunks")
        child_col = Collection(name=cfg.child_collection_name, schema=child_schema, using=cfg.alias)

        # ---- Parent Collection ----
        parent_fields = [
            FieldSchema(name="parent_id", dtype=DataType.VARCHAR, is_primary=True, max_length=128),
            FieldSchema(name="node_id", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="difficulty", dtype=DataType.FLOAT),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=64),
        ]
        parent_schema = CollectionSchema(parent_fields, description="EduAgent Parent Chunks")
        parent_col = Collection(name=cfg.parent_collection_name, schema=parent_schema, using=cfg.alias)

    def create_indexes(self) -> None:
        """为两个 Collection 创建向量索引。"""
        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config

        child_col = Collection(name=cfg.child_collection_name, using=cfg.alias)
        child_index_params = {
            "metric_type": cfg.metric_type,
            "index_type": cfg.index_type,
            "params": {"nlist": cfg.nlist},
        }
        child_col.create_index(field_name="embedding", index_params=child_index_params)

        # Parent Collection 没有向量字段，无需创建向量索引
        # 但可为 parent_id 创建标量索引加速查询

    def load_collections(self) -> None:
        """将 Collection 加载到内存。"""
        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config
        child_col = Collection(name=cfg.child_collection_name, using=cfg.alias)
        child_col.load()

    def drop_collections(self) -> None:
        """删除两个 Collection。"""
        self._ensure_connected()
        from pymilvus import utility
        cfg = self._config
        for name in [cfg.child_collection_name, cfg.parent_collection_name]:
            if utility.has_collection(name, using=cfg.alias):
                utility.drop_collection(name, using=cfg.alias)

    # ------------------------------------------------------------------
    # 数据插入
    # ------------------------------------------------------------------

    def insert_parent(self, parent: ParentChunk) -> bool:
        """插入单条父块记录。

        Args:
            parent: 父块数据。

        Returns:
            True。
        """
        return self.insert_parents_batch([parent])

    def insert_parents_batch(self, parents: List[ParentChunk]) -> bool:
        """批量插入父块。"""
        if not parents:
            return True
        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config
        col = Collection(name=cfg.parent_collection_name, using=cfg.alias)

        data = [
            [p.parent_id for p in parents],
            [p.node_id for p in parents],
            [p.content for p in parents],
            [p.title for p in parents],
            [p.difficulty for p in parents],
            [p.category for p in parents],
        ]
        col.insert(data)
        col.flush()
        return True

    def insert_child(self, child: ChildChunk) -> bool:
        """插入单条子块记录（含向量嵌入）。

        若 child.embedding 为 None，自动调用 embed_fn 生成向量。

        Args:
            child: 子块数据。

        Returns:
            True。
        """
        return self.insert_children_batch([child])

    def insert_children_batch(self, children: List[ChildChunk]) -> bool:
        """批量插入子块。"""
        if not children:
            return True
        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config
        col = Collection(name=cfg.child_collection_name, using=cfg.alias)

        # 对于没有 embedding 的子块，批量生成
        missing_embed_idxs = [
            i for i, c in enumerate(children) if c.embedding is None
        ]
        if missing_embed_idxs:
            texts = [children[i].content for i in missing_embed_idxs]
            embeddings = self.embed_texts(texts)
            for idx, emb in zip(missing_embed_idxs, embeddings):
                children[idx].embedding = emb

        data = [
            [c.child_id for c in children],
            [c.parent_id for c in children],
            [c.node_id for c in children],
            [c.content for c in children],
            [c.chunk_index for c in children],
            [c.embedding for c in children],
        ]
        col.insert(data)
        col.flush()
        return True

    # ------------------------------------------------------------------
    # 向量检索 (核心功能)
    # ------------------------------------------------------------------

    def search(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        filter_node_ids: Optional[List[str]] = None,
        filter_categories: Optional[List[str]] = None,
        difficulty_range: Optional[Tuple[float, float]] = None,
    ) -> ChunkSearchResult:
        """执行 Parent-Child 双层向量检索。

        流程:
          1. 将 query_text 向量化
          2. 在 Child Collection 中执行 ANN 搜索
          3. 收集命中子块的 parent_id（去重）
          4. 从 Parent Collection 获取完整父块上下文
          5. 组装 ChunkSearchResult 并返回

        Args:
            query_text: 查询文本。
            top_k: 子块召回数量，默认使用 config.default_top_k。
            filter_node_ids: 限定知识点 ID 范围（标量过滤）。
            filter_categories: 限定知识点类别。
            difficulty_range: 难度区间 (min, max)。

        Returns:
            ChunkSearchResult: 子块命中 + 父块上下文。
        """
        self._ensure_connected()
        import time
        from pymilvus import Collection

        start_time = time.perf_counter()
        cfg = self._config
        k = top_k or cfg.default_top_k

        # Step 1: 向量化查询
        query_vector = self.embed_text(query_text)

        # Step 2: 构建标量过滤表达式
        expr_parts: List[str] = []
        if filter_node_ids:
            ids_str = ", ".join(f'"{nid}"' for nid in filter_node_ids)
            expr_parts.append(f"node_id in [{ids_str}]")
        if filter_categories:
            cats_str = ", ".join(f'"{cat}"' for cat in filter_categories)
            expr_parts.append(f"category in [{cats_str}]")
        if difficulty_range:
            lo, hi = difficulty_range
            expr_parts.append(f"difficulty >= {lo} && difficulty <= {hi}")
        expr = " && ".join(expr_parts) if expr_parts else None

        # Step 3: Child Collection 向量搜索
        child_col = Collection(name=cfg.child_collection_name, using=cfg.alias)
        search_params = {
            "metric_type": cfg.metric_type,
            "params": {"nprobe": cfg.search_nprobe},
        }

        output_fields = ["parent_id", "node_id", "content", "chunk_index"]
        raw_results = child_col.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=k,
            expr=expr,
            output_fields=output_fields,
        )

        # Step 4: 解析子块命中
        child_hits: List[SearchResult] = []
        parent_ids_seen: set = set()
        for hits in raw_results:  # 每个查询向量的命中列表
            for hit in hits:
                pid = hit.entity.get("parent_id")
                child_hits.append(SearchResult(
                    child_id=hit.id,
                    parent_id=pid,
                    node_id=hit.entity.get("node_id", ""),
                    score=round(hit.distance, 6),
                    child_content=hit.entity.get("content", ""),
                    child_chunk_index=hit.entity.get("chunk_index", 0),
                ))
                parent_ids_seen.add(pid)

        # Step 5: 父块反查 (Parent Lookup)
        parent_contexts: List[ParentChunk] = []
        if parent_ids_seen:
            parent_contexts = self._fetch_parents_by_ids(
                list(parent_ids_seen)[: cfg.max_parents_per_query]
            )

        # Step 6: 统计
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return ChunkSearchResult(
            query=query_text,
            child_hits=child_hits,
            parent_contexts=parent_contexts,
            total_child_hits=len(child_hits),
            search_latency_ms=round(elapsed_ms, 2),
        )

    def _fetch_parents_by_ids(self, parent_ids: List[str]) -> List[ParentChunk]:
        """通过 parent_id 列表批量获取父块。"""
        if not parent_ids:
            return []

        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config
        col = Collection(name=cfg.parent_collection_name, using=cfg.alias)

        ids_str = ", ".join(f'"{pid}"' for pid in parent_ids)
        expr = f"parent_id in [{ids_str}]"

        try:
            results = col.query(
                expr=expr,
                output_fields=["parent_id", "node_id", "content", "title", "difficulty", "category"],
            )
        except Exception:
            return []

        parents: List[ParentChunk] = []
        for r in results:
            parents.append(ParentChunk(
                parent_id=r.get("parent_id", ""),
                node_id=r.get("node_id", ""),
                content=r.get("content", ""),
                title=r.get("title", ""),
                difficulty=r.get("difficulty", 0.5),
                category=r.get("category", "concept"),
            ))
        return parents

    # ------------------------------------------------------------------
    # 智能辅导加分项 — 父块检索 + 视频时序切片检索
    # ------------------------------------------------------------------

    def search_parent_chunks(
        self,
        query_text: str,
        current_node_id: str,
        top_k: Optional[int] = None,
    ) -> List[ParentChunk]:
        """检索与查询最相关的父块全文上下文（用于 Tutor Agent 文本轨）。

        流程:
          1. 在 Child Collection 中执行 ANN 搜索
          2. 通过 parent_id 反查父块完整学术上下文
          3. 返回去重后的父块列表

        Args:
            query_text: 学生的答疑提问文本。
            current_node_id: 当前知识点 ID，用于范围限定。
            top_k: 子块召回数量。

        Returns:
            去重后的父块列表（按相似度降序）。
        """
        self._ensure_connected()
        cfg = self._config
        k = top_k or cfg.default_top_k

        # Step 1: 向量化查询并在子块层检索
        query_vector = self.embed_text(query_text)
        from pymilvus import Collection

        child_col = Collection(name=cfg.child_collection_name, using=cfg.alias)
        search_params = {
            "metric_type": cfg.metric_type,
            "params": {"nprobe": cfg.search_nprobe},
        }

        # 限定当前知识点范围
        expr = f'node_id == "{current_node_id}"'

        raw_results = child_col.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=k,
            expr=expr,
            output_fields=["parent_id"],
        )

        # Step 2: 收集 parent_id 并去重
        parent_ids_seen: List[str] = []
        seen: set = set()
        for hits in raw_results:
            for hit in hits:
                pid = hit.entity.get("parent_id")
                if pid and pid not in seen:
                    seen.add(pid)
                    parent_ids_seen.append(pid)

        # Step 3: 反查父块
        if not parent_ids_seen:
            return []

        return self._fetch_parents_by_ids(
            parent_ids_seen[: cfg.max_parents_per_query]
        )

    def search_video_temporal_slices(
        self,
        query_text: str,
        top_k: int = 1,
    ) -> List[Dict[str, Any]]:
        """时序滑动窗口多模态相似度匹配 — 微课切片索引轨核心。

        模拟将初始微课视频按 5 秒一帧进行多模态特征向量化后，
        在 Milvus 的 Video Slice Collection 中执行点对点最高相似度检索，
        动态计算最匹配的画面起点与终点 (Time Range)。

        注：Video Slice Collection 需预先创建并载入视频帧向量 +
        ASR 转写文本向量。若 Collection 不存在，回退到默认视频。

        Args:
            query_text: 答疑查询文本（与视频 ASR 文本进行语义匹配）。
            top_k: 返回的最匹配切片数量。

        Returns:
            匹配的视频元数据列表，每项包含:
              - url: 视频 CDN 地址
              - time_range: 推荐时间片段 (如 "00:30-01:15")
              - similarity: 余弦相似度分数
        """
        self._ensure_connected()
        from pymilvus import Collection, utility

        cfg = self._config
        video_collection_name = "edu_video_slices"

        # 若 Video Slice Collection 不存在，回退到默认视频
        if not utility.has_collection(video_collection_name, using=cfg.alias):
            return [{
                "url": "https://default_course_cdn/fallback.mp4",
                "time_range": "00:00-01:00",
                "similarity": 0.0,
            }]

        # 向量化查询
        query_vector = self.embed_text(query_text)

        col = Collection(name=video_collection_name, using=cfg.alias)
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": cfg.search_nprobe},
        }

        try:
            raw_results = col.search(
                data=[query_vector],
                anns_field="video_embedding",
                param=search_params,
                limit=top_k,
                output_fields=["url", "start_sec", "end_sec", "asr_text"],
            )
        except Exception:
            return [{
                "url": "https://default_course_cdn/fallback.mp4",
                "time_range": "00:00-01:00",
                "similarity": 0.0,
            }]

        # 解析结果
        results: List[Dict[str, Any]] = []
        for hits in raw_results:
            for hit in hits:
                start = hit.entity.get("start_sec", 0)
                end = hit.entity.get("end_sec", 60)
                results.append({
                    "url": hit.entity.get("url", "https://default_course_cdn/fallback.mp4"),
                    "time_range": f"{int(start)//60:02d}:{int(start)%60:02d}-{int(end)//60:02d}:{int(end)%60:02d}",
                    "similarity": round(hit.distance, 4),
                    "asr_text": hit.entity.get("asr_text", ""),
                })

        return results if results else [{
            "url": "https://default_course_cdn/fallback.mp4",
            "time_range": "00:00-01:00",
            "similarity": 0.0,
        }]

    # ------------------------------------------------------------------
    # 清空与状态
    # ------------------------------------------------------------------

    def get_collection_stats(self) -> Dict[str, Any]:
        """获取两个 Collection 的行数统计。"""
        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config

        stats: Dict[str, Any] = {}
        for name in [cfg.child_collection_name, cfg.parent_collection_name]:
            try:
                col = Collection(name=name, using=cfg.alias)
                stats[name] = {"num_entities": col.num_entities}
            except Exception:
                stats[name] = {"num_entities": 0, "error": "collection not found"}
        return stats

    def flush_all(self) -> None:
        """强制持久化所有 Collection 的未写入数据。"""
        self._ensure_connected()
        from pymilvus import Collection

        cfg = self._config
        for name in [cfg.child_collection_name, cfg.parent_collection_name]:
            try:
                col = Collection(name=name, using=cfg.alias)
                col.flush()
            except Exception:
                pass
