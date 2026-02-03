package client

import (
	"context"
	"fmt"
	"log"
	"strconv"
	"time"

	"github.com/adshao/go-binance/v2"
	"github.com/aphis/24hrt-backend/config"
)

type TradingClient struct {
	client    *binance.Client
	apiKey    string
	secretKey string
	isTestnet bool
	timeOffset int64 // Cache server time offset
}

// NewTradingClient creates a new Binance trading client
func NewTradingClient(cfg *config.Config) *TradingClient {
	client := binance.NewClient(cfg.BinanceAPIKey, cfg.BinanceSecretKey)
	
	// Set testnet base URL if testnet mode is enabled
	if cfg.UseTestnet {
		client.BaseURL = "https://testnet.binance.vision"
		log.Println("🧪 Using Binance TESTNET")
	} else {
		log.Println("⚠️  Using Binance PRODUCTION - Real money!")
	}

	tc := &TradingClient{
		client:    client,
		apiKey:    cfg.BinanceAPIKey,
		secretKey: cfg.BinanceSecretKey,
		isTestnet: cfg.UseTestnet,
	}

	// Sync time with server and set time offset in the client BEFORE any API calls
	if err := tc.syncTimeAndApply(); err != nil {
		log.Printf("⚠️  Failed to sync time: %v", err)
	}

	return tc
}

// syncTimeAndApply synchronizes with server and immediately applies the offset
func (tc *TradingClient) syncTimeAndApply() error {
	// Get server time first (Binance returns UTC time in milliseconds)
	serverTime, err := tc.client.NewServerTimeService().Do(context.Background())
	if err != nil {
		return fmt.Errorf("failed to get server time: %w", err)
	}

	// IMPORTANT: Must use UTC time for comparison with Binance server
	// time.Now() returns local time, so we must explicitly use UTC()
	localTimeUTC := time.Now().UTC().UnixNano() / int64(time.Millisecond)
	
	// Calculate raw offset
	actualOffset := serverTime - localTimeUTC
	
	// Add safety buffer to ensure we're never ahead of server time
	// This prevents timestamp errors (-5 seconds buffer)
	tc.timeOffset = actualOffset - 5000
	
	// Apply to client
	tc.client.TimeOffset = tc.timeOffset
	
	log.Printf("🕐 Time synchronized (using UTC):")
	log.Printf("   Server time (UTC): %d", serverTime)
	log.Printf("   Local time (UTC):  %d", localTimeUTC)
	log.Printf("   System timezone:   %s", time.Now().Location().String())
	log.Printf("   Raw offset:        %dms", actualOffset)
	log.Printf("   Applied offset:    %dms (with -5000ms safety buffer)", tc.timeOffset)
	
	return nil
}

// syncTime re-synchronizes time (for periodic updates)
func (tc *TradingClient) syncTime() error {
	return tc.syncTimeAndApply()
}

// getServerTime returns synchronized server time
func (tc *TradingClient) getServerTime() int64 {
	localTime := time.Now().UnixNano() / int64(time.Millisecond)
	return localTime + tc.timeOffset
}

// OrderResult contains order execution details
type OrderResult struct {
	OrderID       int64
	Symbol        string
	Side          string
	Type          string
	Price         string
	Quantity      string
	Status        string
	ExecutedQty   string
	CummulativeQuoteQty string
}

// PlaceMarketBuyOrder places a market buy order
func (tc *TradingClient) PlaceMarketBuyOrder(symbol string, quantity string) (*OrderResult, error) {
	// Check if API keys are configured
	if tc.apiKey == "" || tc.apiKey == "your_testnet_api_key_here" {
		return nil, fmt.Errorf("API keys not configured. Please set up Binance testnet API keys")
	}

	// Resync time before placing order
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	order, err := tc.client.NewCreateOrderService().
		Symbol(symbol).
		Side(binance.SideTypeBuy).
		Type(binance.OrderTypeMarket).
		Quantity(quantity).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to place buy order: %w", err)
	}

	result := &OrderResult{
		OrderID:             order.OrderID,
		Symbol:              order.Symbol,
		Side:                string(order.Side),
		Type:                string(order.Type),
		Price:               order.Price,
		Quantity:            order.OrigQuantity,
		Status:              string(order.Status),
		ExecutedQty:         order.ExecutedQuantity,
		CummulativeQuoteQty: order.CummulativeQuoteQuantity,
	}

	log.Printf("✅ BUY Order placed: %s %s @ Market (OrderID: %d)", quantity, symbol, order.OrderID)
	return result, nil
}

