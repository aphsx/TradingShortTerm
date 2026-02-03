package server

import (
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
	"sync"

	"github.com/aphis/24hrt-backend/client"
	"github.com/aphis/24hrt-backend/config"
	"github.com/aphis/24hrt-backend/websocket"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	ws "github.com/gorilla/websocket"
)

type ClientInfo struct {
	conn     *ws.Conn
	symbol   string
	interval string // For kline streams
}

type Server struct {
	router         *gin.Engine
	upgrader       ws.Upgrader
	priceClients   map[*ws.Conn]*ClientInfo
	klineClients   map[*ws.Conn]*ClientInfo
	clientsMux     sync.Mutex
	streamers      map[string]*websocket.PriceStreamer
	klineStreamers map[string]*websocket.KlineStreamer
	streamersMux   sync.Mutex
	tradingClient  *client.TradingClient
	broadcastHub   *websocket.BroadcastHub // Add enhanced broadcasting
}

type PriceMessage struct {
	Symbol    string `json:"symbol"`
	Price     string `json:"price"`
	Timestamp int64  `json:"timestamp"`
}

type OrderRequest struct {
	Symbol   string `json:"symbol" binding:"required"`
	Side     string `json:"side" binding:"required"`
	Quantity string `json:"quantity" binding:"required"`
	Type     string `json:"type"`
	Price    string `json:"price,omitempty"`
}

type BalanceResponse struct {
	Asset  string `json:"asset"`
	Free   string `json:"free"`
	Locked string `json:"locked"`
}

// NewServer creates a new HTTP server instance
func NewServer(tradingClient *client.TradingClient) *Server {
	gin.SetMode(gin.ReleaseMode)

	s := &Server{
		router:         gin.Default(),
		priceClients:   make(map[*ws.Conn]*ClientInfo),
		klineClients:   make(map[*ws.Conn]*ClientInfo),
		streamers:      make(map[string]*websocket.PriceStreamer),
		klineStreamers: make(map[string]*websocket.KlineStreamer),
		tradingClient:  tradingClient,
		broadcastHub:   websocket.NewBroadcastHub(), // Initialize broadcast hub
		upgrader: ws.Upgrader{
			CheckOrigin: func(r *http.Request) bool {
				return true
			},
		},
	}

	// Setup CORS
	config := cors.DefaultConfig()
	config.AllowAllOrigins = true
	config.AllowMethods = []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"}
	config.AllowHeaders = []string{"Origin", "Content-Type", "Authorization"}
	s.router.Use(cors.New(config))

	s.setupRoutes()
	
	// Start broadcast hub
	go s.broadcastHub.Run()
	
	return s
}

func (s *Server) setupRoutes() {
	api := s.router.Group("/api")
	{
		api.GET("/health", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{"status": "ok"})
		})
		api.GET("/price", s.handlePriceWebSocket)
		api.GET("/kline", s.handleKline)
		api.GET("/kline/history", s.handleKlineHistory)   // Historical data
		api.GET("/symbols", s.handleGetSymbols)           // Available symbols
		api.GET("/symbols/default", s.handleGetDefaultSymbols) // Default symbols from config
		api.GET("/intervals", s.handleGetIntervals)       // Available intervals
		api.POST("/order", s.handlePlaceOrder)
		api.GET("/balance", s.handleGetBalance)
		api.GET("/orders", s.handleGetOrders)             // Order history
		api.GET("/orders/open", s.handleGetOpenOrders)    // Open orders
		api.GET("/trades", s.handleGetTrades)             // Account trade history
		api.GET("/depth", s.handleGetDepth)               // Order book depth
		api.GET("/recent-trades", s.handleGetRecentTrades) // Recent public trades
		api.GET("/prices", s.handleGetAllPrices)          // All symbol prices
		api.GET("/ticker/24hr", s.handleGet24hrTicker)    // 24hr ticker data
	}
}

