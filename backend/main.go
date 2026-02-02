package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/aphis/24hrt-backend/client"
	"github.com/aphis/24hrt-backend/config"
	"github.com/aphis/24hrt-backend/server"
	"github.com/aphis/24hrt-backend/websocket"
)

func main() {
	// Set log output to stdout instead of stderr
	log.SetOutput(os.Stdout)
	
	log.Println("🚀 Starting 24HrT Trading Bot Backend...")

	// Load configuration
	cfg := config.Load()
	
	// Validate API keys
	if cfg.BinanceAPIKey == "" || cfg.BinanceAPIKey == "your_testnet_api_key_here" {
		log.Println("⚠️  Warning: No valid API key found!")
		log.Println("📝 Get testnet keys from: https://testnet.binance.vision/")
		log.Println("📝 Then create a .env file with your keys")
	}

	// Create trading client
	tradingClient := client.NewTradingClient(cfg)

	// Test connectivity
	if err := tradingClient.TestConnectivity(); err != nil {
		log.Printf("❌ Failed to connect: %v", err)
		log.Println("💡 Make sure you're using valid API keys")
		return
	}

	// Get server time
	if _, err := tradingClient.GetServerTime(); err != nil {
		log.Printf("⚠️  Warning: %v", err)
	}

	// Get account balance (only if API keys are valid)
	if cfg.BinanceAPIKey != "" && cfg.BinanceAPIKey != "your_testnet_api_key_here" {
		if _, err := tradingClient.GetAccountBalance(); err != nil {
			log.Printf("⚠️  Could not fetch balance: %v", err)
		}
	}

	// Create HTTP server for Electron communication with trading client
	httpServer := server.NewServer(tradingClient)

	// Start HTTP server in a goroutine
	go func() {
		if err := httpServer.Start("8080"); err != nil {
			log.Printf("❌ HTTP server error: %v", err)
		}
	}()

	// Start WebSocket price stream
	priceStreamer := websocket.NewPriceStreamer(cfg.DefaultSymbol)
	if err := priceStreamer.Start(); err != nil {
		log.Printf("❌ Failed to start price stream: %v", err)
		return
	}
	defer priceStreamer.Stop()

	// Handle price updates and send to HTTP server
	go func() {
		for update := range priceStreamer.GetUpdateChannel() {
			// Send price to all connected WebSocket clients (Electron)
			httpServer.SendPrice(update.Symbol, update.Price, update.Timestamp)
			
			// Log occasionally for debugging (uncomment if needed)
			// log.Printf("💰 Price Update: %s = %s", update.Symbol, update.Price)
		}
	}()

	// Handle WebSocket errors
	go func() {
		for err := range priceStreamer.GetErrorChannel() {
			log.Printf("⚠️  Stream error: %v", err)
		}
	}()

	log.Println("✅ Backend is running!")
	log.Printf("📊 Watching %s price updates...", cfg.DefaultSymbol)
	log.Println("🌐 HTTP Server: http://localhost:8080")
	log.Println("🔌 WebSocket: ws://localhost:8080/api/price")
	log.Println("Press Ctrl+C to stop")

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	log.Println("\n👋 Shutting down gracefully...")
	time.Sleep(500 * time.Millisecond)
}
