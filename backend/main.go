package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/aphis/24hrt-backend/client"
	"github.com/aphis/24hrt-backend/config"
	"github.com/aphis/24hrt-backend/server"
)

func main() {
	// Set log output to stdout instead of stderr
	log.SetOutput(os.Stdout)

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

	log.Println("✅ Backend is running!")
	log.Println("📊 Dynamic multi-symbol streaming enabled")
	log.Println("🌐 HTTP Server: http://localhost:8080")
	log.Println("🔌 WebSocket Price: ws://localhost:8080/api/price?symbol=BTCUSDT")
	log.Println("🕯️  WebSocket Klines: ws://localhost:8080/api/kline?symbol=BTCUSDT&interval=1m")
	log.Println("📈 REST Klines: http://localhost:8080/api/klines?symbol=BTCUSDT&interval=1m&limit=500")
	log.Println("💡 Streamers start automatically when clients connect")
	log.Println("Press Ctrl+C to stop")

	// Wait for interrupt signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	<-sigChan

	// Cleanup
	log.Println("🧹 Cleaning up...")
	httpServer.Cleanup()

	log.Println("\n👋 Shutting down gracefully...")
}