// PlaceMarketSellOrder places a market sell order
func (tc *TradingClient) PlaceMarketSellOrder(symbol string, quantity string) (*OrderResult, error) {
	// Check if API keys are configured
	if tc.apiKey == "" || tc.apiKey == "your_testnet_api_key_here" {
		return nil, fmt.Errorf("API keys not configured. Please set up Binance testnet API keys")
	}

	// Resync time before placing order
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	order, err := tc.client.NewCreateOrderService().
		Symbol(symbol).
		Side(binance.SideTypeSell).
		Type(binance.OrderTypeMarket).
		Quantity(quantity).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to place sell order: %w", err)
	}

	result := &OrderResult{
		OrderID:             order.OrderID,
		Symbol:              order.Symbol,
		Side:                string(order.Side),
		Type:                string(order.Type),
		Price:               order.Price,
		Quantity:            order.OrigQuantity,
		Status:              string(order.Status),
		ExecutedQty:         order.ExecutedQuantity,
		CummulativeQuoteQty: order.CummulativeQuoteQuantity,
	}

	log.Printf("✅ SELL Order placed: %s %s @ Market (OrderID: %d)", quantity, symbol, order.OrderID)
	return result, nil
}

// PlaceLimitBuyOrder places a limit buy order
func (tc *TradingClient) PlaceLimitBuyOrder(symbol string, quantity string, price string) (*OrderResult, error) {
	// Check if API keys are configured
	if tc.apiKey == "" || tc.apiKey == "your_testnet_api_key_here" {
		return nil, fmt.Errorf("API keys not configured. Please set up Binance testnet API keys")
	}

	// Resync time before placing order
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	order, err := tc.client.NewCreateOrderService().
		Symbol(symbol).
		Side(binance.SideTypeBuy).
		Type(binance.OrderTypeLimit).
		TimeInForce(binance.TimeInForceTypeGTC).
		Quantity(quantity).
		Price(price).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to place limit buy order: %w", err)
	}

	result := &OrderResult{
		OrderID:  order.OrderID,
		Symbol:   order.Symbol,
		Side:     string(order.Side),
		Type:     string(order.Type),
		Price:    order.Price,
		Quantity: order.OrigQuantity,
		Status:   string(order.Status),
	}

	log.Printf("✅ LIMIT BUY Order placed: %s %s @ %s (OrderID: %d)", quantity, symbol, price, order.OrderID)
	return result, nil
}

// PlaceLimitSellOrder places a limit sell order
func (tc *TradingClient) PlaceLimitSellOrder(symbol string, quantity string, price string) (*OrderResult, error) {
	// Check if API keys are configured
	if tc.apiKey == "" || tc.apiKey == "your_testnet_api_key_here" {
		return nil, fmt.Errorf("API keys not configured. Please set up Binance testnet API keys")
	}

	// Resync time before placing order
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	order, err := tc.client.NewCreateOrderService().
		Symbol(symbol).
		Side(binance.SideTypeSell).
		Type(binance.OrderTypeLimit).
		TimeInForce(binance.TimeInForceTypeGTC).
		Quantity(quantity).
		Price(price).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to place limit sell order: %w", err)
	}

	result := &OrderResult{
		OrderID:  order.OrderID,
		Symbol:   order.Symbol,
		Side:     string(order.Side),
		Type:     string(order.Type),
		Price:    order.Price,
		Quantity: order.OrigQuantity,
		Status:   string(order.Status),
	}

	log.Printf("✅ LIMIT SELL Order placed: %s %s @ %s (OrderID: %d)", quantity, symbol, price, order.OrderID)
	return result, nil
}

