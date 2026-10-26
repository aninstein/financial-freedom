---
version: alpha
colors:
  background: "#120F11"
  surface: "#1C171A"
  surfaceRaised: "#292125"
  text: "#F7EFEC"
  muted: "#B5A5AA"
  line: "#3E3035"
  primary: "#F47B68"
  primarySolid: "#B83E32"
  onPrimary: "#FFF5F1"
  primarySoft: "#322022"
  primaryLine: "#754039"
  shell: "#171214"
  marketUp: "#FF786F"
  marketDown: "#65C79A"
  ready: "#65C79A"
  secondary: "#DFA6A0"
  positive: "#F47B68"
  caution: "#F5AD4E"
  negative: "#FF8B91"
typography:
  sans:
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif"
  data:
    fontFamily: "'SF Mono', 'Cascadia Code', ui-monospace, monospace"
rounded:
  panel: "16px"
  control: "10px"
  pill: "999px"
spacing:
  unit: "4px"
  panel: "16px"
components:
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  primaryAction:
    backgroundColor: "{colors.primarySolid}"
    textColor: "{colors.onPrimary}"
    rounded: "{rounded.control}"
  brandLink:
    textColor: "{colors.primary}"
  analysisLabel:
    textColor: "{colors.secondary}"
  selectedNavigation:
    backgroundColor: "{colors.primarySoft}"
    textColor: "{colors.primary}"
  dialogBorder:
    backgroundColor: "{colors.primaryLine}"
  shellPanel:
    backgroundColor: "{colors.shell}"
  marketRise:
    textColor: "{colors.marketUp}"
  marketFall:
    textColor: "{colors.marketDown}"
  readyStatus:
    textColor: "{colors.ready}"
  raisedPanel:
    backgroundColor: "{colors.surfaceRaised}"
  primaryText:
    textColor: "{colors.text}"
  mutedLabel:
    textColor: "{colors.muted}"
  divider:
    backgroundColor: "{colors.line}"
  positiveStatus:
    textColor: "{colors.positive}"
  cautionStatus:
    textColor: "{colors.caution}"
  negativeStatus:
    textColor: "{colors.negative}"
---

## Overview

The product is a personal investing workspace with an AI research agent. Treat financial information as an instrument panel: legible, sourced, time-aware, and calm. The signature is an evidence rail that links every recommendation to its quote, market data, and strategy run. The experience is a product surface, not a trading terminal clone.

The reference is the project's supplied Duet AI concepts: warm graphite canvas, restrained vermilion and dusty rose accents, thin separators, compact conversation elements, and low visual noise. Keep the content specific to portfolios, market sessions, strategies, and evidence. Avoid generic purple AI gradients, glossy glass panels, and flashing trading effects.

The index page uses a compact quote board within this language: one featured index, ten small linked cards, tabular numerals, and fixed geometry. Price changes use the existing red-rise/green-fall tokens without flashing. Source and exchange timestamps remain in quiet text beside the numbers; live display cadence never overrides data freshness labels.

## Colors

Use background and surface for the shell and panels. Vermilion is the primary interactive accent; solid vermilion buttons use warm white labels. Dusty rose denotes AI analysis. Navigation selections, result cards, composer focus and modal headers share warm red tints. Positive, caution, and negative colors are semantic and must not carry meaning alone; pair them with labels or symbols. Preserve contrast for muted text and dense financial data. Quote changes, breadth bars and candlestick charts use a user-selected market palette: A-share view is red-rise/green-fall (default); US view is green-rise/red-fall. MA5/10/20/60 keep distinct line colors. Market direction uses dedicated tokens, separate from brand and error tones. A configured AI model with a ready local runtime uses a green status dot and a textual status; this does not claim that its remote provider has passed a live probe. Body text stays warm white for readable research and tables.

## Typography

Use the system sans stack for Chinese and English interface text. Use the monospace stack for prices, timestamps, symbols, and provenance IDs. Align numeric values with tabular figures when available. Do not depend on remote font loading.

## Layout

The primary surface is an Agent conversation, following the reference VOS/Duet workspace: left navigation and recent research, a quiet conversation canvas, and a right rail for personal watchlist and market clocks. Chat has a bottom composer and its own message scroller. The welcome state offers three concrete research starting points. Data is reached through separate routes, conversation links, and evidence-backed result cards.

Desktop navigation is 224px. At widths ≤1220px the context rail opens in an application modal; at ≤760px navigation uses a modal menu. Data pages use natural-height content within the canonical page scroller; wide tables own horizontal overflow. Keep every action available on narrow screens. Use URL state for market filters, search, paging and detail tabs.

Use a 4px base rhythm with 16px panel corners and 10px controls. Prefer fine separators to nested cards. Preserve generous conversation width and readable paragraph length. Financial tables can be denser than chat. Do not turn the homepage into a collection of dashboard widgets.

## Runtime Token Mapping

