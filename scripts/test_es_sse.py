#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EduAgent — ES 知识库检索 + SSE 流式输出 综合测试脚本
====================================================

使用方式:
  # 测试 ES（需要真实密码）
  python scripts/test_es_sse.py --es-password <密码>

  # 仅测 ES（跳过SSE）
  python scripts/test_es_sse.py --es-password <密码> --skip-sse

  # 仅测 SSE（跳过ES）
  python scripts/test_es_sse.py --skip-es

  # 无认证 ES（docker-compose 模式）
  python scripts/test_es_sse.py --no-es-auth

环境变量优先级高于命令行参数:
  ES_PASSWORD=<密码> python scripts/test_es_sse.py
"""
from __future__ import annotations

import io
import sys

# Force UTF-8 output on Windows (fixes GBK codec errors with Unicode symbols)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from io import TextIOWrapper
from typing import Any, Dict, List, Optional

# ── ANSI 颜色 ────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg: str)  -> None: print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg: str) -> None: print(f"  {RED}✗{RESET} {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def info(msg: str) -> None: print(f"  {CYAN}→{RESET} {msg}")
def sep(title: str = "") -> None:
    line = "─" * 60
    print(f"\n{BOLD}{line}{RESET}")
    if title:
        print(f"{BOLD}  {title}{RESET}")

# ── 默认配置 ──────────────────────────────────────────────────────────────────
DEFAULT_ES_HOST    = "http://127.0.0.1:9200"
DEFAULT_ES_INDEX   = "eduagent_data_structure_kb"
DEFAULT_ES_USER    = "elastic"
DEFAULT_BACKEND    = "http://127.0.0.1:8800"
DEFAULT_COURSE_ID  = "data_structures"
DEFAULT_USER_ID    = "test_student_001"

# 代表性测试查询（覆盖不同知识点和查询类型）
TEST_QUERIES = [
    {
        "query": "快速排序的时间复杂度分析",
        "expected_keywords": ["快排", "O(n log n)", "分治", "partition"],
    },
    {
        "query": "动态规划和贪心算法的区别",
        "expected_keywords": ["动态规划", "贪心", "最优子结构", "子问题"],
    },
    {
        "query": "二叉树的前序遍历代码实现",
        "expected_keywords": ["二叉树", "前序", "递归", "root"],
    },
]

# ── HTTP 工具 ─────────────────────────────────────────────────────────────────

def _make_basic_auth(user: str, password: str) -> str:
    import base64
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def es_get(path: str, host: str, auth_header: Optional[str]) -> Dict[str, Any]:
    """Send a GET request to ES and return parsed JSON."""
    url = host.rstrip("/") + "/" + path.lstrip("/")
    req = urllib.request.Request(url)
    if auth_header:
        req.add_header("Authorization", auth_header)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def es_post(path: str, body: Dict, host: str, auth_header: Optional[str]) -> Dict[str, Any]:
    """Send a POST request to ES and return parsed JSON."""
    url = host.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if auth_header:
        req.add_header("Authorization", auth_header)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def backend_post(path: str, body: Dict, base_url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _session_api_path(user_id: str, course_id: str, suffix: str = "") -> str:
    session_id = urllib.parse.quote(f"{user_id}:{course_id}", safe="")
    return f"/api/sessions/{session_id}{suffix}"


def _dev_auth_headers(user_id: str) -> Dict[str, str]:
    """Mint a local dev token (same default JWT secret as a dev server)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from src.auth.security import SecurityManager

    token = SecurityManager.create_token_pair(user_id, "STUDENT")["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── ES 测试 ───────────────────────────────────────────────────────────────────

def test_es_health(host: str, auth_header: Optional[str]) -> bool:
    sep("① ES 集群健康检查")
    try:
        health = es_get("_cluster/health", host, auth_header)
        status = health.get("status", "unknown")
        color = GREEN if status == "green" else (YELLOW if status == "yellow" else RED)
        ok(f"集群状态: {color}{status}{RESET}  节点数: {health.get('number_of_nodes', '?')}")
        ok(f"活跃分片: {health.get('active_shards', '?')}  主分片: {health.get('active_primary_shards', '?')}")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            fail(f"ES 认证失败 (401) — 请通过 --es-password 或 ES_PASSWORD 环境变量提供正确密码")
        else:
            fail(f"ES 返回 HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        fail(f"无法连接 ES ({host}): {e}")
        return False


def test_es_index(index: str, host: str, auth_header: Optional[str]) -> bool:
    sep("② ES 索引统计")
    try:
        # 索引是否存在
        try:
            mapping = es_get(f"{index}/_mapping", host, auth_header)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                fail(f"索引 {index!r} 不存在 — 请先运行: python scripts/ingest_data_structure_kb.py")
                return False
            raise

        ok(f"索引 {index!r} 存在")

        # 统计文档数
        stats = es_get(f"{index}/_stats", host, auth_header)
        doc_count = stats["_all"]["primaries"]["docs"]["count"]
        store_mb = stats["_all"]["primaries"]["store"]["size_in_bytes"] / 1024 / 1024

        if doc_count == 0:
            warn(f"索引为空（0 条文档）— 请先运行 ingest 脚本")
            return False

        ok(f"文档数: {BOLD}{doc_count}{RESET}  存储: {store_mb:.1f} MB")

        # 查看 mapping 字段
        index_mapping = mapping.get(index, {}).get("mappings", {}).get("properties", {})
        has_vector = "embedding" in index_mapping
        has_content = "content" in index_mapping
        ok(f"字段: embedding={has_vector} content={has_content}  总字段数: {len(index_mapping)}")

        return True

    except Exception as e:
        fail(f"索引检查失败: {e}")
        return False


def _score_result(hit: Dict, query: str, expected_keywords: List[str]) -> str:
    """打印单条检索结果并返回关键词命中情况描述。"""
    score  = hit.get("_score", 0)
    source = hit.get("_source", {})
    content     = source.get("content", "")
    title_path  = source.get("title_path", "")
    chapter     = source.get("chapter", "")
    section     = source.get("section", "")
    has_code    = source.get("has_code_block", False)
    lang_tags   = source.get("language_tags", [])

    # 片段截取（最多120字）
    snippet = content.replace("\n", " ").strip()[:120]

    # 关键词命中
    hit_kws = [kw for kw in expected_keywords if kw.lower() in content.lower()]
    kw_ratio = len(hit_kws) / max(len(expected_keywords), 1)
    kw_color = GREEN if kw_ratio >= 0.5 else (YELLOW if kw_ratio > 0 else DIM)

    print(f"    {BOLD}得分 {score:.4f}{RESET}  路径: {title_path or f'{chapter} > {section}'}")
    print(f"    片段: {DIM}{snippet}…{RESET}")
    if has_code:
        print(f"    含代码: {lang_tags or ['(未标注)']}")
    print(f"    关键词命中: {kw_color}{hit_kws or '无'}{RESET}")
    return f"{len(hit_kws)}/{len(expected_keywords)}"


def test_es_search(index: str, host: str, auth_header: Optional[str]) -> None:
    sep("③ Hybrid 检索质量测试（BM25 + 向量 + RRF）")

    for i, case in enumerate(TEST_QUERIES, 1):
        query   = case["query"]
        kws     = case["expected_keywords"]
        print(f"\n  {CYAN}[Query {i}]{RESET} {BOLD}{query}{RESET}")

        # ── BM25-only ──
        bm25_body = {
            "size": 3,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["content^3", "title_path^2", "chapter", "section", "knowledge_point"],
                    "type": "best_fields",
                }
            },
        }
        try:
            bm25_resp = es_post(f"{index}/_search", bm25_body, host, auth_header)
            hits = bm25_resp.get("hits", {}).get("hits", [])
            took = bm25_resp.get("took", 0)
            info(f"BM25 top-{len(hits)} （耗时 {took}ms）")
            if hits:
                _score_result(hits[0], query, kws)
            else:
                warn("BM25 无结果 — 索引可能为空或分词器不匹配")
        except Exception as e:
            fail(f"BM25 搜索失败: {e}")

        # ── 向量检索（需要 embedding 字段存在）──
        # 用随机向量代替真实 embedding，仅测试 kNN API 可用性
        try:
            knn_body = {
                "size": 3,
                "knn": {
                    "field": "embedding",
                    "query_vector": [0.01] * 512,   # 512-dim placeholder
                    "k": 3,
                    "num_candidates": 50,
                },
            }
            knn_resp = es_post(f"{index}/_search", knn_body, host, auth_header)
            knn_hits = knn_resp.get("hits", {}).get("hits", [])
            knn_took = knn_resp.get("took", 0)
            info(f"kNN top-{len(knn_hits)} （耗时 {knn_took}ms）")
            if knn_hits:
                print(f"    kNN top-1 得分: {knn_hits[0].get('_score', 0):.4f}  (随机向量，仅验证API)")
        except urllib.error.HTTPError as e:
            body_str = e.read().decode()[:200]
            if "No [knn] queries" in body_str or "failed to parse" in body_str:
                warn("kNN API 不可用（ES版本可能不支持 knn 字段）")
            else:
                warn(f"kNN 请求失败: {body_str[:120]}")
        except Exception as e:
            warn(f"kNN 测试跳过: {e}")

    print()