// CancelOrder cancels an existing order
func (tc *TradingClient) CancelOrder(symbol string, orderID int64) error {
	// Resync time before canceling order
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	_, err := tc.client.NewCancelOrderService().
		Symbol(symbol).
		OrderID(orderID).
		Do(context.Background())

	if err != nil {
		return fmt.Errorf("failed to cancel order: %w", err)
	}

	log.Printf("🚫 Order cancelled: %d", orderID)
	return nil
}

// BalanceInfo represents account balance information
type BalanceInfo struct {
	Asset  string
	Free   string
	Locked string
}

// GetAccountBalance retrieves account balance information
func (tc *TradingClient) GetAccountBalance() ([]BalanceInfo, error) {
	// Check if API keys are configured
	if tc.apiKey == "" || tc.apiKey == "your_testnet_api_key_here" {
		return nil, fmt.Errorf("API keys not configured. Please set up Binance testnet API keys")
	}

	// Resync time before fetching balance to avoid timestamp errors
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	// Use RecvWindow to allow for more timestamp tolerance (10 seconds)
	account, err := tc.client.NewGetAccountService().Do(context.Background())
	if err != nil {
		return nil, fmt.Errorf("failed to get account info: %w", err)
	}

	var balances []BalanceInfo
	for _, balance := range account.Balances {
		if balance.Free != "0" || balance.Locked != "0" {
			balances = append(balances, BalanceInfo{
				Asset:  balance.Asset,
				Free:   balance.Free,
				Locked: balance.Locked,
			})
			log.Printf("💼 %s: %s (Free), %s (Locked)", balance.Asset, balance.Free, balance.Locked)
		}
	}

	return balances, nil
}

// PlaceMarketOrder places a market order (buy or sell)
func (tc *TradingClient) PlaceMarketOrder(symbol, side, quantity string) (*OrderResult, error) {
	if side == "BUY" {
		return tc.PlaceMarketBuyOrder(symbol, quantity)
	} else if side == "SELL" {
		return tc.PlaceMarketSellOrder(symbol, quantity)
	}
	return nil, fmt.Errorf("invalid order side: %s", side)
}

// GetOpenOrders retrieves all open orders for a symbol
func (tc *TradingClient) GetOpenOrders(symbol string) ([]*OrderResult, error) {
	// Resync time before fetching orders
	if err := tc.syncTime(); err != nil {
		log.Printf("⚠️  Time sync failed, proceeding anyway: %v", err)
	}

	orders, err := tc.client.NewListOpenOrdersService().
		Symbol(symbol).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to get open orders: %w", err)
	}

	results := make([]*OrderResult, len(orders))
	for i, order := range orders {
		results[i] = &OrderResult{
			OrderID:  order.OrderID,
			Symbol:   order.Symbol,
			Side:     string(order.Side),
			Type:     string(order.Type),
			Price:    order.Price,
			Quantity: order.OrigQuantity,
			Status:   string(order.Status),
		}
	}

	log.Printf("📋 Found %d open orders for %s", len(orders), symbol)
	return results, nil
}

// TestConnectivity tests connection to Binance API
func (tc *TradingClient) TestConnectivity() error {
	err := tc.client.NewPingService().Do(context.Background())
	if err != nil {
		return fmt.Errorf("connectivity test failed: %w", err)
	}

	log.Println("✅ Successfully connected to Binance API")
	return nil
}

// GetServerTime gets Binance server time (useful for debugging time sync issues)
func (tc *TradingClient) GetServerTime() (int64, error) {
	serverTime, err := tc.client.NewServerTimeService().Do(context.Background())
	if err != nil {
		return 0, fmt.Errorf("failed to get server time: %w", err)
	}

	log.Printf("🕐 Server time: %d", serverTime)
	return serverTime, nil
}

// KlineData represents candlestick data
type KlineData struct {
	OpenTime                 int64   `json:"openTime"`
	Open                     string  `json:"open"`
	High                     string  `json:"high"`
	Low                      string  `json:"low"`
	Close                    string  `json:"close"`
	Volume                   string  `json:"volume"`
	CloseTime                int64   `json:"closeTime"`
	QuoteAssetVolume         string  `json:"quoteAssetVolume"`
	NumberOfTrades           int     `json:"numberOfTrades"`
	TakerBuyBaseAssetVolume  string  `json:"takerBuyBaseAssetVolume"`
	TakerBuyQuoteAssetVolume string  `json:"takerBuyQuoteAssetVolume"`
}

