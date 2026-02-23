/// data_adapter.rs — Data Adapter for NautilusTrader
///
/// Provides integration between MFT engine's parquet data format and NautilusTrader's
/// data catalog system. Handles conversion between Kline objects and NautilusTrader
/// market data formats.
///
/// Architecture:
/// ┌─────────────────────────────────────────────────────┐
/// │  MFT Parquet Files (BTCUSDT/, ETHUSDT/, etc.)       │
/// │        │                                            │
/// │        ▼                                            │
/// │  MFTDataAdapter (conversion layer)                  │
/// │        │                                            │
/// │   ┌────┴──────────────────────────────────┐        │
/// │   │  Format Converters                    │        │
/// │   │  ├─ Kline → QuoteTick                 │        │
/// │   │  ├─ Kline → TradeTick                 │        │
/// │   │  └─ Kline → Bar                       │        │
/// │   └────────────────────────────────────────┘        │
/// │        │                                            │
/// │        ▼                                            │
/// │  NautilusTrader DataEngine                          │
/// └─────────────────────────────────────────────────────┘

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;
use anyhow::{Result, anyhow};
use chrono::{DateTime, Utc, TimeZone};
use nautilus_core::nanos::UnixNanos;
use nautilus_data::catalog::DataCatalog;
use nautilus_data::clients::DataClient;
use nautilus_model::data::{
    Bar, BarSpecification, BarType, QuoteTick, TradeTick,
    bar::Bar,
    quote::QuoteTick,
    trade::TradeTick,
};
use nautilus_model::enums::{
    AggregationSource, BarAggregation, PriceType, 
    QuoteSide, OrderSide, AssetClass
};
use nautilus_model::identifiers::{
    InstrumentId, Symbol, Venue,
    trade_id::TradeId,
    order_id::OrderId,
};
use nautilus_model::instruments::Instrument;
use nautilus_model::types::{Price, Quantity, Money};
use polars::prelude::*;
use tracing::{info, warn, error};

use mft_engine::data::Kline;

/// Configuration for the data adapter
#[derive(Debug, Clone)]
pub struct DataAdapterConfig {
    /// Root path to parquet data files
    pub data_path: String,
    /// Available trading pairs
    pub symbols: Vec<String>,
    /// Venue name (e.g., "BINANCE")
    pub venue: String,
    /// Default bar specification
    pub bar_spec: BarSpecification,
}

impl Default for DataAdapterConfig {
    fn default() -> Self {
        Self {
            data_path: "./data".to_string(),
            symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string(), "SOLUSDT".to_string()],
            venue: "BINANCE".to_string(),
            bar_spec: BarSpecification {
                step: BarAggregation::Minute,
                aggregation_source: AggregationSource::External,
                price_type: PriceType::Last,
            },
        }
    }
}

/// Adapter to convert MFT parquet data to NautilusTrader format
pub struct MFTDataAdapter {
    config: DataAdapterConfig,
    instruments: HashMap<String, nautilus_model::instruments::crypto::CryptoPerpetual>,
    cached_data: HashMap<InstrumentId, Vec<Kline>>,
}

impl MFTDataAdapter {
    /// Create new data adapter
    pub fn new(config: DataAdapterConfig) -> Result<Self> {
        Ok(Self {
            config,
            instruments: HashMap::new(),
            cached_data: HashMap::new(),
        })
    }

    /// Load all available data from parquet files
    pub fn load_all_data(&mut self) -> Result<()> {
        info!("Loading data from {}...", self.config.data_path);
        
        for symbol in &self.config.symbols {
            self.load_symbol_data(symbol)?;
        }
        
        info!("Loaded data for {} symbols", self.cached_data.len());
        Ok(())
    }

    /// Load data for a specific symbol
    pub fn load_symbol_data(&mut self, symbol: &str) -> Result<()> {
        let symbol_path = Path::new(&self.config.data_path).join(symbol);
        if !symbol_path.exists() {
            warn!("Data directory not found for symbol: {}", symbol);
            return Ok(());
        }

        info!("Loading data for symbol: {}", symbol);
        
        // Find all parquet files for this symbol
        let mut klines = Vec::new();
        
        // Read parquet files (assuming single file per symbol for now)
        let parquet_files = glob::glob(&format!("{}/**/*.parquet", symbol_path.display()))?;
        
        for file_path in parquet_files {
            let file_path = file_path?;
            info!("Reading parquet file: {}", file_path.display());
            
            let mut df = polars::prelude::LazyFrame::scan_parquet(&file_path, Default::default())?
                .collect()?;
            
            // Convert DataFrame to Kline objects
            let symbol_klines = self.dataframe_to_klines(&df, symbol)?;
            klines.extend(symbol_klines);
        }
        
        // Sort by timestamp
        klines.sort_by_key(|k| k.open_time);
        
        let instrument_id = InstrumentId::from(format!("{}.{}", symbol, self.config.venue));
        self.cached_data.insert(instrument_id, klines);
        
        info!("Loaded {} klines for {}", 
              self.cached_data.get(&instrument_id).unwrap().len(), symbol);
        
        Ok(())
    }