// handleKlineHistory handles historical data requests with custom date ranges
func (s *Server) handleKlineHistory(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	interval := c.DefaultQuery("interval", "1m")
	startTime := c.Query("startTime")
	endTime := c.Query("endTime")
	limit := c.DefaultQuery("limit", "500")

	log.Printf("📊 Historical data request: %s %s (limit: %s)", symbol, interval, limit)

	// If custom date range is provided
	if startTime != "" && endTime != "" {
		klines, err := s.tradingClient.GetKlinesWithTimeRange(symbol, interval, startTime, endTime, limit)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{
				"error":   err.Error(),
				"message": "Failed to fetch historical klines",
			})
			return
		}
		c.JSON(http.StatusOK, gin.H{
			"data":  klines,
			"count": len(klines),
			"range": fmt.Sprintf("%s - %s", startTime, endTime),
		})
		return
	}

	// Otherwise, use regular limit-based fetch
	klines, err := s.tradingClient.GetKlines(symbol, interval, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   err.Error(),
			"message": "Failed to fetch klines",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"data":  klines,
		"count": len(klines),
		"source": "api",
	})
}

// handleGetSymbols returns available trading symbols from Binance
func (s *Server) handleGetSymbols(c *gin.Context) {
	// Fetch real symbols from Binance API
	prices, err := s.tradingClient.GetSymbolPrices()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   err.Error(),
			"message": "Failed to fetch symbols from Binance",
		})
		return
	}

	// Extract symbol names from price data
	var symbols []string
	for _, price := range prices {
		// Only include USDT pairs for now to keep it clean
		if strings.HasSuffix(price.Symbol, "USDT") {
			symbols = append(symbols, price.Symbol)
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"symbols": symbols,
		"count":   len(symbols),
		"source":  "binance-api",
	})
}

// handleGetDefaultSymbols returns default symbols from config
func (s *Server) handleGetDefaultSymbols(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"symbols": config.AppConfig.DefaultSymbols,
		"count":   len(config.AppConfig.DefaultSymbols),
		"source":  "config",
	})
}

// handleGetIntervals returns available time intervals
func (s *Server) handleGetIntervals(c *gin.Context) {
	intervals := []string{
		"1m", "3m", "5m", "15m", "30m",
		"1h", "2h", "4h", "6h", "8h", "12h",
		"1d", "3d", "1w", "1M",
	}

	c.JSON(http.StatusOK, gin.H{
		"intervals": intervals,
		"count":     len(intervals),
	})
}

// handleGetOrders handles retrieving order history
func (s *Server) handleGetOrders(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	limitStr := c.DefaultQuery("limit", "20")
	
	limit, err := strconv.Atoi(limitStr)
	if err != nil {
		limit = 20
	}

	orders, err := s.tradingClient.GetAllOrders(symbol, limit)
	if err != nil {
		log.Printf("❌ Failed to fetch orders: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
		})
		return
	}

	log.Printf("📜 Retrieved %d orders for %s", len(orders), symbol)
	c.JSON(http.StatusOK, gin.H{
		"orders": orders,
		"count":  len(orders),
		"symbol": symbol,
	})
}

// handleGetOpenOrders handles retrieving open orders
func (s *Server) handleGetOpenOrders(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "")

	orders, err := s.tradingClient.GetOpenOrders(symbol)
	if err != nil {
		log.Printf("❌ Failed to fetch open orders: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
		})
		return
	}

	log.Printf("📋 Retrieved %d open orders", len(orders))
	c.JSON(http.StatusOK, gin.H{
		"orders": orders,
		"count":  len(orders),
		"symbol": symbol,
	})
}

