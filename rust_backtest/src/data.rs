use anyhow::Result;
use nautilus_model::data::{Data, QuoteTick};
use nautilus_model::identifiers::{InstrumentId, Symbol, Venue};
use nautilus_model::types::{Price, Quantity};
use reqwest::Client;
use serde::Deserialize;
use std::path::Path;
use polars::prelude::*;

#[derive(Debug, Deserialize)]
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

pub struct BinanceDownloader {
    client: Client,
}

impl BinanceDownloader {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
        }
    }

    pub async fn download_agg_trades(
        &self,
        symbol: &str,
        start_time: i64,
        end_time: i64,
    ) -> Result<Vec<Data>> {
        let url = format!(
            "https://fapi.binance.com/fapi/v1/aggTrades?symbol={}&startTime={}&endTime={}&limit=1000",
            symbol, start_time, end_time
        );

        let response = self.client.get(&url).send().await?.json::<Vec<BinanceAggTrade>>().await?;
        let instrument_id = InstrumentId::new(
            Symbol::from(format!("{}.BINANCE", symbol)),
            Venue::from("BINANCE")
        );

        let mut data = Vec::new();
        for t in response {
            let ts = (t.time * 1_000_000) as u64; // ms to ns
            let price = Price::from(t.price.as_str());
            let qty = Quantity::from(t.qty.as_str());
            
            // Order based on compiler error suggestion: BidPrice, AskPrice, BidSize, AskSize
            let quote = QuoteTick::new(
                instrument_id.clone(),
                price, // Bid Price
                price, // Ask Price
                qty,   // Bid Size
                qty,   // Ask Size
                ts.into(), // ts_event
                ts.into(), // ts_init
            );
            data.push(Data::Quote(quote));
        }

        Ok(data)
    }

    pub fn save_to_parquet(&self, data: &[Data], path: &Path) -> Result<()> {
        let mut timestamps = Vec::new();
        let mut prices = Vec::new();
        let mut quantities = Vec::new();

        for d in data {
            if let Data::Quote(q) = d {
                timestamps.push(u64::from(q.ts_event) as i64);
                prices.push(f64::from(q.bid_price));
                quantities.push(f64::from(q.bid_size));
            }
        }

        let mut df = df!(
            "timestamp" => timestamps,
            "price" => prices,
            "qty" => quantities,
        )?;

        let mut file = std::fs::File::create(path)?;
        ParquetWriter::new(&mut file).finish(&mut df)?;

        Ok(())
    }
}
