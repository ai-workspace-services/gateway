# APISIX adapter

v1 可选适配器，使用现有 APISIX Standalone file-driven role。

生成完整 `apisix.yaml` 配置，不把 APISIX Standalone 描述为 Kong PostgreSQL 动态配置的等价实现。租户变更、全量发布和回滚由部署流水线负责。

APISIX adapter 负责 Host/URI 路由、Key Auth、Consumer 限制、按租户限流、审计请求头和 upstream 节点调度。它通过 Standalone 全量配置发布实现这些能力，不提供 Kong PostgreSQL 的动态控制面语义。