# ── SSE 测试 ──────────────────────────────────────────────────────────────────

def test_session_advance(backend: str) -> bool:
    sep("④ 会话推进端点: POST /api/sessions/{session_id}/advance")
    path = _session_api_path(DEFAULT_USER_ID, DEFAULT_COURSE_ID, "/advance")
    info(f"请求: POST {backend}{path}")
    try:
        headers = _dev_auth_headers(DEFAULT_USER_ID)
        init_path = _session_api_path(DEFAULT_USER_ID, DEFAULT_COURSE_ID, "/path/init")
        init_state = backend_post(init_path, {}, backend, headers=headers)
        node_id = init_state.get("current_node_id") or (init_state.get("active_path") or [None])[0]
        if not node_id:
            fail("path/init 未返回学习节点")
            return False
        info(f"当前节点: {node_id}")

        result = backend_post(path, {
            "current_node_id": node_id,
            "interaction_type": "load_node",
        }, backend, headers=headers)

        if result.get("current_node_id") != node_id:
            fail(f"advance 返回节点不一致: {result.get('current_node_id')!r}")
            return False
        ok(f"advance OK  interaction={result.get('interaction_type')}  contract_v{result.get('resource_contract_version')}")
        return True

    except urllib.error.URLError as e:
        if "Connection refused" in str(e) or "actively refused" in str(e).lower():
            fail(f"后端未运行 ({backend}) — 请先启动: python frontend/server.py")
        else:
            fail(f"网络错误: {e}")
        return False
    except Exception as e:
        fail(f"会话推进测试失败: {e}")
        return False