func (s *Server) handleKline(c *gin.Context) {
	// Check if it's a WebSocket upgrade request
	if c.Request.Header.Get("Upgrade") == "websocket" {
		s.handleKlineWebSocket(c)
		return
	}

	// Otherwise, handle as REST API for historical data
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	interval := c.DefaultQuery("interval", "1m")
	limit := c.DefaultQuery("limit", "100")

	// First try to get from buffer for faster response
	s.streamersMux.Lock()
	if streamer, exists := s.klineStreamers[symbol+"_"+interval]; exists {
		buffer := streamer.GetBuffer()
		history := buffer.GetHistory(1000) // Get up to 1000 candles from buffer
		s.streamersMux.Unlock()
		
		if len(history) > 0 {
			log.Printf("📊 Serving %d candles from buffer for %s", len(history), symbol)
			c.JSON(http.StatusOK, gin.H{
				"data": history,
				"source": "buffer",
				"count": len(history),
			})
			return
		}
	}
	s.streamersMux.Unlock()

	// If no buffer data, fetch from Binance API
	klines, err := s.tradingClient.GetKlines(symbol, interval, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   err.Error(),
			"message": "Failed to fetch klines",
		})
		return
	}

	log.Printf("📊 Fetched %d klines from API for %s", len(klines), symbol)
	c.JSON(http.StatusOK, gin.H{
		"data": klines,
		"source": "api",
		"count": len(klines),
	})
}

// HandlePriceWebSocket upgrades HTTP to WebSocket for price streaming
func (s *Server) handlePriceWebSocket(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")

	conn, err := s.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("Failed to upgrade connection: %v", err)
		return
	}

	// Register new client with symbol info
	clientInfo := &ClientInfo{
		conn:   conn,
		symbol: symbol,
	}

	s.clientsMux.Lock()
	s.priceClients[conn] = clientInfo
	s.clientsMux.Unlock()

	log.Printf("🔌 New WebSocket client connected for %s (Total: %d)", symbol, len(s.priceClients))

	// Start price streamer for this symbol if not already running
	s.ensureStreamerRunning(symbol)

	// Wait for client to disconnect
	defer func() {
		s.clientsMux.Lock()
		delete(s.priceClients, conn)
		s.clientsMux.Unlock()
		conn.Close()
		log.Printf("🔌 Client disconnected (Remaining: %d)", len(s.priceClients))

		// Check if we should stop the streamer for this symbol
		s.checkStopStreamer(symbol)
	}()

	// Keep connection alive
	for {
		_, _, err := conn.ReadMessage()
		if err != nil {
			break
		}
	}
}

// handleKlineWebSocket upgrades HTTP to WebSocket for kline/candlestick streaming
func (s *Server) handleKlineWebSocket(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	interval := c.DefaultQuery("interval", "1m")

	conn, err := s.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("Failed to upgrade connection: %v", err)
		return
	}

	// Register client with broadcast hub for enhanced broadcasting
	client := s.broadcastHub.RegisterClient(conn, symbol, interval)

	log.Printf("🔌 New Kline WebSocket client connected for %s %s (Total: %d)", 
		symbol, interval, s.broadcastHub.GetClientCount())

	// Start kline streamer for this symbol+interval if not already running
	s.ensureKlineStreamerRunning(symbol, interval)

	// Send immediate snapshot if available
	s.streamersMux.Lock()
	if streamer, exists := s.klineStreamers[symbol+"_"+interval]; exists {
		snapshot := streamer.GetSnapshot()
		s.broadcastHub.SendSnapshot(client, snapshot)
	}
	s.streamersMux.Unlock()

	// Wait for client to disconnect
	defer func() {
		s.broadcastHub.UnregisterClient(client)
		log.Printf("🔌 Kline client disconnected (Remaining: %d)", s.broadcastHub.GetClientCount())

		// Check if we should stop the streamer for this symbol+interval
		s.checkStopKlineStreamer(symbol, interval)
	}()

	// Keep connection alive
	for {
		_, _, err := conn.ReadMessage()
		if err != nil {
			break
		}
	}
}

