# Spec Kitty specifications

Specs are tracked as feature deltas under `kitty-specs/<feature>/`. The project charter is in `.kittify/charter/charter.md`.

## Features

- [001 — Quant trading foundation](001-quant-trading-foundation/spec.md): Phase 1 market data, instrument registry, account visibility, research/backtest base, paper trading, and dashboard wiring.
- [002 — AI investment research agent](002-ai-investment-research-agent/spec.md): Read-only AI research MVP with ENV-configured models, uploaded financial documents, evidence retrieval, market/fund/financial tools, strategy analysis, and remaining data-source gaps.

The Spec Kitty CLI was not present in this checkout when these artifacts were prepared, so the files follow its artifact shape and workflow by hand. Reconcile them with the installed CLI before generating managed work packages or accepting/merging a feature.

- [005 — 多市场账户与AI模拟交易](005-ai-paper-trading/spec.md)：五市场开户、初始资金、冻结与持仓、统一撮合、单轮AI授权与执行审计。

- [006 — 模拟生命周期与券商实盘适配](006-paper-lifecycle-and-live-brokers/spec.md)：登录身份/模拟实验分离、指定资金、清零新开；实盘部分已暂缓。

- [007 — 模拟盘与投研工作台](007-paper-research-workbench/spec.md)：当前范围、指数、历史统计、资金采集、研报财报研究及数据缺口。
- [008 — 新闻、流动性与板块轮动](008-news-liquidity-sector-rotation/spec.md)：策略研究优先新闻/央行流动性和行业轮动，再落到个股。

- [009 — 密码登录与火山短信](009-password-login-and-volc-sms/spec.md)：默认密码登录、密码交易确认，可选火山短信登录保护，替代强制验证器。
- [010 — 大盘指数快照与订阅行情](010-live-index-feed/spec.md)：每秒本机快照展示、公共源批量采集和可选 Longbridge 订阅。
- [011 — 股票投研数据底座、研报检索与关联证据](011-research-data-foundation/spec.md)：保留 llm-wiki 记忆层，建设时点化事实、文档索引、关系证据和可复现的列式分析快照；[选型调研](../docs/STORAGE_ENGINE_RESEARCH.md)。
