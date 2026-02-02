package websocket

import (
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/adshao/go-binance/v2"
)

// KlineUpdate represents a candlestick update - MUST MATCH Lightweight Charts format
type KlineUpdate struct {
	Symbol string  `json:"symbol"`
	Time   int64   `json:"time"`   // Unix timestamp in seconds
	Open   float64 `json:"open"`
	High   float64 `json:"high"`
	Low    float64 `json:"low"`
	Close  float64 `json:"close"`
	Volume float64 `json:"volume"`
}

// KlineStreamer manages WebSocket connection to Binance kline streams
type KlineStreamer struct {
	symbol       string
	interval     string
	updateChan   chan KlineUpdate
	errorChan    chan error
	stopChan     chan struct{}
	isRunning    bool
	doneC        chan struct{}
	stopC        chan struct{}
	errC         chan error
	buffer       *DataBuffer // Add buffering capability
	mu           sync.Mutex  // Add mutex for thread safety
	compression  bool        // Enable data compression for better performance
}

// NewKlineStreamer creates a new kline streamer for a given symbol and interval
func NewKlineStreamer(symbol, interval string) *KlineStreamer {
	return &KlineStreamer{
		symbol:      symbol,
		interval:    interval,
		updateChan:  make(chan KlineUpdate, 100),
		errorChan:   make(chan error, 10),
		stopChan:    make(chan struct{}),
		doneC:       make(chan struct{}),
		stopC:       make(chan struct{}),
		errC:        make(chan error),
		isRunning:   false,
		buffer:      NewDataBuffer(symbol, interval), // Initialize buffer
		compression: true, // Enable compression by default
	}
}

// Start begins listening to kline updates via WebSocket
func (ks *KlineStreamer) Start() error {
	if ks.isRunning {
		return fmt.Errorf("streamer already running")
	}

	ks.isRunning = true
	go ks.startStream()
	
	log.Printf("🚀 Started Kline WebSocket stream for %s (%s)", ks.symbol, ks.interval)
	return nil
}

// Stop gracefully stops the WebSocket stream
func (ks *KlineStreamer) Stop() {
	if ks.isRunning {
		close(ks.stopChan)
		ks.isRunning = false
		log.Printf("🛑 Stopped Kline WebSocket stream for %s", ks.symbol)
	}
}

// GetUpdateChannel returns the channel for kline updates
func (ks *KlineStreamer) GetUpdateChannel() <-chan KlineUpdate {
	return ks.updateChan
}

// GetErrorChannel returns the channel for errors
func (ks *KlineStreamer) GetErrorChannel() <-chan error {
	return ks.errorChan
}

// startStream internal goroutine to handle WebSocket connection
func (ks *KlineStreamer) startStream() {
	for {
		select {
		case <-ks.stopChan:
			return
		default:
			ks.connectAndListen()
			// Wait before reconnecting
			time.Sleep(5 * time.Second)
			log.Printf("♻️  Attempting to reconnect kline stream for %s...", ks.symbol)
		}
	}
}

// connectAndListen establishes WebSocket connection and listens for updates
func (ks *KlineStreamer) connectAndListen() {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("❌ Panic in kline stream: %v", r)
			ks.errorChan <- fmt.Errorf("panic: %v", r)
		}
	}()

	wsKlineHandler := func(event *binance.WsKlineEvent) {
		// Parse the kline data
		kline := event.Kline
		
		// Convert strings to float64
		open, _ := parseFloat(kline.Open)
		high, _ := parseFloat(kline.High)
		low, _ := parseFloat(kline.Low)
		close, _ := parseFloat(kline.Close)
		volume, _ := parseFloat(kline.Volume)
		
		// Convert millisecond timestamp to seconds (Lightweight Charts requirement)
		timeSeconds := kline.StartTime / 1000
		
		update := KlineUpdate{
			Symbol: event.Symbol,
			Time:   timeSeconds,
			Open:   open,
			High:   high,
			Low:    low,
			Close:  close,
			Volume: volume,
		}
		
		// Update buffer for snapshot capability
		ks.buffer.UpdateKline(update)
		
		select {
		case ks.updateChan <- update:
			// Only log on candle close to reduce noise
			if kline.IsFinal {
				log.Printf("🕯️  %s %s - Close: %.2f | O: %.2f H: %.2f L: %.2f | Vol: %.2f", 
					event.Symbol, ks.interval, close, open, high, low, volume)
			}
		default:
			// Channel full, skip this update
			log.Printf("⚠️  Channel full, skipping update")
		}
	}

	errHandler := func(err error) {
		log.Printf("❌ WebSocket error for %s: %v", ks.symbol, err)
		select {
		case ks.errorChan <- err:
		default:
		}
	}

	// Start WebSocket kline service
	doneC, stopC, err := binance.WsKlineServe(ks.symbol, ks.interval, wsKlineHandler, errHandler)
	if err != nil {
		log.Printf("❌ Failed to start kline WebSocket: %v", err)
		ks.errorChan <- err
		return
	}

	ks.doneC = doneC
	ks.stopC = stopC

	// Wait for done or stop signal
	select {
	case <-ks.stopChan:
		close(ks.stopC)
		return
	case <-ks.doneC:
		log.Printf("⚠️  Kline WebSocket closed for %s", ks.symbol)
		return
	}
}

// Helper function to parse string to float64
func parseFloat(s string) (float64, error) {
	var f float64
	_, err := fmt.Sscanf(s, "%f", &f)
	return f, err
}

// GetBuffer returns the data buffer for snapshot access
func (ks *KlineStreamer) GetBuffer() *DataBuffer {
	ks.mu.Lock()
	defer ks.mu.Unlock()
	return ks.buffer
}

// GetSnapshot returns current data snapshot for new clients
func (ks *KlineStreamer) GetSnapshot() map[string]interface{} {
	ks.mu.Lock()
	defer ks.mu.Unlock()
	
	snapshot := ks.buffer.GetSnapshot()
	snapshot["isRunning"] = ks.isRunning
	snapshot["clientCount"] = len(ks.updateChan) // Approximate client count
	
	return snapshot
}