def test_sse_tutor_stream(backend: str) -> bool:
    sep("⑤ SSE Tutor 端点: POST /api/sessions/{session_id}/tutor (stream=true)")
    url = backend.rstrip("/") + _session_api_path(DEFAULT_USER_ID, DEFAULT_COURSE_ID, "/tutor")
    payload = {
        "question": "快速排序的最坏情况是什么？如何避免？",
        "context_type": "concept",
        "stream": True,
    }
    info(f"请求: POST {url}")
    info(f"问题: {payload['question']}")
    try:
        data = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "text/event-stream")
        for name, value in _dev_auth_headers(DEFAULT_USER_ID).items():
            req.add_header(name, value)
        resp = urllib.request.urlopen(req, timeout=30)

        tokens_received = 0
        full_text = ""
        start = time.time()
        reader = TextIOWrapper(resp, encoding="utf-8")

        event_type = ""
        data_buf   = ""
        done_received = False

        for raw_line in reader:
            line = raw_line.rstrip("\n")
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_buf = line[len("data:"):].strip()
            elif line == "" and event_type:
                if event_type == "token":
                    try:
                        tok = json.loads(data_buf)
                        token_text = tok.get("token", "")
                        full_text += token_text
                        tokens_received += 1
                        if tokens_received <= 5:
                            print(f"    {DIM}token#{tokens_received}: {repr(token_text)}{RESET}")
                    except Exception:
                        pass
                elif event_type == "done":
                    done_received = True
                    break
                elif event_type == "error":
                    fail(f"服务端错误: {data_buf[:200]}")
                    return False

                if time.time() - start > 25:
                    warn("超时（25s），中断读取")
                    break
                event_type = ""
                data_buf   = ""

        resp.close()
        elapsed = time.time() - start

        if tokens_received == 0:
            fail("未收到任何token")
            return False

        ok(f"共收到 {BOLD}{tokens_received}{RESET} 个token  耗时 {elapsed:.1f}s  done={done_received}")
        preview = full_text[:200].replace("\n", " ")
        ok(f"回答预览: {DIM}{preview}…{RESET}")
        return True

    except urllib.error.URLError as e:
        if "Connection refused" in str(e) or "actively refused" in str(e).lower():
            fail(f"后端未运行 ({backend})")
        elif "404" in str(e):
            fail("/api/sessions/{session_id}/tutor 端点不存在 (404) — 检查 server.py 路由注册")
        else:
            fail(f"网络错误: {e}")
        return False
    except Exception as e:
        fail(f"Tutor SSE 测试失败: {e}")
        return False


