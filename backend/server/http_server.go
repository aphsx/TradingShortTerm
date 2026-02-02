package server

import (
	"log"
	"net/http"
	"sync"

	"github.com/aphis/24hrt-backend/client"
	"github.com/aphis/24hrt-backend/websocket"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	ws "github.com/gorilla/websocket"
)

type ClientInfo struct {
	conn   *ws.Conn
	symbol string
}

type Server struct {
	router        *gin.Engine
	upgrader      ws.Upgrader
	priceClients  map[*ws.Conn]*ClientInfo
	clientsMux    sync.Mutex
	streamers     map[string]*websocket.PriceStreamer
	streamersMux  sync.Mutex
	tradingClient *client.TradingClient
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
		router:        gin.Default(),
		priceClients:  make(map[*ws.Conn]*ClientInfo),
		streamers:     make(map[string]*websocket.PriceStreamer),
		tradingClient: tradingClient,
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
	return s
}

func (s *Server) setupRoutes() {
	api := s.router.Group("/api")
	{
		api.GET("/health", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{"status": "ok"})
		})
		api.GET("/price", s.handlePriceWebSocket)
		api.GET("/balance", s.handleGetBalance)
		api.POST("/order", s.handlePlaceOrder)
		api.GET("/klines", s.handleGetKlines)
	}
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
			s.broadcastPrice(update.Symbol, update.Price, update.Timestamp)
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

// broadcastPrice sends price update to all clients subscribed to that symbol
func (s *Server) broadcastPrice(symbol, price string, timestamp int64) {
	priceMsg := PriceMessage{
		Symbol:    symbol,
		Price:     price,
		Timestamp: timestamp,
	}

	s.clientsMux.Lock()
	defer s.clientsMux.Unlock()

	for conn, clientInfo := range s.priceClients {
		// Only send to clients subscribed to this symbol
		if clientInfo.symbol == symbol {
			err := conn.WriteJSON(priceMsg)
			if err != nil {
				log.Printf("Error sending price to client: %v", err)
				conn.Close()
				delete(s.priceClients, conn)
			}
		}
	}
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

func (s *Server) handlePlaceOrder(c *gin.Context) {
	var req OrderRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	result, err := s.tradingClient.PlaceMarketOrder(req.Symbol, req.Side, req.Quantity)
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
		"status":   result.Status,
		"quantity": result.Quantity,
		"price":    result.Price,
	})
}

func (s *Server) handleGetKlines(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	interval := c.DefaultQuery("interval", "1m")
	limit := c.DefaultQuery("limit", "100")

	klines, err := s.tradingClient.GetKlines(symbol, interval, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error":   err.Error(),
			"message": "Failed to fetch klines",
		})
		return
	}

	c.JSON(http.StatusOK, klines)
}

func (s *Server) Start(port string) error {
	log.Printf("🚀 Starting HTTP server on :%s", port)
	return s.router.Run(":" + port)
}

// Cleanup stops all active streamers
func (s *Server) Cleanup() {
	s.streamersMux.Lock()
	defer s.streamersMux.Unlock()

	for symbol, streamer := range s.streamers {
		streamer.Stop()
		log.Printf("🛑 Stopped streamer for %s", symbol)
	}
	s.streamers = make(map[string]*websocket.PriceStreamer)
}
