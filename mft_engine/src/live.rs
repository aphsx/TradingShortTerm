/// live.rs — Live Trading via Binance USDT-M Futures REST API
///
/// Implements signed REST order submission for Binance Futures.
/// Compatible with both testnet and mainnet (controlled via BINANCE_USE_TESTNET).
///
/// BINANCE FUTURES ORDER FLOW:
///   1. Build query string with required params
///   2. Append timestamp (server-synced preferred; we use local UTC)
///   3. Sign query string with HMAC-SHA256 using API secret
///   4. POST to /fapi/v1/order with X-MBX-APIKEY header
///
/// ORDER TYPES USED:
///   MARKET — for immediate fills (taker fee applies)
///   Futures require `positionSide` = BOTH for one-way mode,
///   or LONG/SHORT for hedge mode.  Default: one-way mode (BOTH).

use anyhow::{Context, Result};
use chrono::Utc;
use hmac::{Hmac, Mac};
use reqwest::{Client, StatusCode};
use serde::Deserialize;
use sha2::Sha256;
use tracing::{error, info, warn};
use crate::time_sync;

type HmacSha256 = Hmac<Sha256>;

// ── Response types ────────────────────────────────────────────────────────

#[derive(Deserialize, Debug)]
pub struct OrderResponse {
    #[serde(rename = "orderId")]
    pub order_id:     i64,
    pub symbol:       String,
    pub status:       String,
    #[serde(rename = "type")]
    pub order_type:   String,
    pub side:         String,
    #[serde(rename = "origQty")]
    pub orig_qty:     String,
    #[serde(rename = "executedQty")]
    pub executed_qty: String,
    #[serde(rename = "avgPrice")]
    pub avg_price:    String,
}

#[derive(Deserialize, Debug)]
pub struct BinanceError {
    pub code: i64,
    pub msg:  String,
}

// ── Live Order Client ─────────────────────────────────────────────────────

pub struct LiveOrderClient {
    client:     Client,
    api_key:    String,
    api_secret: String,
    base_url:   String,
    time_sync:  time_sync::TimeSync,
}

impl LiveOrderClient {
    pub fn new(api_key: &str, api_secret: &str, base_url: &str) -> Self {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(10))
            .build()
            .expect("HTTP client build failed");
        Self {
            client,
            api_key:    api_key.to_owned(),
            api_secret: api_secret.to_owned(),
            base_url:   base_url.to_owned(),
            time_sync:  time_sync::TimeSync::new(),
        }
    }

    /// Sign a query string with HMAC-SHA256.
    fn sign(&self, query: &str) -> String {
        let mut mac = HmacSha256::new_from_slice(self.api_secret.as_bytes())
            .expect("HMAC key error");
        mac.update(query.as_bytes());
        hex::encode(mac.finalize().into_bytes())
    }

    /// Sync time with Binance server
    pub async fn sync_time(&mut self, testnet: bool) -> Result<()> {
        self.time_sync.sync(testnet).await
    }

    /// Current Unix timestamp in milliseconds (server-synced).
    fn timestamp_ms(&self) -> i64 {
        self.time_sync.timestamp_ms()
    }

    /// Place a MARKET order on Binance Futures.
    ///
    /// # Arguments
    /// * `symbol`    — e.g. "BTCUSDT"
    /// * `side`      — "BUY" or "SELL"
    /// * `quantity`  — base asset quantity (e.g. 0.001 BTC)
    ///
    /// Returns the order response on success.
    pub async fn market_order(
        &self,
        symbol:   &str,
        side:     &str,
        quantity: f64,
    ) -> Result<OrderResponse> {
        // Format quantity to 3 decimal places (BTC precision)
        let qty_str = format!("{:.3}", quantity);

        let ts = self.timestamp_ms();
        // Build query string (without signature)
        let params = format!(
            "symbol={}&side={}&type=MARKET&quantity={}&timestamp={}",
            symbol, side, qty_str, ts
        );
        let signature = self.sign(&params);
        let full_params = format!("{}&signature={}", params, signature);

        let url = format!("{}/fapi/v1/order", self.base_url);

        info!("Placing {} {} {} @ MARKET", side, qty_str, symbol);

        let resp = self.client
            .post(&url)
            .header("X-MBX-APIKEY", &self.api_key)
            .header("Content-Type", "application/x-www-form-urlencoded")
            .body(full_params)
            .send()
            .await
            .context("HTTP POST to /fapi/v1/order failed")?;

        let status = resp.status();
        let body   = resp.text().await.context("Failed to read response body")?;

        if status != StatusCode::OK {
            let api_err: Result<BinanceError, _> = serde_json::from_str(&body);
            match api_err {
                Ok(e) => error!("Binance API error {}: {}", e.code, e.msg),
                Err(_) => error!("HTTP {} — body: {}", status, body),
            }
            anyhow::bail!("Order placement failed: HTTP {}", status);
        }

        let order: OrderResponse = serde_json::from_str(&body)
            .context("Failed to parse order response")?;

        info!(
            "Order filled: id={} {} {} qty={}/{}  avgPx={}",
            order.order_id, order.side, order.symbol,
            order.executed_qty, order.orig_qty, order.avg_price
        );
        Ok(order)
    }

    /// Set leverage for a symbol (required before first trade).
    pub async fn set_leverage(
        &self,
        symbol:   &str,
        leverage: u32,
    ) -> Result<()> {
        let ts = self.timestamp_ms();
        let params = format!(
            "symbol={}&leverage={}&timestamp={}",
            symbol, leverage, ts
        );
        let signature = self.sign(&params);
        let full_params = format!("{}&signature={}", params, signature);

        let url = format!("{}/fapi/v1/leverage", self.base_url);

        let resp = self.client
            .post(&url)
            .header("X-MBX-APIKEY", &self.api_key)
            .header("Content-Type", "application/x-www-form-urlencoded")
            .body(full_params)
            .send()
            .await
            .context("Set leverage request failed")?;

        if resp.status() != StatusCode::OK {
            let body = resp.text().await?;
            anyhow::bail!("Set leverage failed: {}", body);
        }

        info!("Set leverage {}x for {}", leverage, symbol);
        Ok(())
    }

    /// Get current open positions for a symbol.
    pub async fn get_position(
        &self,
        symbol: &str,
    ) -> Result<Vec<serde_json::Value>> {
        let ts = self.timestamp_ms();
        let params = format!("symbol={}&timestamp={}", symbol, ts);
        let signature = self.sign(&params);

        let url = format!(
            "{}/fapi/v2/positionRisk?{}&signature={}",
            self.base_url, params, signature
        );

        let resp = self.client
            .get(&url)
            .header("X-MBX-APIKEY", &self.api_key)
            .send()
            .await
            .context("positionRisk request failed")?;

        let data: Vec<serde_json::Value> = resp.json().await
            .context("Failed to parse positionRisk")?;
        Ok(data)
    }

    /// Close all open positions for a symbol via opposite MARKET order.
    pub async fn close_all_positions(&self, symbol: &str) -> Result<()> {
        let positions = self.get_position(symbol).await?;
        for pos in positions {
            let amt: f64 = pos["positionAmt"].as_str()
                .and_then(|s| s.parse().ok())
                .unwrap_or(0.0);
            if amt.abs() < 1e-6 {
                continue;
            }
            let side = if amt > 0.0 { "SELL" } else { "BUY" };
            warn!("Force-closing position: {} qty={}", side, amt.abs());
            self.market_order(symbol, side, amt.abs()).await?;
        }
        Ok(())
    }
}
