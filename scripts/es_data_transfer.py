# -*- coding: utf-8 -*-
"""
ES 知识库数据传输工具 — 纯 Python 导出 / 导入 / 直传
=====================================================

零额外依赖：基于项目已有的 elasticsearch 库，无需安装 elasticdump。

功能:
  1. export — 将索引的 settings / mapping / data 导出为 JSON 文件
  2. import — 从 JSON 文件恢复索引到目标 ES
  3. copy  — 索引直传（源 ES → 目标 ES，不落盘，适合跨机器迁移）

用法:
  # ---- 导出到本地 JSON 文件 ----
  python scripts/es_data_transfer.py export \
      --source-host http://127.0.0.1:9200 \
      --source-index eduagent_knowledge_base \
      --out-dir backups/my_backup

  # ---- 从 JSON 文件恢复到目标 ES ----
  python scripts/es_data_transfer.py import \
      --target-host http://10.0.0.5:9200 \
      --target-index eduagent_knowledge_base \
      --from-dir backups/my_backup

  # ---- 索引直传（源 → 目标，不落盘）----
  python scripts/es_data_transfer.py copy \
      --source-host http://127.0.0.1:9200 \
      --source-index eduagent_knowledge_base \
      --target-host http://10.0.0.5:9200 \
      --target-index eduagent_kb_backup

  # ---- 显示索引信息 ----
  python scripts/es_data_transfer.py info --host http://127.0.0.1:9200 --index eduagent_knowledge_base
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# 辅助
# ============================================================================

def _build_es_client(hosts: List[str], user: Optional[str] = None,
                     password: Optional[str] = None,
                     timeout: int = 60) -> Any:
    """创建 Elasticsearch 客户端。"""
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        sys.exit(
            "elasticsearch 未安装。请执行: pip install elasticsearch"
        )

    kwargs: Dict[str, Any] = {
        "hosts": hosts,
        "request_timeout": timeout,
        "verify_certs": False,
    }
    if user and password:
        kwargs["basic_auth"] = (user, password)

    client = Elasticsearch(**kwargs)
    # 连接验证
    if not client.ping():
        sys.exit(f"无法连接到 ES: {hosts}")
    return client


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _size_str(byte_count: int) -> str:
    if byte_count >= 1_048_576:
        return f"{byte_count / 1_048_576:.1f} MB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.1f} KB"
    return f"{byte_count} B"


def _index_exists(client: Any, index_name: str) -> bool:
    return client.indices.exists(index=index_name)


# ============================================================================
# export — 导出索引到 JSON 文件
# ============================================================================

def cmd_export(args: argparse.Namespace) -> int:
    """导出索引 settings / mapping / data 到本地 JSON 文件。"""
    source_hosts = args.source_host or ["http://127.0.0.1:9200"]
    if isinstance(source_hosts, str):
        source_hosts = [source_hosts]

    print(f"连接源 ES: {source_hosts}")
    client = _build_es_client(source_hosts, args.source_user, args.source_password)

    index = args.source_index or "eduagent_knowledge_base"
    if not _index_exists(client, index):
        sys.exit(f"源索引不存在: {index}")

    # 输出目录
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or f"backups/es_{index}_{ts}"
    _ensure_dir(out_dir)

    # ---- 1. 导出 Settings ----
    print("\n[1/3] 导出 Settings...")
    settings = client.indices.get_settings(index=index)
    settings_path = os.path.join(out_dir, "eduagent_settings.json")
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✓ {settings_path} ({_size_str(os.path.getsize(settings_path))})")

    # ---- 2. 导出 Mapping ----
    print("[2/3] 导出 Mapping...")
    mapping = client.indices.get_mapping(index=index)
    mapping_path = os.path.join(out_dir, "eduagent_mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✓ {mapping_path} ({_size_str(os.path.getsize(mapping_path))})")

    # ---- 3. 导出数据（scroll API） ----
    print("[3/3] 导出文档数据（scroll 流式读取）...")
    scroll_size = args.scroll_size or 1000
    scroll_keep = args.scroll_keep or "5m"
    data_path = os.path.join(out_dir, "eduagent_data.json")

    doc_count = 0
    batch_no = 0

    with open(data_path, "w", encoding="utf-8") as f:
        f.write('{"docs":[\n')

        resp = client.search(
            index=index,
            scroll=scroll_keep,
            size=scroll_size,
            query={"match_all": {}},
        )
        scroll_id = resp.get("_scroll_id")
        hits = resp["hits"]["hits"]

        while hits:
            for hit in hits:
                if doc_count > 0:
                    f.write(",\n")
                doc = {
                    "_index": hit.get("_index", index),
                    "_id": hit.get("_id", ""),
                    "_source": hit.get("_source", {}),
                }
                json.dump(doc, f, ensure_ascii=False, default=str)
                doc_count += 1

            batch_no += 1
            print(f"  已导出 {doc_count} 条文档 (批次 {batch_no})...", end="\r")

            if scroll_id:
                resp = client.scroll(scroll_id=scroll_id, scroll=scroll_keep)
                hits = resp["hits"]["hits"]
            else:
                hits = []

        f.write("\n]}\n")

    # 清理 scroll
    if scroll_id:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

    file_size = os.path.getsize(data_path)
    print(f"\n  ✓ {data_path} ({doc_count} 条文档, {_size_str(file_size)})")

    # ---- 汇总 ----
    print(f"\n{'='*50}")
    print(f"  ✅ 导出完成")
    print(f"  索引: {index}")
    print(f"  输出: {out_dir}/")
    print(f"  文档: {doc_count} 条")
    print(f"{'='*50}")
    print(f"\n  恢复命令:")
    print(f"    python scripts/es_data_transfer.py import \\")
    print(f"        --target-host <目标ES地址> \\")
    print(f"        --target-index {index} \\")
    print(f"        --from-dir {out_dir}")
    return 0


# ============================================================================
# import — 从 JSON 恢复索引
# ============================================================================

def cmd_import(args: argparse.Namespace) -> int:
    """从 JSON 备份文件恢复索引到目标 ES。"""
    target_hosts = args.target_host or ["http://127.0.0.1:9200"]
    if isinstance(target_hosts, str):
        target_hosts = [target_hosts]

    print(f"连接目标 ES: {target_hosts}")
    client = _build_es_client(target_hosts, args.target_user, args.target_password)

    target_index = args.target_index or "eduagent_knowledge_base"
    from_dir = args.from_dir
    if not from_dir:
        sys.exit("请指定备份目录: --from-dir <DIR>")

    # 检查文件
    settings_file = os.path.join(from_dir, "eduagent_settings.json")
    mapping_file = os.path.join(from_dir, "eduagent_mapping.json")
    data_file = os.path.join(from_dir, "eduagent_data.json")

    for fpath, label in [
        (settings_file, "Settings"),
        (mapping_file, "Mapping"),
        (data_file, "Data"),
    ]:
        if not os.path.isfile(fpath):
            sys.exit(f"缺少备份文件: {fpath} ({label})")

    # 是否重建
    if _index_exists(client, target_index):
        if args.recreate:
            print(f"删除已有索引: {target_index}")
            client.indices.delete(index=target_index)
        else:
            resp = input(
                f"索引 '{target_index}' 已存在，是否覆盖？[y/N] "
            )
            if resp.lower() not in ("y", "yes"):
                print("已取消")
                return 0
            client.indices.delete(index=target_index)

    # ---- 1. 恢复 Settings ----
    print("\n[1/3] 恢复 Settings...")
    with open(settings_file, "r", encoding="utf-8") as f:
        raw_settings = json.load(f)

    # 提取纯 settings 体（去掉外层 index 包装）
    settings_body = _extract_settings_body(raw_settings)
    # 先以空 body 创建索引，再 close → update settings → open
    client.indices.create(index=target_index, settings=settings_body if settings_body else {"number_of_shards": 1})
    print("  ✓ Settings 已恢复")

    # ---- 2. 恢复 Mapping ----
    print("[2/3] 恢复 Mapping...")
    with open(mapping_file, "r", encoding="utf-8") as f:
        raw_mapping = json.load(f)

    mapping_body = _extract_mapping_body(raw_mapping)
    if mapping_body:
        client.indices.put_mapping(index=target_index, body=mapping_body)
    print("  ✓ Mapping 已恢复")

    # ---- 3. 恢复数据 ----
    print("[3/3] 恢复文档数据...")
    with open(data_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    docs = raw_data.get("docs", raw_data if isinstance(raw_data, list) else [])
    if not docs:
        print("  ⚠ 数据文件为空，跳过")
        return 0

    batch_size = args.batch_size or 500
    from elasticsearch import helpers

    total = len(docs)
    imported = 0
    errors = 0

    for start in range(0, total, batch_size):
        batch = docs[start : start + batch_size]
        actions = [
            {
                "_index": doc.get("_index", target_index),
                "_id": doc.get("_id"),
                "_source": doc.get("_source", doc),
            }
            for doc in batch
        ]
        try:
            success_count, err_list = helpers.bulk(
                client, actions, stats_only=False, raise_on_error=False
            )
            if isinstance(success_count, tuple):
                success_count = success_count[0]
            imported += len(actions) - len(err_list)
            errors += len(err_list)
        except Exception as exc:
            print(f"\n  批量导入出错 (offset={start}): {exc}")
            errors += len(batch)

        print(f"  已导入 {imported}/{total} 条...", end="\r")

    client.indices.refresh(index=target_index)
    print(f"\n  ✓ 数据恢复完成 ({imported} 成功, {errors} 失败)")

    # ---- 汇总 ----
    print(f"\n{'='*50}")
    print(f"  ✅ 恢复完成")
    print(f"  目标: {target_hosts}")
    print(f"  索引: {target_index}")
    print(f"  文档: {imported} 条")
    print(f"{'='*50}")
    return 0 if errors == 0 else 1


# ============================================================================
# copy — 索引直传（源 ES → 目标 ES）
# ============================================================================

def cmd_copy(args: argparse.Namespace) -> int:
    """索引直传：从源 ES 直接同步到目标 ES（不落盘）。"""
    source_hosts = args.source_host or ["http://127.0.0.1:9200"]
    target_hosts = args.target_host or ["http://127.0.0.1:9200"]
    if isinstance(source_hosts, str):
        source_hosts = [source_hosts]
    if isinstance(target_hosts, str):
        target_hosts = [target_hosts]

    source_index = args.source_index or "eduagent_knowledge_base"
    target_index = args.target_index or source_index

    print(f"源 ES: {source_hosts}  |  索引: {source_index}")
    print(f"目标 ES: {target_hosts}  |  索引: {target_index}")

    src = _build_es_client(source_hosts, args.source_user, args.source_password)
    tgt = _build_es_client(target_hosts, args.target_user, args.target_password)

    if not _index_exists(src, source_index):
        sys.exit(f"源索引不存在: {source_index}")

    # Step 1: 拉取 settings + mapping
    print("\n[1/4] 拉取 Settings & Mapping...")
    raw_settings = src.indices.get_settings(index=source_index)
    raw_mapping = src.indices.get_mapping(index=source_index)

    # Step 2: 目标端创建索引
    print("[2/4] 目标端创建索引...")
    if _index_exists(tgt, target_index):
        if args.recreate:
            tgt.indices.delete(index=target_index)
        else:
            resp = input(f"目标索引 '{target_index}' 已存在，是否覆盖？[y/N] ")
            if resp.lower() not in ("y", "yes"):
                print("已取消")
                return 0
            tgt.indices.delete(index=target_index)

    settings_body = _extract_settings_body(raw_settings)
    mapping_body = _extract_mapping_body(raw_mapping)
    body: Dict[str, Any] = {}
    if settings_body:
        body["settings"] = settings_body
    if mapping_body:
        body["mappings"] = mapping_body
    if not body.get("settings"):
        body["settings"] = {"number_of_shards": 1, "number_of_replicas": 0}

    tgt.indices.create(index=target_index, body=body)

    # Step 3: 滚动源 ES 数据 → 批量写入目标 ES
    print("[3/4] 流式传输数据...")
    scroll_size = args.scroll_size or 1000
    scroll_keep = args.scroll_keep or "5m"
    from elasticsearch import helpers

    total_docs = 0
    batch_no = 0

    resp = src.search(
        index=source_index,
        scroll=scroll_keep,
        size=scroll_size,
        query={"match_all": {}},
    )
    scroll_id = resp.get("_scroll_id")
    hits = resp["hits"]["hits"]

    while hits:
        actions = [
            {
                "_index": target_index,
                "_id": hit["_id"],
                "_source": hit["_source"],
            }
            for hit in hits
        ]

        try:
            helpers.bulk(tgt, actions, stats_only=True, raise_on_error=True)
        except Exception as exc:
            # 失败时退出一批一批重试
            for action in actions:
                try:
                    tgt.index(
                        index=target_index,
                        id=action["_id"],
                        document=action["_source"],
                    )
                except Exception as inner:
                    print(f"\n  写入失败 _id={action['_id']}: {inner}")

        total_docs += len(hits)
        batch_no += 1
        print(f"  已传输 {total_docs} 条 (批次 {batch_no})...", end="\r")

        if scroll_id:
            resp = src.scroll(scroll_id=scroll_id, scroll=scroll_keep)
            hits = resp["hits"]["hits"]
        else:
            hits = []

    if scroll_id:
        try:
            src.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass

    tgt.indices.refresh(index=target_index)
    print(f"\n  ✓ 流式传输完成 ({total_docs} 条文档)")

    # Step 4: 验证
    print("[4/4] 验证...")
    src_count = src.count(index=source_index)["count"]
    tgt_count = tgt.count(index=target_index)["count"]

    print(f"\n{'='*50}")
    print(f"  ✅ 直传完成")
    print(f"  源:   {source_hosts} / {source_index} ({src_count} 条)")
    print(f"  目标: {target_hosts} / {target_index} ({tgt_count} 条)")
    if src_count != tgt_count:
        print(f"  ⚠ 文档数不一致！差异: {abs(src_count - tgt_count)} 条")
    print(f"{'='*50}")
    return 0


# ============================================================================
# info — 显示索引信息
# ============================================================================

def cmd_info(args: argparse.Namespace) -> int:
    """显示索引信息。"""
    hosts = args.host or ["http://127.0.0.1:9200"]
    if isinstance(hosts, str):
        hosts = [hosts]
    index = args.index or "eduagent_knowledge_base"

    client = _build_es_client(hosts, args.user, args.password)

    if not _index_exists(client, index):
        print(f"索引 '{index}' 不存在")
        # 列出所有索引
        all_indices = list(client.indices.get_alias(index="*").keys())
        if all_indices:
            print(f"\n现有索引: {', '.join(all_indices[:20])}")
        return 0

    count = client.count(index=index)["count"]
    stats = client.indices.stats(index=index)
    idx_stats = stats["indices"][index]["total"]

    size_bytes = idx_stats["store"]["size_in_bytes"]
    print(f"索引名称: {index}")
    print(f"文档数量: {count}")
    print(f"存储大小: {_size_str(size_bytes)}")
    print(f"分片数:   {idx_stats['shards']['total']}")
    print(f"段数:     {idx_stats['segments']['count']}")

    # 显示 mapping 关键字段
    mapping = client.indices.get_mapping(index=index)
    properties = (
        mapping.get(index, {})
        .get("mappings", {})
        .get("properties", {})
    )
    print(f"\n字段列表 ({len(properties)} 个):")
    for name, prop in list(properties.items())[:15]:
        ptype = prop.get("type", "?")
        print(f"  {name:25s} → {ptype}")
    if len(properties) > 15:
        print(f"  ... 还有 {len(properties) - 15} 个字段")

    return 0


# ============================================================================
# 内部辅助
# ============================================================================

def _extract_settings_body(raw: Dict) -> Optional[Dict[str, Any]]:
    """从 get_settings 的返回中提取纯净的 settings 体。"""
    for index_name, index_data in raw.items():
        settings = index_data.get("settings", {})
        # 去掉 index.{provided, creation_date, uuid, version} 等不可设置的字段
        index_settings = settings.get("index", dict(settings))
        clean = {
            k: v
            for k, v in index_settings.items()
            if k
            not in (
                "provided_name",
                "creation_date",
                "uuid",
                "version",
                "routing",
            )
        }
        return clean if clean else None
    return None


def _extract_mapping_body(raw: Dict) -> Optional[Dict[str, Any]]:
    """从 get_mapping 的返回中提取纯净的 mappings 体。"""
    for index_name, index_data in raw.items():
        mappings = index_data.get("mappings", {})
        # 移除 _meta、_size 等自动字段（不能 put）
        return {
            "properties": mappings.get("properties", {}),
            "dynamic": mappings.get("dynamic", True),
        }
    return None


# ============================================================================
# CLI 入口
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="ES 知识库数据传输工具 — 导出 / 导入 / 索引直传",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导出
  %(prog)s export --source-host http://127.0.0.1:9200 --source-index eduagent_knowledge_base

  # 导入
  %(prog)s import --target-host http://10.0.0.5:9200 --from-dir backups/es_eduagent_20260613

  # 直传（不落盘）
  %(prog)s copy --source-host http://127.0.0.1:9200 --target-host http://10.0.0.5:9200
        """,
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # ---- export ----
    p_export = sub.add_parser("export", help="导出索引到 JSON 文件")
    p_export.add_argument("--source-host", nargs="+", default=["http://127.0.0.1:9200"],
                          help="源 ES 地址")
    p_export.add_argument("--source-index", default="eduagent_knowledge_base",
                          help="源索引名称")
    p_export.add_argument("--source-user", default="elastic", help="源 ES 用户名")
    p_export.add_argument("--source-password", default="KDCloud$2020", help="源 ES 密码")
    p_export.add_argument("--out-dir", default=None, help="输出目录")
    p_export.add_argument("--scroll-size", type=int, default=1000,
                          help="每批滚动读取的文档数")
    p_export.add_argument("--scroll-keep", default="5m",
                          help="scroll 上下文保持时间")

    # ---- import ----
    p_import = sub.add_parser("import", help="从 JSON 文件恢复索引")
    p_import.add_argument("--target-host", nargs="+", default=["http://127.0.0.1:9200"],
                          help="目标 ES 地址")
    p_import.add_argument("--target-index", default="eduagent_knowledge_base",
                          help="目标索引名称")
    p_import.add_argument("--target-user", default="elastic", help="目标 ES 用户名")
    p_import.add_argument("--target-password", default="KDCloud$2020", help="目标 ES 密码")
    p_import.add_argument("--from-dir", required=True, help="备份文件目录")
    p_import.add_argument("--batch-size", type=int, default=500,
                          help="每批写入的文档数")
    p_import.add_argument("-r", "--recreate", action="store_true",
                          help="自动覆盖已有索引")

    # ---- copy ----
    p_copy = sub.add_parser("copy", help="索引直传（源 ES → 目标 ES）")
    p_copy.add_argument("--source-host", nargs="+", default=["http://127.0.0.1:9200"])
    p_copy.add_argument("--source-index", default="eduagent_knowledge_base")
    p_copy.add_argument("--source-user", default="elastic")
    p_copy.add_argument("--source-password", default="KDCloud$2020")
    p_copy.add_argument("--target-host", nargs="+", default=["http://127.0.0.1:9200"])
    p_copy.add_argument("--target-index", default=None)
    p_copy.add_argument("--target-user", default="elastic")
    p_copy.add_argument("--target-password", default="KDCloud$2020")
    p_copy.add_argument("--scroll-size", type=int, default=1000)
    p_copy.add_argument("--scroll-keep", default="5m")
    p_copy.add_argument("-r", "--recreate", action="store_true",
                        help="自动覆盖目标索引")

    # ---- info ----
    p_info = sub.add_parser("info", help="显示索引信息")
    p_info.add_argument("--host", nargs="+", default=["http://127.0.0.1:9200"])
    p_info.add_argument("--index", default="eduagent_knowledge_base")
    p_info.add_argument("--user", default="elastic")
    p_info.add_argument("--password", default="KDCloud$2020")

    args = parser.parse_args()

    if args.command == "export":
        return cmd_export(args)
    elif args.command == "import":
        return cmd_import(args)
    elif args.command == "copy":
        return cmd_copy(args)
    elif args.command == "info":
        return cmd_info(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