// ensureKlineStreamerRunning starts a kline streamer for the symbol+interval if not already running
func (s *Server) ensureKlineStreamerRunning(symbol, interval string) {
	s.streamersMux.Lock()
	defer s.streamersMux.Unlock()

	streamKey := fmt.Sprintf("%s_%s", symbol, interval)

	// Check if streamer already exists
	if _, exists := s.klineStreamers[streamKey]; exists {
		return
	}

	// Create and start new kline streamer
	streamer := websocket.NewKlineStreamer(symbol, interval)
	if err := streamer.Start(); err != nil {
		log.Printf("❌ Failed to start kline streamer for %s %s: %v", symbol, interval, err)
		return
	}

	s.klineStreamers[streamKey] = streamer
	log.Printf("🚀 Started kline streamer for %s %s", symbol, interval)

	// Handle kline updates for this symbol+interval
	go func() {
		for update := range streamer.GetUpdateChannel() {
			// Use enhanced broadcasting system
			s.broadcastHub.BroadcastToSymbol(symbol, map[string]interface{}{
				"type": "kline",
				"data": update,
			})
		}
	}()

	// Handle errors
	go func() {
		for err := range streamer.GetErrorChannel() {
			log.Printf("⚠️  Kline stream error for %s %s: %v", symbol, interval, err)
		}
	}()
}

// checkStopKlineStreamer stops the kline streamer if no clients are subscribed to it
func (s *Server) checkStopKlineStreamer(symbol, interval string) {
	// Check if any clients are still subscribed via broadcast hub
	targetClients := s.broadcastHub.GetClientsBySymbol(symbol)
	hasClients := false
	for _, client := range targetClients {
		if client.Interval == interval { // Use exported field
			hasClients = true
			break
		}
	}

	if !hasClients {
		streamKey := fmt.Sprintf("%s_%s", symbol, interval)
		s.streamersMux.Lock()
		if streamer, exists := s.klineStreamers[streamKey]; exists {
			streamer.Stop()
			delete(s.klineStreamers, streamKey)
			log.Printf("🛑 Stopped kline streamer for %s %s (no clients)", symbol, interval)
		}
		s.streamersMux.Unlock()
	}
}

// broadcastKline is deprecated - use BroadcastHub instead
// This function is kept for backward compatibility but should not be used
func (s *Server) broadcastKline(symbol, interval string, update websocket.KlineUpdate) {
	// Use enhanced broadcasting system instead
	s.broadcastHub.BroadcastToSymbol(symbol, map[string]interface{}{
		"type": "kline",
		"data": update,
	})
}

// ensureStreamerRunning starts a price streamer for the symbol if not already running
func (s *Server) ensureStreamerRunning(symbol string) {
	s.streamersMux.Lock()
	defer s.streamersMux.Unlock()

	// Check if streamer already exists
	if _, exists := s.streamers[symbol]; exists {
		return
	}

	// Create and start new streamer
	streamer := websocket.NewPriceStreamer(symbol)
	if err := streamer.Start(); err != nil {
		log.Printf("❌ Failed to start streamer for %s: %v", symbol, err)
		return
	}

	s.streamers[symbol] = streamer
	log.Printf("🚀 Started price streamer for %s", symbol)

	// Handle price updates for this symbol
	go func() {
		for update := range streamer.GetUpdateChannel() {
			// Use enhanced broadcasting system
			s.broadcastHub.BroadcastToSymbol(symbol, map[string]interface{}{
				"type": "price",
				"data": map[string]interface{}{
					"symbol":    update.Symbol,
					"price":     update.Price,
					"timestamp": update.Timestamp,
				},
			})
		}
	}()

	// Handle errors
	go func() {
		for err := range streamer.GetErrorChannel() {
			log.Printf("⚠️  Stream error for %s: %v", symbol, err)
		}
	}()
}

