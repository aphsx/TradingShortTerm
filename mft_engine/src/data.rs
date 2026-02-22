/// data.rs — Binance Futures REST Data Fetcher
///
/// Fetches kline (OHLCV) and aggregate trade data from Binance USDT-M Futures.
/// Supports both testnet (https://testnet.binancefuture.com) and mainnet.

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::Deserialize;
use tracing::{debug, info};

use crate::models::ofi::TradeTick;

// ── Kline (OHLCV) types ───────────────────────────────────────────────────

/// Parsed kline bar from Binance array response.
#[derive(Debug, Clone)]
pub struct Kline {
    pub open_time:  i64,
    pub open:       f64,
    pub high:       f64,
    pub low:        f64,
    pub close:      f64,
    pub volume:     f64,
    pub close_time: i64,
    pub quote_vol:  f64,
    pub n_trades:   i64,
    pub taker_buy_base_vol: f64,
}

impl Kline {
    /// Log-return of this bar: ln(close / open)
    pub fn log_return(&self) -> f64 {
        if self.open > 0.0 {
            (self.close / self.open).ln()
        } else {
            0.0
        }
    }

    /// Approximate buy/sell volume split.
    /// taker_sell ≈ total_vol − taker_buy
    pub fn taker_sell_vol(&self) -> f64 {
        (self.volume - self.taker_buy_base_vol).max(0.0)
    }

    /// Convert this bar to a synthetic TradeTick for OFI/VPIN (bar-level approximation).
    /// Uses taker buy fraction as OFI signal.
    pub fn to_tick(&self) -> TradeTick {
        let buy_frac = if self.volume > 0.0 {
            self.taker_buy_base_vol / self.volume
        } else {
            0.5
        };
        let is_buy = buy_frac > 0.5;
        TradeTick {
            price:  self.close,
            volume: self.volume,
            is_buy,
            ts_ms:  self.close_time,
        }
    }
}

// ── Binance Futures kline API response ────────────────────────────────────

/// Raw Binance kline array (12-element JSON array per bar).
/// Index layout: [open_time, open, high, low, close, volume, close_time,
///                quote_vol, n_trades, taker_buy_base, taker_buy_quote, ignore]
#[derive(Deserialize)]
struct RawKline(
    serde_json::Value, // 0: open_time (i64)
    serde_json::Value, // 1: open      (str)
    serde_json::Value, // 2: high      (str)
    serde_json::Value, // 3: low       (str)
    serde_json::Value, // 4: close     (str)
    serde_json::Value, // 5: volume    (str)
    serde_json::Value, // 6: close_time(i64)
    serde_json::Value, // 7: quote_vol (str)
    serde_json::Value, // 8: n_trades  (i64)
    serde_json::Value, // 9: taker_buy_base (str)
    serde_json::Value, // 10: taker_buy_quote (str)
    serde_json::Value, // 11: ignore
);

fn parse_f64(v: &serde_json::Value) -> f64 {
    match v {
        serde_json::Value::String(s) => s.parse().unwrap_or(0.0),
        serde_json::Value::Number(n) => n.as_f64().unwrap_or(0.0),
        _ => 0.0,
    }
}