    /// Convert polars DataFrame to Kline objects
    fn dataframe_to_klines(&self, df: &DataFrame, symbol: &str) -> Result<Vec<Kline>> {
        let mut klines = Vec::new();
        
        // Get column vectors
        let open_times = df.column("open_time")?.datetime()?;
        let opens = df.column("open")?.f64()?;
        let highs = df.column("high")?.f64()?;
        let lows = df.column("low")?.f64()?;
        let closes = df.column("close")?.f64()?;
        let volumes = df.column("volume")?.f64()?;
        
        for i in 0..df.height() {
            let open_time = open_times.get(i).unwrap();
            let open = opens.get(i).unwrap();
            let high = highs.get(i).unwrap();
            let low = lows.get(i).unwrap();
            let close = closes.get(i).unwrap();
            let volume = volumes.get(i).unwrap();
            
            // Convert timestamp (assuming milliseconds)
            let datetime = Utc.timestamp_millis_opt(open_time / 1_000_000)
                .single()
                .ok_or_else(|| anyhow!("Invalid timestamp: {}", open_time))?;
            
            let kline = Kline {
                symbol: symbol.to_string(),
                open_time: datetime,
                close_time: datetime + chrono::Duration::minutes(1), // Assuming 1-minute bars
                open,
                high,
                low,
                close,
                volume,
                quote_volume: volume * close, // Approximate
                count: 0,
                taker_buy_volume: volume * 0.5, // Estimate
                taker_buy_quote_volume: volume * close * 0.5,
            };
            
            klines.push(kline);
        }
        
        Ok(klines)
    }

    /// Convert Kline to NautilusTrader Bar
    pub fn kline_to_bar(&self, kline: &Kline, instrument_id: &InstrumentId) -> Result<Bar> {
        let ts_event = UnixNanos::from(kline.open_time.timestamp_nanos() as u64);
        let ts_init = ts_event;
        
        let open = Price::from(kline.open);
        let high = Price::from(kline.high);
        let low = Price::from(kline.low);
        let close = Price::from(kline.close);
        let volume = Quantity::from(kline.volume);
        
        let bar_spec = BarSpecification {
            step: BarAggregation::Minute,
            aggregation_source: AggregationSource::External,
            price_type: PriceType::Last,
        };
        
        let bar_type = BarType::new(instrument_id.clone(), bar_spec);
        
        Ok(Bar::new(
            bar_type,
            open,
            high,
            low,
            close,
            volume,
            ts_event,
            ts_init,
        ))
    }

    /// Convert Kline to QuoteTick
    pub fn kline_to_quote_tick(&self, kline: &Kline, instrument_id: &InstrumentId) -> Result<QuoteTick> {
        let ts_event = UnixNanos::from(kline.open_time.timestamp_nanos() as u64);
        let ts_init = ts_event;
        
        let bid_price = Price::from(kline.close * 0.999); // Simulate bid
        let ask_price = Price::from(kline.close * 1.001); // Simulate ask
        let bid_size = Quantity::from(kline.volume * 0.5);
        let ask_size = Quantity::from(kline.volume * 0.5);
        
        Ok(QuoteTick::new(
            instrument_id.clone(),
            bid_price,
            ask_price,
            bid_size,
            ask_size,
            ts_event,
            ts_init,
        ))
    }

    /// Convert Kline to TradeTick
    pub fn kline_to_trade_tick(&self, kline: &Kline, instrument_id: &InstrumentId) -> Result<TradeTick> {
        let ts_event = UnixNanos::from(kline.open_time.timestamp_nanos() as u64);
        let ts_init = ts_event;
        
        let price = Price::from(kline.close);
        let size = Quantity::from(kline.volume);
        let trade_id = TradeId::new(format!("{}_{}", kline.symbol, kline.open_time.timestamp()));
        let order_side = if kline.close > kline.open { 
            OrderSide::Buy 
        } else { 
            OrderSide::Sell 
        };
        
        Ok(TradeTick::new(
            instrument_id.clone(),
            price,
            size,
            order_side,
            trade_id,
            ts_event,
            ts_init,
        ))
    }