// checkStopStreamer stops the streamer if no clients are subscribed to it
func (s *Server) checkStopStreamer(symbol string) {
	s.clientsMux.Lock()
	hasClients := false
	for _, clientInfo := range s.priceClients {
		if clientInfo.symbol == symbol {
			hasClients = true
			break
		}
	}
	s.clientsMux.Unlock()

	if !hasClients {
		s.streamersMux.Lock()
		if streamer, exists := s.streamers[symbol]; exists {
			streamer.Stop()
			delete(s.streamers, symbol)
			log.Printf("🛑 Stopped price streamer for %s (no clients)", symbol)
		}
		s.streamersMux.Unlock()
	}
}

// broadcastPrice is deprecated - use BroadcastHub instead
// This function is kept for backward compatibility but should not be used
func (s *Server) broadcastPrice(symbol, price string, timestamp int64) {
	// Use enhanced broadcasting system instead
	s.broadcastHub.BroadcastToSymbol(symbol, map[string]interface{}{
		"type": "price",
		"data": map[string]interface{}{
			"symbol":    symbol,
			"price":     price,
			"timestamp": timestamp,
		},
	})
}

func (s *Server) handleGetBalance(c *gin.Context) {
	balances, err := s.tradingClient.GetAccountBalance()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	var response []BalanceResponse
	for _, bal := range balances {
		response = append(response, BalanceResponse{
			Asset:  bal.Asset,
			Free:   bal.Free,
			Locked: bal.Locked,
		})
	}

	c.JSON(http.StatusOK, gin.H{"balances": response})
}

// handleGetTrades handles retrieving account trade history
func (s *Server) handleGetTrades(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	limitStr := c.DefaultQuery("limit", "50")
	
	limit, err := strconv.Atoi(limitStr)
	if err != nil {
		limit = 50
	}

	trades, err := s.tradingClient.GetMyTrades(symbol, limit)
	if err != nil {
		log.Printf("❌ Failed to fetch trades: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
		})
		return
	}

	log.Printf("📈 Retrieved %d trades for %s", len(trades), symbol)
	c.JSON(http.StatusOK, gin.H{
		"trades": trades,
		"count":  len(trades),
		"symbol": symbol,
	})
}

// handleGetDepth handles retrieving order book depth
func (s *Server) handleGetDepth(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	limitStr := c.DefaultQuery("limit", "100")
	
	limit, err := strconv.Atoi(limitStr)
	if err != nil {
		limit = 100
	}

	depth, err := s.tradingClient.GetOrderBookDepth(symbol, limit)
	if err != nil {
		log.Printf("❌ Failed to fetch order book depth: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
		})
		return
	}

	log.Printf("📊 Retrieved order book depth for %s (bids: %d, asks: %d)", 
		symbol, len(depth.Bids), len(depth.Asks))
	c.JSON(http.StatusOK, gin.H{
		"lastUpdateId": depth.LastUpdateID,
		"bids":         depth.Bids,
		"asks":         depth.Asks,
		"symbol":       symbol,
	})
}

func (s *Server) handlePlaceOrder(c *gin.Context) {
	var req OrderRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var result *client.OrderResult
	var err error

	// Handle different order types
	switch req.Type {
	case "MARKET":
		result, err = s.tradingClient.PlaceMarketOrder(req.Symbol, req.Side, req.Quantity)
	case "LIMIT":
		if req.Price == "" {
			c.JSON(http.StatusBadRequest, gin.H{
				"error":   "Price is required for limit orders",
				"message": "Missing price parameter",
			})
			return
		}
		if req.Side == "BUY" {
			result, err = s.tradingClient.PlaceLimitBuyOrder(req.Symbol, req.Quantity, req.Price)
		} else if req.Side == "SELL" {
			result, err = s.tradingClient.PlaceLimitSellOrder(req.Symbol, req.Quantity, req.Price)
		} else {
			c.JSON(http.StatusBadRequest, gin.H{
				"error":   "Invalid order side",
				"message": "Side must be BUY or SELL",
			})
			return
		}
	default:
		c.JSON(http.StatusBadRequest, gin.H{
			"error":   "Invalid order type",
			"message": "Type must be MARKET or LIMIT",
		})
		return
	}

	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   err.Error(),
			"message": "Failed to place order",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":  "Order placed successfully",
		"orderId":  result.OrderID,
		"symbol":   result.Symbol,
		"side":     result.Side,
		"type":     result.Type,
		"status":   result.Status,
		"quantity": result.Quantity,
		"price":    result.Price,
	})
}

