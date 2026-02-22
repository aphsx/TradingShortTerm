use anyhow::Result;
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::Deserialize;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Deserialize)]
struct ServerTimeResponse {
    serverTime: i64,
}

pub struct TimeSync {
    client: Client,
    offset_ms: i64,
}

impl TimeSync {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            offset_ms: 0,
        }
    }

    /// Sync with Binance server time
    pub async fn sync(&mut self, testnet: bool) -> Result<()> {
        let base_url = if testnet {
            "https://testnet.binancefuture.com"
        } else {
            "https://fapi.binance.com"
        };

        let url = format!("{}/fapi/v1/time", base_url);
        
        // Measure round-trip time
        let local_before = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as i64;

        let response: ServerTimeResponse = self.client
            .get(&url)
            .send()
            .await?
            .json()
            .await?;

        let local_after = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as i64;

        // Calculate offset (server_time - estimated_local_time)
        let round_trip = local_after - local_before;
        let estimated_local = local_before + round_trip / 2;
        self.offset_ms = response.serverTime - estimated_local;

        println!("⏰ Time sync: offset {}ms", self.offset_ms);
        Ok(())
    }

    /// Get server-synced timestamp in milliseconds
    pub fn timestamp_ms(&self) -> i64 {
        let local_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_millis() as i64;
        local_ms + self.offset_ms
    }
}
