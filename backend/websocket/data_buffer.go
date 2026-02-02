package websocket

import (
	"log"
	"sync"
	"time"
)

// DataBuffer acts as a snapshot manager for latest data
// This ensures UI always has data when reconnecting
type DataBuffer struct {
	symbol      string
	interval    string
	latestKline *KlineUpdate
	klineHistory []KlineUpdate // Keep last 1000 candles for quick recovery
	maxHistory  int
	mu          sync.RWMutex
}

// NewDataBuffer creates a new data buffer for a symbol
func NewDataBuffer(symbol, interval string) *DataBuffer {
	return &DataBuffer{
		symbol:     symbol,
		interval:   interval,
		maxHistory: 1000,
		klineHistory: make([]KlineUpdate, 0, 1000),
	}
}

// UpdateKline updates the latest kline data
func (db *DataBuffer) UpdateKline(kline KlineUpdate) {
	db.mu.Lock()
	defer db.mu.Unlock()

	// Update latest
	db.latestKline = &kline

	// Add to history (only keep final candles to avoid duplicates)
	if len(db.klineHistory) == 0 || db.klineHistory[len(db.klineHistory)-1].Time != kline.Time {
		db.klineHistory = append(db.klineHistory, kline)
		
		// Keep only last maxHistory items
		if len(db.klineHistory) > db.maxHistory {
			db.klineHistory = db.klineHistory[1:]
		}
		
		log.Printf("📊 Buffered %s candles: %d (latest: %.2f)", 
			db.symbol, len(db.klineHistory), kline.Close)
	}
}

// GetLatestKline returns the most recent kline data
func (db *DataBuffer) GetLatestKline() *KlineUpdate {
	db.mu.RLock()
	defer db.mu.RUnlock()
	return db.latestKline
}

// GetHistory returns recent kline history for quick UI recovery
func (db *DataBuffer) GetHistory(limit int) []KlineUpdate {
	db.mu.RLock()
	defer db.mu.RUnlock()

	if limit <= 0 || limit > len(db.klineHistory) {
		limit = len(db.klineHistory)
	}

	// Return last 'limit' items
	start := len(db.klineHistory) - limit
	result := make([]KlineUpdate, limit)
	copy(result, db.klineHistory[start:])
	return result
}

// GetSnapshot returns a complete snapshot for new clients
func (db *DataBuffer) GetSnapshot() map[string]interface{} {
	db.mu.RLock()
	defer db.mu.RUnlock()

	snapshot := map[string]interface{}{
		"symbol":     db.symbol,
		"interval":   db.interval,
		"timestamp":  time.Now().Unix(),
		"latest":     db.latestKline,
		"history":    db.klineHistory,
		"historyLen": len(db.klineHistory),
	}

	return snapshot
}

// Clear clears all buffered data
func (db *DataBuffer) Clear() {
	db.mu.Lock()
	defer db.mu.Unlock()
	
	db.latestKline = nil
	db.klineHistory = db.klineHistory[:0]
	log.Printf("🧹 Cleared buffer for %s", db.symbol)
}
