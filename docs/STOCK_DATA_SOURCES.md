# 个股数据来源与接口选择

调研日期：2026-10-26。公开资料接口与授权数据服务分开处理。

| 类别 | 本期实现 | 来源与边界 |
|---|---|---|
| OHLC/成交量 | 本地真实日线；腾讯/新浪/东财/SGE适配器 | 保存来源与单位，非复权；周/月由已有日线聚合 |
| 公司概况 | A股stock_profile_cninfo；港股stock_hk_company_profile_em | 巨潮资讯/东方财富；原始文本和单位 |
| 盘口/估值 | 东方财富结构化单票行情查询（字段参考stock_individual_info_em / stock_bid_ask_em） | 东方财富公开网页字段；不承诺实时SLA或Level-2 |
| 财务摘要与三表 | A股stock_financial_abstract + 东财报告期利润/资产负债/现金流；港股年度分析 | 原报告期与指标，不将累计披露期误称实时财务 |
| 股东 | stock_zh_a_gdhs_detail_em / stock_gdfx_top_10_em | 股东户数与按明确披露期查询的十大股东，非实时持仓 |
| 分红 | stock_history_dividend_detail | 新浪历史分红，单位和除权日期保留原值 |
| 个股资金 | stock_individual_fund_flow | 成交分类估计，非北向逐笔、基金真实交易 |
| 公告 | 东方财富公开公告JSON查询（单标的/20条） | 非正式OpenAPI契约；可跳原公告 |
| 新闻/主营/研报目录 | stock_news_em / stock_zygc_em / stock_research_report_em | 相关新闻与正式披露区别展示 |

AKShare官方文档列出了[个股信息、行情、公司和财务等股票接口](https://akshare.akfamily.xyz/data/stock/stock.html)，因此本期优先复用已有适配器，避免在页面里散落爬虫逻辑。上游超时或改字段时，各分项独立显示错误/过期缓存。

东方财富有正式的[Choice量化接口](https://quantapi.eastmoney.com/)，提供[产品手册](https://quantapi.eastmoney.com/Manual)及[SDK下载](https://quantapi.eastmoney.com/Download?from=web)。它需要独立账号、SDK及相应数据权限，不能把push2、公开公告JSON或AKShare称为已经接通的官方Choice API。本期未安装Choice SDK、未采购权限、未调用券商交易接口。

[Tushare Pro的数据接口](https://tushare.pro/document/2?doc_id=25)也可作为有明确鉴权和权限要求的数据源；目前保留为后续替换选项，不把未配置的Token或权限当作已接入。

外部链接按验证过的证券格式构造；服务端没有接收任意URL的抓取接口。美国市场可跳SEC/Nasdaq、港股可跳披露易；本期没有声称覆盖东方财富网站的全部字段、研报全文、Level-2或全部海外基本面。

## 新闻 / 央行 / 轮动

- 财联社电报及东方财富财经快讯：AKShare [stock_info源码](https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_info.py)，分源60秒轮询，非授权秒级SLA，发布时间不等于首次观察时间。
- [央行公开市场业务交易公告目录](https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html)：固定域名HTTPS抓取原文与表格，按期限保留操作量及未披露字段，不借公告操作量推算净投放。
- 行业轮动使用AKShare [stock_sector_fund_flow_rank源码](https://github.com/akfamily/akshare/blob/main/akshare/stock/stock_fund_em.py) 的今日/5日/10日窗口；收益排名独立于资金排名，分类估计资金不当作机构真实流水。不同窗口源未给明确交易所时间，可能不同步。
- 指数：依据[AKShare官方指数文档](https://akshare.akfamily.xyz/data/index/index.html)分别使用中国股票指数日线和全球指数历史，不借同代码股票行情代替指数。