def test_tutor_sync(backend: str) -> bool:
    """同步 tutor ask（用于确认后端连通性基线）。"""
    sep("⑥ 同步 Tutor 端点（基线）: POST /api/sessions/{session_id}/tutor")
    tutor_path = _session_api_path(DEFAULT_USER_ID, DEFAULT_COURSE_ID, "/tutor")
    payload = {
        "question": "什么是动态规划？",
        "context_type": "concept",
        "stream": False,
    }
    info(f"请求: POST {backend}{tutor_path}")
    try:
        resp_data = backend_post(tutor_path, payload, backend, headers=_dev_auth_headers(DEFAULT_USER_ID))
        tutor_resp = resp_data.get("tutor_response") or {}
        text = tutor_resp.get("text_explanation", "") if isinstance(tutor_resp, dict) else ""
        ok(f"同步响应 OK  回答长度: {len(text)} chars")
        ok(f"预览: {DIM}{text[:120].replace(chr(10), ' ')}…{RESET}")
        return True
    except urllib.error.URLError as e:
        if "Connection refused" in str(e) or "actively refused" in str(e).lower():
            fail(f"后端未运行 ({backend})")
        else:
            fail(f"错误: {e}")
        return False
    except Exception as e:
        fail(f"同步Tutor测试失败: {e}")
        return False


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="EduAgent ES + SSE 综合测试")
    parser.add_argument("--es-host",    default=os.getenv("ES_HOSTS", DEFAULT_ES_HOST).split(",")[0].strip())
    parser.add_argument("--es-index",   default=os.getenv("ES_INDEX", DEFAULT_ES_INDEX))
    parser.add_argument("--es-user",    default=os.getenv("ES_USER", DEFAULT_ES_USER))
    parser.add_argument("--es-password",default=os.getenv("ES_PASSWORD", ""))
    parser.add_argument("--no-es-auth", action="store_true",  help="不发送 ES 认证头（适用于 xpack.security.enabled=false）")
    parser.add_argument("--backend",    default=os.getenv("BACKEND_URL", DEFAULT_BACKEND))
    parser.add_argument("--skip-es",    action="store_true")
    parser.add_argument("--skip-sse",   action="store_true")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 62}{RESET}")
    print(f"{BOLD}  EduAgent 知识库 & 流式输出 综合测试{RESET}")
    print(f"{BOLD}{'═' * 62}{RESET}")
    print(f"  ES:      {args.es_host}  index={args.es_index}")
    print(f"  Backend: {args.backend}")
    print()

    results: Dict[str, bool] = {}

    # ── ES 测试 ──
    if not args.skip_es:
        auth_header = None
        if not args.no_es_auth:
            if args.es_password and args.es_password not in ("change-me", ""):
                auth_header = _make_basic_auth(args.es_user, args.es_password)
                info(f"ES 认证: {args.es_user}:{'*' * len(args.es_password)}")
            else:
                warn("未提供ES密码（或仍为占位符 'change-me'）— 将尝试无认证连接")

        es_ok = test_es_health(args.es_host, auth_header)
        results["es_health"] = es_ok

        if es_ok:
            results["es_index"] = test_es_index(args.es_index, args.es_host, auth_header)
            if results["es_index"]:
                test_es_search(args.es_index, args.es_host, auth_header)
                results["es_search"] = True
    else:
        info("跳过 ES 测试 (--skip-es)")

    # ── SSE 测试 ──
    if not args.skip_sse:
        results["tutor_sync"]      = test_tutor_sync(args.backend)
        results["session_advance"] = test_session_advance(args.backend)
        results["sse_tutor"]       = test_sse_tutor_stream(args.backend)
    else:
        info("跳过 SSE 测试 (--skip-sse)")

    # ── 总结 ──
    sep("测试总结")
    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    for name, v in results.items():
        status = f"{GREEN}通过{RESET}" if v else f"{RED}失败{RESET}"
        print(f"  {status}  {name}")
    print()
    if passed == total:
        print(f"  {GREEN}{BOLD}全部 {total}/{total} 测试通过 ✓{RESET}\n")
    else:
        print(f"  {YELLOW}{BOLD}{passed}/{total} 测试通过{RESET}\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
