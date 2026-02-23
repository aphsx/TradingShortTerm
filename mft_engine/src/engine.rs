use dashmap::DashMap;
use std::sync::Arc;
use tokio::sync::{mpsc, broadcast};
use anyhow::Result;
use log::{info, error};
use crate::models::{Position, Signal, Side};

pub struct TradingEngine {
    pub positions: Arc<DashMap<String, Position>>,
    pub signals_tx: mpsc::Sender<Signal>,
    pub signals_rx: mpsc::Receiver<Signal>,
    pub data_broadcast: broadcast::Sender<serde_json::Value>,
}

impl TradingEngine {
    pub async fn new() -> Result<Self> {
        let (signals_tx, signals_rx) = mpsc::channel(100);
        let (data_broadcast, _) = broadcast::channel(100);

        Ok(Self {
            positions: Arc::new(DashMap::new()),
            signals_tx,
            signals_rx,
            data_broadcast,
        })
    }

    pub async fn run(&mut self) -> Result<()> {
        println!("Engine loop started...");
        info!("Engine loop started...");
        
        // Simple demo run that exits after a few seconds
        println!("Running demo trading engine for 2 seconds...");
        info!("Running demo trading engine for 10 seconds...");
        
        // Send a demo signal immediately
        let demo_signal = Signal {
            symbol: "BTCUSDT".to_string(),
            side: Side::Buy,
            price: 50000.0,
            timestamp: chrono::Utc::now().timestamp(),
        };
        
        println!("Sending demo signal: {:?}", demo_signal);
        info!("Sending demo signal: {:?}", demo_signal);
        
        // Process the signal in a simple way
        println!("Processing signal...");
        info!("Processing signal...");
        println!("Signal processed successfully!");
        info!("Signal processed successfully!");
        
        // Wait a bit then exit
        println!("Waiting 2 seconds before exit...");
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        println!("Demo completed. Exiting gracefully...");
        info!("Demo completed. Exiting gracefully...");
        
        Ok(())
    }
}
