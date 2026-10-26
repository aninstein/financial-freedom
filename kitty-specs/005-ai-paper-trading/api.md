# 005 · API 增量（统一 /api/v1）

全部接口需要已完成MFA的会话；所有写请求携带CSRF。

| 接口                                 | 说明                                                                                                                       |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| GET /paper/markets                   | 五市场、币种、默认初始资金、基础规则                                                                                       |
| POST /paper/accounts                 | label、market、initial_cash；Idempotency-Key必填，返回独立模拟账户                                                         |
| GET /accounts                        | 兼容接口；模拟账户增加market、equity、available_cash、frozen_cash、positions.sellable/cost/估值时点等                      |
| GET /paper/contracts/{instrument_id} | 港股逐证券每手股数及来源，其他市场固定基础规则                                                                             |
| PUT /paper/contracts/{instrument_id} | lot_size、note；手工模拟规则7天有效，已有挂单不可修改                                                                      |
| POST /paper/contracts/sync-hk        | 固定官方HKEX清单导入，保留来源URL、更新时间；不接受自由URL                                                                 |
| POST /paper/quotes/pull              | instrument_id；加入关注队列并请求带时间戳的单股报价，返回来源及executable                                                  |
| POST /paper/orders/preview           | 兼容原订单结构，统一风控预览；无副作用                                                                                     |
| POST /paper/orders                   | 同上；Idempotency-Key必填；市价需新鲜行情，限价可等待；返回filled/accepted                                                 |
| GET /paper/orders                    | account_id可选、offset>=0、limit<=200（默认50），返回最新订单列表                                                          |
| POST /paper/orders/{id}/cancel       | 仅撤未成交单，重复撤同一已撤单幂等，释放冻结                                                                               |
| POST /paper/ai/runs                  | account_id、objective、instruments[1..10]、max_notional、max_orders[1..5]、authorize=true；Idempotency-Key必填，202返回run |
| GET /paper/ai/runs                   | 最新20轮，可按account_id筛选，limit<=100                                                                                   |
| GET /paper/ai/runs/{id}              | 任务授权、模型、总结/错误、证据和实际订单                                                                                  |
| POST /paper/ai/runs/{id}/stop        | 原子禁止后续AI写入，撤销本轮全部未成交订单；已成交不回滚                                                                   |

AI工具不接受account_id，由服务端绑定；place_paper_trade还要求reason和稳定client_order_id。交易只接受普通股票；market选择US/HK/CN_MAIN/CN_CHINEXT/CN_STAR；CN_ALL仅供历史兼容账户，不可新开。
