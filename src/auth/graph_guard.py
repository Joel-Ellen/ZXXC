# -*- coding: utf-8 -*-
"""
LangGraph 运行时不可变上下文防护节点
=====================================
针对多智能体协同网络的沙箱环境硬隔离保护器。
防御多线程状态污染与越权篡改。
"""

from typing import Dict, Any, Callable
from langgraph.errors import GraphInterrupt


class LangGraphImmutableContextGuard:
    """LangGraph 上下文不可变防护。

    在 LangGraph 调度任何实际 Agent Node 运行前，对多线程共享状态
    (Graph State) 与底层安全线索 (Thread Config) 执行不可变性强对齐校验。
    """

    @staticmethod
    def create_secure_node_wrapper(
        node_func: Callable,
    ) -> Callable:
        """高阶包装闭包：给任意 Agent Node 加上安全校验层。

        校验流程：
          1. 从 LangGraph config.configurable 提取网关注入的 authenticated_user_id
          2. 运行时防御性核对 state.user_id 与 config 中的身份签名是否一致
          3. 不一致 → 硬熔断抛出 GraphInterrupt
          4. 一致 → 移交控制权给实际 Agent Node

        Args:
            node_func: 原始的 LangGraph node 函数 (state, config) -> state。

        Returns:
            带安全校验的包装函数。
        """
        def wrapper(state: Any, config: Dict[str, Any]) -> Any:
            # 1. 从 LangGraph 系统底层不可变配置提取网关注入的真实身份签名
            configurable = config.get("configurable", {})
            authenticated_user_id = configurable.get("authenticated_user_id")

            if not authenticated_user_id:
                raise GraphInterrupt(
                    "AUTHENTICATION_CONTEXT_MISSING_IN_GRAPH_THREAD"
                )

            # 2. 运行时防御性核对：检测当前正在流转的内存状态是否发生篡改
            state_user_id = getattr(state, "user_id", None)
            if state_user_id != authenticated_user_id:
                raise GraphInterrupt(
                    f"SECURITY_VIOLATION: Graph State user_id '{state_user_id}' "
                    f"does not match Thread context '{authenticated_user_id}'."
                )

            # 3. 校验通过 → 移交控制权
            return node_func(state, config)

        return wrapper

    @classmethod
    def wrap_all_nodes(
        cls,
        node_map: Dict[str, Callable],
    ) -> Dict[str, Callable]:
        """批量包装所有节点。

        Args:
            node_map: {"node_name": node_func}。

        Returns:
            {"node_name": secure_wrapper}。
        """
        return {
            name: cls.create_secure_node_wrapper(func)
            for name, func in node_map.items()
        }
