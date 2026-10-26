# Work packages

Implementation order and dependency map:

1. [WP01 — Domain and persistence](tasks/WP01-domain-persistence.md)
2. [WP02 — Provider and market calendar](tasks/WP02-provider-calendar.md) (depends on WP01)
3. [WP03 — Read API and historical store](tasks/WP03-market-api.md) (depends on WP01–02)
4. [WP04 — Accounts and paper trading](tasks/WP04-paper-trading.md) (depends on WP01–03)
5. [WP05 — Dashboard data wiring and operations guide](tasks/WP05-dashboard-operations.md) (depends on WP02–04)
6. [WP06 — Deterministic research baseline](tasks/WP06-research-baseline.md) (depends on WP01–03)

Package status is recorded in each work package. Core local workflows are implemented; upstream AKShare coverage remains partial in this runtime, so provider-dependent acceptance cannot be declared complete until the feeds work in the user's environment.
