# Caddy adapter

将公共路由契约渲染为 AI Gateway 专用 Caddyfile 片段。

职责：自动 TLS、Host 路由和反向代理到当前选择的 Kong/APISIX。不会覆盖现有 Web SaaS 的 Caddy 配置，也不保存凭据。

IP 白名单、认证、租户 ACL 和限流由 Kong/APISIX adapter 负责；Caddy 保持为薄 TLS 入口。
