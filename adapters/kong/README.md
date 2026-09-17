# Kong adapter

v1 主适配器。生成可由 decK 或 Kong Admin API 同步的 entity bundle。

Kong 使用 Traditional 模式和 PostgreSQL。禁止直接 SQL 修改 Kong 内部表；数据库 DSN 和 Admin 凭据由 Vault 注入。

Kong adapter 负责通用 API Gateway 能力：Host/Path 路由、Consumer/ACL、Key Auth/JWT、按租户限流、请求审计元数据，以及基于 upstream targets 的权重、算法和超时调度。AI 模型别名和 Provider 选择仍由 New API/LiteLLM 负责。