    /// Get cached data for an instrument
    pub fn get_data(&self, instrument_id: &InstrumentId) -> Option<&Vec<Kline>> {
        self.cached_data.get(instrument_id)
    }

    /// Get data within time range
    pub fn get_data_in_range(
        &self, 
        instrument_id: &InstrumentId,
        start: DateTime<Utc>,
        end: DateTime<Utc>
    ) -> Vec<&Kline> {
        if let Some(data) = self.cached_data.get(instrument_id) {
            data.iter()
                .filter(|k| k.open_time >= start && k.open_time <= end)
                .collect()
        } else {
            Vec::new()
        }
    }

    /// Create mock instruments for testing
    pub fn create_mock_instruments(&mut self) -> Result<()> {
        info!("Creating mock instruments...");
        
        for symbol in &self.config.symbols {
            let instrument_id = InstrumentId::from(format!("{}.{}", symbol, self.config.venue));
            
            // Create a basic crypto instrument
            // Note: This is a simplified mock implementation
            // In practice, you'd create proper Instrument objects with all required fields
            
            info!("Created mock instrument: {}", instrument_id);
        }
        
        Ok(())
    }

    /// Get available instrument IDs
    pub fn get_instrument_ids(&self) -> Vec<InstrumentId> {
        self.cached_data.keys().cloned().collect()
    }

    /// Get data statistics
    pub fn get_data_stats(&self) -> HashMap<String, String> {
        let mut stats = HashMap::new();
        
        for (instrument_id, data) in &self.cached_data {
            if let Some(first) = data.first() {
                if let Some(last) = data.last() {
                    stats.insert(
                        instrument_id.to_string(),
                        format!(
                            "bars: {}, start: {}, end: {}",
                            data.len(),
                            first.open_time.format("%Y-%m-%d %H:%M"),
                            last.open_time.format("%Y-%m-%d %H:%M")
                        )
                    );
                }
            }
        }
        
        stats
    }
}

/// Data client implementation for NautilusTrader integration
pub struct MFTDataClient {
    adapter: Arc<MFTDataAdapter>,
    current_instrument: Option<InstrumentId>,
}

impl MFTDataClient {
    pub fn new(adapter: Arc<MFTDataAdapter>) -> Self {
        Self {
            adapter,
            current_instrument: None,
        }
    }

    /// Set the current instrument for data retrieval
    pub fn set_instrument(&mut self, instrument_id: InstrumentId) {
        self.current_instrument = Some(instrument_id);
    }

    /// Get next bar in sequence
    pub fn next_bar(&mut self) -> Option<Bar> {
        if let Some(instrument_id) = &self.current_instrument {
            if let Some(data) = self.adapter.get_data(instrument_id) {
                // Return the first bar for now (in practice, you'd track position)
                if let Some(kline) = data.first() {
                    return self.adapter.kline_to_bar(kline, instrument_id).ok();
                }
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    #[test]
    fn test_data_adapter_config() {
        let config = DataAdapterConfig::default();
        assert_eq!(config.symbols.len(), 3);
        assert_eq!(config.venue, "BINANCE");
    }

    #[test]
    fn test_kline_to_bar() -> Result<()> {
        let config = DataAdapterConfig::default();
        let adapter = MFTDataAdapter::new(config)?;
        
        let kline = Kline {
            symbol: "BTCUSDT".to_string(),
            open_time: Utc::now(),
            close_time: Utc::now() + chrono::Duration::minutes(1),
            open: 50000.0,
            high: 50100.0,
            low: 49900.0,
            close: 50050.0,
            volume: 100.0,
            quote_volume: 5_005_000.0,
            count: 1000,
            taker_buy_volume: 60.0,
            taker_buy_quote_volume: 3_003_000.0,
        };
        
        let instrument_id = InstrumentId::from("BTCUSDT.BINANCE");
        let bar = adapter.kline_to_bar(&kline, &instrument_id)?;
        
        assert_eq!(bar.open.as_f64(), 50000.0);
        assert_eq!(bar.high.as_f64(), 50100.0);
        assert_eq!(bar.low.as_f64(), 49900.0);
        assert_eq!(bar.close.as_f64(), 50050.0);
        
        Ok(())
    }
}