fn parse_i64(v: &serde_json::Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

impl From<RawKline> for Kline {
    fn from(r: RawKline) -> Self {
        Kline {
            open_time:  parse_i64(&r.0),
            open:       parse_f64(&r.1),
            high:       parse_f64(&r.2),
            low:        parse_f64(&r.3),
            close:      parse_f64(&r.4),
            volume:     parse_f64(&r.5),
            close_time: parse_i64(&r.6),
            quote_vol:  parse_f64(&r.7),
            n_trades:   parse_i64(&r.8),
            taker_buy_base_vol: parse_f64(&r.9),
        }
    }
}

// ── Aggregate trade types ─────────────────────────────────────────────────

#[derive(Deserialize, Debug)]
pub struct BinanceAggTrade {
    #[serde(rename = "a")]
    pub agg_id: i64,
    #[serde(rename = "p")]
    pub price: String,
    #[serde(rename = "q")]
    pub qty: String,
    #[serde(rename = "T")]
    pub time: i64,
    #[serde(rename = "m")]
    pub is_buyer_maker: bool,
}

impl BinanceAggTrade {
    pub fn to_tick(&self) -> TradeTick {
        TradeTick {
            price:  self.price.parse().unwrap_or(0.0),
            volume: self.qty.parse().unwrap_or(0.0),
            // is_buyer_maker = true means the BUYER was the maker,
            // i.e. the SELLER was the aggressor → sell-initiated
            is_buy: !self.is_buyer_maker,
            ts_ms:  self.time,
        }
    }
}

// ── Downloader ────────────────────────────────────────────────────────────

pub struct BinanceDataClient {
    client:   Client,
    base_url: String,
}

impl BinanceDataClient {
    pub fn new(base_url: &str) -> Self {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .expect("Failed to build HTTP client");
        Self { client, base_url: base_url.to_owned() }
    }

    /// Fetch klines for a symbol with pagination support.
    ///
    /// Binance limit per request: 1500.  For longer histories, this function
    /// automatically paginates backwards from `end_time`.
    ///
    /// # Arguments
    /// * `symbol`   — e.g. "BTCUSDT"
    /// * `interval` — "1m", "5m", "15m", etc.
    /// * `limit`    — total bars requested (will paginate if > 1500)
    pub async fn fetch_klines(
        &self,
        symbol:   &str,
        interval: &str,
        limit:    u64,
    ) -> Result<Vec<Kline>> {
        let mut all_klines = Vec::new();
        let page_size = 1500u64.min(limit);
        let mut remaining = limit;
        let mut end_time: Option<i64> = None;

        while remaining > 0 {
            let fetch_n = remaining.min(page_size);
            let mut url = format!(
                "{}/fapi/v1/klines?symbol={}&interval={}&limit={}",
                self.base_url, symbol, interval, fetch_n
            );
            if let Some(et) = end_time {
                url.push_str(&format!("&endTime={}", et));
            }

            debug!("Fetching klines: {}", url);
            let raw: Vec<RawKline> = self.client
                .get(&url)
                .send()
                .await
                .context("HTTP request failed")?
                .json()
                .await
                .context("Failed to parse kline JSON")?;

            if raw.is_empty() {
                break;
            }

            let n_fetched = raw.len();
            let mut bars: Vec<Kline> = raw.into_iter().map(Kline::from).collect();

            // For pagination: next request ends just before oldest fetched bar
            end_time = Some(bars[0].open_time - 1);

            bars.reverse(); // oldest used as pagination cursor; re-reverse to chronological
            bars.reverse();
            all_klines.extend(bars);

            remaining  = remaining.saturating_sub(n_fetched as u64);
            if n_fetched < fetch_n as usize {
                break; // no more data
            }
        }

        all_klines.sort_by_key(|k| k.open_time);
        info!("Fetched {} klines for {} {}", all_klines.len(), symbol, interval);
        Ok(all_klines)
    }

    /// Fetch recent aggregate trades for tick-level OFI/VPIN.
    ///
    /// Returns ticks in chronological order.
    pub async fn fetch_agg_trades(
        &self,
        symbol:     &str,
        start_time: i64,
        end_time:   i64,
    ) -> Result<Vec<TradeTick>> {
        let url = format!(
            "{}/fapi/v1/aggTrades?symbol={}&startTime={}&endTime={}&limit=1000",
            self.base_url, symbol, start_time, end_time
        );

        let raw: Vec<BinanceAggTrade> = self.client
            .get(&url)
            .send()
            .await
            .context("aggTrades request failed")?
            .json()
            .await
            .context("Failed to parse aggTrades JSON")?;

        info!("Fetched {} agg trades", raw.len());
        Ok(raw.iter().map(|t| t.to_tick()).collect())
    }
}