func (s *Server) Start(port string) error {
	log.Printf("🚀 Starting HTTP server on :%s", port)
	return s.router.Run(":" + port)
}

// handleGetRecentTrades handles recent public trades requests
func (s *Server) handleGetRecentTrades(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	limitStr := c.DefaultQuery("limit", "50")

	limit, err := strconv.Atoi(limitStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid limit parameter"})
		return
	}

	trades, err := s.tradingClient.GetRecentTrades(symbol, limit)
	if err != nil {
		log.Printf("❌ Failed to get recent trades: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"symbol": symbol,
		"trades": trades,
	})
}

// Cleanup stops all active streamers
func (s *Server) Cleanup() {
	// Stop broadcast hub
	if s.broadcastHub != nil {
		s.broadcastHub.Stop()
	}

	s.streamersMux.Lock()
	defer s.streamersMux.Unlock()

	for symbol, streamer := range s.streamers {
		streamer.Stop()
		log.Printf("🛑 Stopped price streamer for %s", symbol)
	}
	s.streamers = make(map[string]*websocket.PriceStreamer)

	for streamKey, streamer := range s.klineStreamers {
		streamer.Stop()
		log.Printf("🛑 Stopped kline streamer for %s", streamKey)
	}
	s.klineStreamers = make(map[string]*websocket.KlineStreamer)
}

// handleGetAllPrices returns all symbol prices
func (s *Server) handleGetAllPrices(c *gin.Context) {
	prices, err := s.tradingClient.GetSymbolPrices()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   err.Error(),
			"message": "Failed to get symbol prices",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"prices": prices,
		"count":  len(prices),
	})
}

// handleGet24hrTicker returns 24hr ticker statistics for multiple symbols
func (s *Server) handleGet24hrTicker(c *gin.Context) {
	symbols := c.QueryArray("symbols")
	if len(symbols) == 0 {
		// Default to popular trading pairs
		symbols = []string{
			"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
			"XRPUSDT", "DOTUSDT", "DOGEUSDT", "MATICUSDT", "PAXGUSDT",
			"BTCETH", "ETHBNB", "BTCBUSD", "ETHBUSD", "USDCUSDT",
		}
	}

	type TickerData struct {
		Symbol    string  `json:"symbol"`
		Price     string  `json:"price"`
		Change24h  float64 `json:"change24h"`
		High24h   string  `json:"high24h"`
		Low24h    string  `json:"low24h"`
		Volume24h string  `json:"volume24h"`
	}

	var tickers []TickerData
	
	for _, symbol := range symbols {
		// Get current price
		prices, err := s.tradingClient.GetSymbolPrices()
		if err != nil {
			continue
		}
		
		var currentPrice string
		for _, price := range prices {
			if price.Symbol == symbol {
				currentPrice = price.Price
				break
			}
		}
		
		if currentPrice == "" {
			continue
		}
		
		// Get 24hr statistics (simplified - in production you'd use Binance's 24hr ticker API)
		tickers = append(tickers, TickerData{
			Symbol:    symbol,
			Price:     currentPrice,
			Change24h:  0.0, // Would calculate from real data
			High24h:   currentPrice,
			Low24h:    currentPrice,
			Volume24h: "0",
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"tickers": tickers,
		"count":   len(tickers),
	})
}
