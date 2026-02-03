package config

import (
	"log"
	"os"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

type Config struct {
	BinanceAPIKey      string
	BinanceSecretKey   string
	UseTestnet         bool
	DefaultSymbol      string
	DefaultSymbols     []string
	WSReconnectDelay   int
}

var AppConfig *Config

// Load reads environment variables and initializes the config
func Load() *Config {
	// Load .env file if exists
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using system environment variables")
	}

	useTestnet, _ := strconv.ParseBool(getEnv("BINANCE_USE_TESTNET", "true"))
	wsReconnect, _ := strconv.Atoi(getEnv("WS_RECONNECT_DELAY", "5"))
	
	// Parse default symbols from comma-separated string
	symbolsStr := getEnv("DEFAULT_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT,XRPUSDT,DOTUSDT,DOGEUSDT,MATICUSDT")
	defaultSymbols := strings.Split(symbolsStr, ",")
	for i, symbol := range defaultSymbols {
		defaultSymbols[i] = strings.TrimSpace(symbol)
	}

	AppConfig = &Config{
		BinanceAPIKey:    getEnv("BINANCE_API_KEY", ""),
		BinanceSecretKey: getEnv("BINANCE_SECRET_KEY", ""),
		UseTestnet:       useTestnet,
		DefaultSymbol:    getEnv("DEFAULT_SYMBOL", "BTCUSDT"),
		DefaultSymbols:   defaultSymbols,
		WSReconnectDelay: wsReconnect,
	}

	return AppConfig
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
