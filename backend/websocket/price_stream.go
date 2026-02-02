package websocket

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/adshao/go-binance/v2"
)

type PriceUpdate struct {
	Symbol    string
	Price     string
	Timestamp int64
}

type PriceStreamer struct {
	symbol       string
	updateChan   chan PriceUpdate
	errorChan    chan error
	stopChan     chan struct{}
	isRunning    bool
}

// NewPriceStreamer creates a new price streamer for a given symbol
func NewPriceStreamer(symbol string) *PriceStreamer {
	return &PriceStreamer{
		symbol:     symbol,
		updateChan: make(chan PriceUpdate, 100),
		errorChan:  make(chan error, 10),
		stopChan:   make(chan struct{}),
		isRunning:  false,
	}
}

// Start begins listening to price updates via WebSocket
func (ps *PriceStreamer) Start() error {
	if ps.isRunning {
		return fmt.Errorf("streamer already running")
	}

	ps.isRunning = true
	go ps.startStream()
	
	log.Printf("🚀 Started WebSocket stream for %s", ps.symbol)
	return nil
}

// Stop gracefully stops the WebSocket stream
func (ps *PriceStreamer) Stop() {
	if ps.isRunning {
		close(ps.stopChan)
		ps.isRunning = false
		log.Println("🛑 Stopped WebSocket stream")
	}
}

// GetUpdateChannel returns the channel for price updates
func (ps *PriceStreamer) GetUpdateChannel() <-chan PriceUpdate {
	return ps.updateChan
}

// GetErrorChannel returns the channel for errors
func (ps *PriceStreamer) GetErrorChannel() <-chan error {
	return ps.errorChan
}

// startStream internal goroutine to handle WebSocket connection
func (ps *PriceStreamer) startStream() {
	for {
		select {
		case <-ps.stopChan:
			return
		default:
			ps.connectAndListen()
			// Wait before reconnecting
			time.Sleep(5 * time.Second)
			log.Println("♻️  Attempting to reconnect...")
		}
	}
}

// connectAndListen establishes WebSocket connection and listens for updates
func (ps *PriceStreamer) connectAndListen() {
	wsTradeHandler := func(event *binance.WsTradeEvent) {
		update := PriceUpdate{
			Symbol:    event.Symbol,
			Price:     event.Price,
			Timestamp: event.Time,
		}
		
		select {
		case ps.updateChan <- update:
			log.Printf("💰 %s: %s", update.Symbol, update.Price)
		default:
			// Channel full, skip this update
		}
	}

	errHandler := func(err error) {
		log.Printf("⚠️  WebSocket error: %v", err)
		select {
		case ps.errorChan <- err:
		default:
		}
	}

	// Subscribe to trade stream (most real-time data)
	doneC, stopC, err := binance.WsTradeServe(ps.symbol, wsTradeHandler, errHandler)
	if err != nil {
		log.Printf("❌ Failed to start WebSocket: %v", err)
		ps.errorChan <- err
		return
	}

	// Wait for done signal or stop command
	select {
	case <-ps.stopChan:
		stopC <- struct{}{}
		return
	case <-doneC:
		log.Println("⚠️  WebSocket connection closed")
		return
	}
}

// StartKlineStream alternative method for Kline/Candlestick data
func (ps *PriceStreamer) StartKlineStream(interval string) error {
	if ps.isRunning {
		return fmt.Errorf("streamer already running")
	}

	ps.isRunning = true
	go ps.startKlineStream(interval)
	
	log.Printf("🚀 Started Kline stream for %s (%s interval)", ps.symbol, interval)
	return nil
}

func (ps *PriceStreamer) startKlineStream(interval string) {
	wsKlineHandler := func(event *binance.WsKlineEvent) {
		kline := event.Kline
		update := PriceUpdate{
			Symbol:    event.Symbol,
			Price:     kline.Close,
			Timestamp: event.Time,
		}
		
		select {
		case ps.updateChan <- update:
			log.Printf("📊 %s [%s]: %s", update.Symbol, interval, update.Price)
		default:
		}
	}

	errHandler := func(err error) {
		log.Printf("⚠️  Kline WebSocket error: %v", err)
		select {
		case ps.errorChan <- err:
		default:
		}
	}

	doneC, stopC, err := binance.WsKlineServe(ps.symbol, interval, wsKlineHandler, errHandler)
	if err != nil {
		log.Printf("❌ Failed to start Kline WebSocket: %v", err)
		ps.errorChan <- err
		return
	}

	select {
	case <-ps.stopChan:
		stopC <- struct{}{}
		return
	case <-doneC:
		log.Println("⚠️  Kline WebSocket connection closed")
		return
	}
}

// GetCurrentPrice fetches current price using REST API (for initial state)
func GetCurrentPrice(symbol string) (string, error) {
	client := binance.NewClient("", "")
	prices, err := client.NewListPricesService().Symbol(symbol).Do(context.Background())
	if err != nil {
		return "", err
	}

	if len(prices) > 0 {
		return prices[0].Price, nil
	}

	return "", fmt.Errorf("no price data for %s", symbol)
}