Ownership follows Model B: `prototype/styles.css :root` is canonical; this file mirrors its accepted palette. It maps colors to `--bg`, `--surface`, `--raised`, `--text`, `--muted`, `--line`, `--primary`, `--secondary`, `--positive`, `--caution`, `--negative`; added warm theme roles map `primarySolid/onPrimary/primarySoft/primaryLine/shell/marketUp/marketDown/ready` to `--primary-solid/--on-primary/--primary-soft/--primary-line/--shell/--market-up/--market-down/--ready`; the `:root[data-market-palette="us"]` override swaps only the two market colors. Type maps to `--sans` and `--mono`; radii map to `--panel-radius` and `--control-radius`. Shared renderer/interaction owners live in `prototype/ui.js`; route orchestration and palette state live in `prototype/app.js`. The palette selection is stored in browser localStorage under `finch.marketPalette`. No remote fonts or component framework is required. `prototype/stock.js` owns OHLC aggregation, candle/volume drawing and dossier rendering; `prototype/identity.js` owns sign-in, TOTP enrollment, recovery-code display and reauthentication forms.

Global scrollbars use `--scrollbar-thumb`, `--scrollbar-hover`, `--scrollbar-track`; forced colors restores system coloring. Native select and date popups are intentionally platform-owned. Details are recorded in `UX-CONTRACT.md`.

## Elevation & Depth

Use flat surfaces and one subtle raised surface for focus or selection. Avoid large shadows and glass blur. Sticky navigation must not obscure keyboard focus.

## Shapes

Panels use 16px corners, controls use 10px, and semantic statuses use pill shapes. Do not use rounded cards for every row; use dividers for repeated data.

## Components

Recommendations show direction, horizon, confidence, timestamp, data sources, strategy/backtest reference, and risk caveat. Account balances show institution, currency, as-of time, and connection status. Manual orders are previewed and risk-checked before confirmation. AI paper-trading rounds use a separate explicit mandate: fixed account, symbols, nominal order budget and order count. In the prototype, all order actions are paper-trading simulations.

## Do's and Don'ts

- Do distinguish observed data from AI interpretation.
- Do show source and freshness beside market claims.
- Do keep research chat read-only; only an explicitly authorized paper-trading round may execute within its server-enforced mandate.
- Do use Chinese labels and local numeric formatting in the current prototype.
- Don't imply guaranteed returns or hide uncertainty in a confidence score.
- Don't represent mock balances, quotes, or fills as live account data.

## Private Identity Surface

Unauthenticated screens use the existing warm graphite/vermilion tokens, a quiet identity panel and password fields with explicit reveal controls. Default sign-in consists only of account and password. Optional SMS appears after correct credentials, with masked recipient, user-triggered send, resend cooldown, expiration, inline failure and a return action. It never requires an authenticator app. The workspace stays hidden until full authentication, including SMS when enabled. Reauthentication asks only for the account password; no OTP field appears in transaction or password-change confirmation. Use the shared identity form helper, API security handler and application dialog.

## Stock Detail Surface

The price page is anchored by an OHLC chart with a separate volume band, labeled moving averages, source time and adjustment scope. Period and range controls change real data aggregation or visible samples. Raw financial datasets belong in separate subtabs, with report periods across table columns where possible. Keep external disclosure links near the source panel; distinguish news, announcements, research-directory metadata and user-imported originals.

## Paper Trading Surface

Reuse the vermilion panels, shared forms, market tones and modal confirmation. Account cards prioritize available cash and frozen resources; holdings show sellable quantity, cost and quote provenance. Opening an account and authorizing one AI round are separate actions. Execution records show actual ledger status alongside reasoning, with a visible stop-and-cancel action.

## Research And Paper Lifecycle Surfaces

The active product consists of chat, independent paper accounts, stock dossiers, index research, document research and flow coverage. The real broker surface is deferred and unregistered. Reuse the existing stock OHLC chart for index points, with a separate index route and explicit daily cutoff. Index data never appears as an executable stock.

Cycle statistics use shared stat cards, data tables and source footnotes. Always show sample dates and counts; show an em dash for unavailable statistics. Monthly seasonality is descriptive and labels small samples. Fund collection uses the shared form controls, field errors and per-fund source/status. Paper reset uses the shared destructive dialog, fresh identity verification and user-entered new capital. Preserve the warm graphite/vermilion theme and Chinese red-up/green-down convention.

## Macro And Sector Research Surfaces

News and central bank liquidity have their own routes. The sectors route combines sector rotation, capital flow, sector catalog and constituents; legacy rotation links resolve there. Headlines retain publication and first-observed timestamps; keyword associations are candidate tags. Liquidity groups original operations by tenor and keeps missing rates/maturity/net amounts empty. Rotation uses the existing table and pagination controls, red-up/green-down plus labels, and keeps cross-window rank differences separate from observed-date changes. Do not turn incomplete data into a signal badge implying profit or real-time certainty.