// SymbolPrice represents symbol price information
type SymbolPrice struct {
	Symbol string `json:"symbol"`
	Price  string `json:"price"`
}

// GetSymbolPrices fetches all symbol prices from Binance
func (tc *TradingClient) GetSymbolPrices() ([]SymbolPrice, error) {
	prices, err := tc.client.NewListPricesService().Do(context.Background())
	if err != nil {
		return nil, fmt.Errorf("failed to get symbol prices: %w", err)
	}

	result := make([]SymbolPrice, len(prices))
	for i, price := range prices {
		result[i] = SymbolPrice{
			Symbol: price.Symbol,
			Price:  price.Price,
		}
	}

	log.Printf("📊 Fetched %d symbol prices from Binance", len(result))
	return result, nil
}

// GetKlines fetches historical candlestick data
func (tc *TradingClient) GetKlines(symbol, interval, limitStr string) ([]KlineData, error) {
	limit, err := strconv.Atoi(limitStr)
	if err != nil {
		limit = 100
	}

	klines, err := tc.client.NewKlinesService().
		Symbol(symbol).
		Interval(interval).
		Limit(limit).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to get klines: %w", err)
	}

	result := make([]KlineData, len(klines))
	for i, k := range klines {
		result[i] = KlineData{
			OpenTime:                 k.OpenTime,
			Open:                     k.Open,
			High:                     k.High,
			Low:                      k.Low,
			Close:                    k.Close,
			Volume:                   k.Volume,
			CloseTime:                k.CloseTime,
			QuoteAssetVolume:         k.QuoteAssetVolume,
			NumberOfTrades:           int(k.TradeNum),
			TakerBuyBaseAssetVolume:  k.TakerBuyBaseAssetVolume,
			TakerBuyQuoteAssetVolume: k.TakerBuyQuoteAssetVolume,
		}
	}

	log.Printf("📊 Fetched %d klines for %s (%s)", len(result), symbol, interval)
	return result, nil
}

// GetKlinesWithTimeRange fetches historical candlestick data with custom time range
func (tc *TradingClient) GetKlinesWithTimeRange(symbol, interval, startTime, endTime, limitStr string) ([]KlineData, error) {
	limit, err := strconv.Atoi(limitStr)
	if err != nil {
		limit = 500
	}

	// Parse start and end times
	start, err := strconv.ParseInt(startTime, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid start time: %w", err)
	}

	end, err := strconv.ParseInt(endTime, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid end time: %w", err)
	}

	klines, err := tc.client.NewKlinesService().
		Symbol(symbol).
		Interval(interval).
		StartTime(start).
		EndTime(end).
		Limit(limit).
		Do(context.Background())

	if err != nil {
		return nil, fmt.Errorf("failed to get klines with time range: %w", err)
	}

	result := make([]KlineData, len(klines))
	for i, k := range klines {
		result[i] = KlineData{
			OpenTime:                 k.OpenTime,
			Open:                     k.Open,
			High:                     k.High,
			Low:                      k.Low,
			Close:                    k.Close,
			Volume:                   k.Volume,
			CloseTime:                k.CloseTime,
			QuoteAssetVolume:         k.QuoteAssetVolume,
			NumberOfTrades:           int(k.TradeNum),
			TakerBuyBaseAssetVolume:  k.TakerBuyBaseAssetVolume,
			TakerBuyQuoteAssetVolume: k.TakerBuyQuoteAssetVolume,
		}
	}

	log.Printf("📊 Fetched %d klines for %s (%s) from %s to %s", 
		len(result), symbol, interval, 
		time.Unix(start/1000, 0).Format("2006-01-02 15:04:05"),
		time.Unix(end/1000, 0).Format("2006-01-02 15:04:05"))
	return result, nil
}
