package server

import (
	"log"
	"net/http"
	"sync"

	"github.com/aphis/24hrt-backend/client"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

type Server struct {
	router        *gin.Engine
	upgrader      websocket.Upgrader
	priceClients  map[*websocket.Conn]bool
	clientsMux    sync.Mutex
	priceChan     chan PriceMessage
	tradingClient *client.TradingClient
}

type PriceMessage struct {
	Symbol    string  `json:"symbol"`
	Price     string  `json:"price"`
	Timestamp int64   `json:"timestamp"`
}

type OrderRequest struct {
	Symbol   string `json:"symbol" binding:"required"`
	Side     string `json:"side" binding:"required"`   // BUY or SELL
	Quantity string `json:"quantity" binding:"required"`
	Type     string `json:"type"`                      // MARKET or LIMIT
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
		priceClients:  make(map[*websocket.Conn]bool),
		priceChan:     make(chan PriceMessage, 100),
		tradingClient: tradingClient,
		upgrader: websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool {
				return true // Allow all origins for local development
			},
		},
	}

	// Setup CORS
	config := cors.DefaultConfig()
	config.AllowAllOrigins = true
	config.AllowMethods = []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"}
	config.AllowHeaders = []string{"Origin", "Content-Type", "Authorization"}
	s.router.Use(cors.New(config))

	// Setup routes
	s.setupRoutes()

	// Start broadcasting prices to all connected clients
	go s.broadcastPrices()

	return s
}

func (s *Server) setupRoutes() {
	api := s.router.Group("/api")
	{
		// Health check
		api.GET("/health", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{"status": "ok"})
		})

		// WebSocket for real-time price updates
		api.GET("/price", s.handlePriceWebSocket)

		// Get account balance (will be implemented later)
		api.GET("/balance", s.handleGetBalance)

		// Place order (will be implemented later)
		api.POST("/order", s.handlePlaceOrder)

		// Get historical klines/candlesticks
		api.GET("/klines", s.handleGetKlines)
	}
}

// HandlePriceWebSocket upgrades HTTP to WebSocket for price streaming
func (s *Server) handlePriceWebSocket(c *gin.Context) {
	// Get symbol from query parameter, default to BTCUSDT
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	
	conn, err := s.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("Failed to upgrade connection: %v", err)
		return
	}

	// Register new client
	s.clientsMux.Lock()
	s.priceClients[conn] = true
	s.clientsMux.Unlock()

	log.Printf("🔌 New WebSocket client connected (Total: %d)", len(s.priceClients))

	// Wait for client to disconnect
	defer func() {
		s.clientsMux.Lock()
		delete(s.priceClients, conn)
		s.clientsMux.Unlock()
		conn.Close()
		log.Printf("🔌 Client disconnected (Remaining: %d)", len(s.priceClients))
	}()

	// Keep connection alive
	for {
		_, _, err := conn.ReadMessage()
		if err != nil {
			break
		}
	}
}

// BroadcastPrices sends price updates to all connected WebSocket clients
func (s *Server) broadcastPrices() {
	for priceMsg := range s.priceChan {
		s.clientsMux.Lock()
		for client := range s.priceClients {
			err := client.WriteJSON(priceMsg)
			if err != nil {
				log.Printf("Error sending price to client: %v", err)
				client.Close()
				delete(s.priceClients, client)
			}
		}
		s.clientsMux.Unlock()
	}
}

// SendPrice queues a price update to be broadcast to all clients
func (s *Server) SendPrice(symbol, price string, timestamp int64) {
	select {
	case s.priceChan <- PriceMessage{
		Symbol:    symbol,
		Price:     price,
		Timestamp: timestamp,
	}:
	default:
		// Channel full, skip this update
	}
}

func (s *Server) handleGetBalance(c *gin.Context) {
	balances, err := s.tradingClient.GetAccountBalance()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Convert to response format
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

// HandlePlaceOrder handles order placement requests
func (s *Server) handlePlaceOrder(c *gin.Context) {
	var req OrderRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Place order via trading client
	result, err := s.tradingClient.PlaceMarketOrder(req.Symbol, req.Side, req.Quantity)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
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

// handleGetKlines returns historical candlestick data
func (s *Server) handleGetKlines(c *gin.Context) {
	symbol := c.DefaultQuery("symbol", "BTCUSDT")
	interval := c.DefaultQuery("interval", "1m")
	limit := c.DefaultQuery("limit", "100")

	klines, err := s.tradingClient.GetKlines(symbol, interval, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
			"message": "Failed to fetch klines",
		})
		return
	}

	c.JSON(http.StatusOK, klines)
}

// Start runs the HTTP server
func (s *Server) Start(port string) error {
	log.Printf("🚀 Starting HTTP server on :%s", port)
	return s.router.Run(":" + port)
}

// GetPriceChannel returns the channel for sending price updates
func (s *Server) GetPriceChannel() chan<- PriceMessage {
	return s.priceChan
}
