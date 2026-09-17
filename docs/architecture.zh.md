# AI Gateway 公共组件边界

现有 `edge-gateway` 继续服务 Web SaaS `/api/*`，本项目只负责 AI `/v1/*` 的公共契约和配置渲染。

```text
AI Client
  → Caddy 自动 TLS 薄入口
  → Kong 或 APISIX
      ├── New API → CPA
      └── LiteLLM → 官方 OpenAI/Anthropic/xAI
```

v1 默认使用 Kong Traditional + PostgreSQL。APISIX 使用 Standalone YAML 配置作为可选 adapter。Caddy 不承担 IP 白名单、认证或限流；这些策略由选中的 Kong/APISIX adapter 负责。所有凭据由 Vault 或 CPA 节点本地加密目录提供，不能进入公共 manifest。
