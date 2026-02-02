package client

import (
	"context"
	"fmt"
	"log"

	"github.com/adshao/go-binance/v2"
	"github.com/aphis/24hrt-backend/config"
)

type TradingClient struct {
	client    *binance.Client
	apiKey    string
	secretKey string
	isTestnet bool
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

	return &TradingClient{
		client:    client,
		apiKey:    cfg.BinanceAPIKey,
		secretKey: cfg.BinanceSecretKey,
		isTestnet: cfg.UseTestnet,
	}
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
