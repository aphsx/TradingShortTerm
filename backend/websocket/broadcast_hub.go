package websocket

import (
	"encoding/json"
	"log"
	"sync"

	ws "github.com/gorilla/websocket"
)

// BroadcastHub manages multiple WebSocket connections and broadcasts data efficiently
// This replaces the simple Hub pattern with a more robust solution
type BroadcastHub struct {
	clients      map[*ws.Conn]*ClientConnection
	register     chan *ClientConnection
	unregister   chan *ClientConnection
	broadcast    chan []byte
	mu           sync.RWMutex
	isRunning    bool
}

// ClientConnection represents a connected client with metadata
type ClientConnection struct {
	conn     *ws.Conn
	Symbol   string    // Exported fields for external access
	Interval string    // Exported fields for external access
	send     chan []byte
	mu       sync.Mutex
}

// NewBroadcastHub creates a new broadcast hub
func NewBroadcastHub() *BroadcastHub {
	return &BroadcastHub{
		clients:   make(map[*ws.Conn]*ClientConnection),
		register:  make(chan *ClientConnection),
		unregister: make(chan *ClientConnection),
		broadcast: make(chan []byte, 256), // Buffered channel
	}
}

// Run starts the broadcast hub
func (h *BroadcastHub) Run() {
	h.isRunning = true
	
	for h.isRunning {
		select {
		case client := <-h.register:
			h.registerClient(client)
			
		case client := <-h.unregister:
			h.unregisterClient(client)
			
		case message := <-h.broadcast:
			h.broadcastMessage(message)
		}
	}
}

// Stop stops the broadcast hub
func (h *BroadcastHub) Stop() {
	h.isRunning = false
	
	// Close all client connections
	h.mu.Lock()
	for _, client := range h.clients {
		client.Close()
	}
	h.clients = make(map[*ws.Conn]*ClientConnection)
	h.mu.Unlock()
	
	log.Println("🛑 Broadcast hub stopped")
}

// RegisterClient adds a new client to the hub
func (h *BroadcastHub) RegisterClient(conn *ws.Conn, symbol, interval string) *ClientConnection {
	client := &ClientConnection{
		conn:     conn,
		Symbol:   symbol,   // Use exported fields
		Interval: interval, // Use exported fields
		send:     make(chan []byte, 256),
	}
	
	h.register <- client
	return client
}

// UnregisterClient removes a client from the hub
func (h *BroadcastHub) UnregisterClient(client *ClientConnection) {
	h.unregister <- client
}

// GetClientCount returns the number of connected clients
func (h *BroadcastHub) GetClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

// GetClientsBySymbol returns clients subscribed to a specific symbol
func (h *BroadcastHub) GetClientsBySymbol(symbol string) []*ClientConnection {
	h.mu.RLock()
	defer h.mu.RUnlock()
	
	targetClients := make([]*ClientConnection, 0)
	for _, client := range h.clients {
		if client.Symbol == symbol { // Use exported field
			targetClients = append(targetClients, client)
		}
	}
	return targetClients
}

// BroadcastToAll sends message to all connected clients
func (h *BroadcastHub) BroadcastToAll(data interface{}) {
	jsonData, err := json.Marshal(data)
	if err != nil {
		log.Printf("❌ Failed to marshal broadcast data: %v", err)
		return
	}
	
	select {
	case h.broadcast <- jsonData:
	default:
		log.Printf("⚠️  Broadcast channel full, dropping message")
	}
}

// BroadcastToSymbol sends message to clients subscribed to a specific symbol
func (h *BroadcastHub) BroadcastToSymbol(symbol string, data interface{}) {
	jsonData, err := json.Marshal(data)
	if err != nil {
		log.Printf("❌ Failed to marshal symbol broadcast data: %v", err)
		return
	}
	
	targetClients := h.GetClientsBySymbol(symbol)
	for _, client := range targetClients {
		select {
		case client.send <- jsonData:
		default:
			log.Printf("⚠️  Client send channel full for %s", symbol)
		}
	}
}

// SendSnapshot sends buffered data to a specific client
func (h *BroadcastHub) SendSnapshot(client *ClientConnection, snapshot map[string]interface{}) {
	jsonData, err := json.Marshal(map[string]interface{}{
		"type":     "snapshot",
		"data":     snapshot,
		"symbol":   client.Symbol,   // Use exported field
		"interval": client.Interval, // Use exported field
	})
	if err != nil {
		log.Printf("❌ Failed to marshal snapshot: %v", err)
		return
	}
	
	select {
	case client.send <- jsonData:
		log.Printf("📸 Sent snapshot to client for %s", client.Symbol) // Use exported field
	default:
		log.Printf("⚠️  Failed to send snapshot - channel full")
	}
}

// --- Internal Methods ---

func (h *BroadcastHub) registerClient(client *ClientConnection) {
	h.mu.Lock()
	defer h.mu.Unlock()
	
	h.clients[client.conn] = client
	log.Printf("👋 Client connected: %s (%s) | Total: %d", 
		client.Symbol, client.Interval, len(h.clients)) // Use exported fields
	
	// Start client writer goroutine
	go h.writePump(client)
}

func (h *BroadcastHub) unregisterClient(client *ClientConnection) {
	h.mu.Lock()
	defer h.mu.Unlock()
	
	if _, ok := h.clients[client.conn]; ok {
		delete(h.clients, client.conn)
		client.Close()
		log.Printf("👋 Client disconnected: %s | Total: %d", 
			client.Symbol, len(h.clients)) // Use exported field
	}
}

func (h *BroadcastHub) broadcastMessage(message []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	
	for _, client := range h.clients {
		select {
		case client.send <- message:
		default:
			// Client send channel is full, close and remove
			log.Printf("⚠️  Client send channel full, disconnecting")
			go h.unregisterClient(client)
		}
	}
}

func (h *BroadcastHub) writePump(client *ClientConnection) {
	defer client.Close()
	
	for {
		select {
		case message, ok := <-client.send:
			if !ok {
				// Hub closed the channel
				return
			}
			
			client.mu.Lock()
			err := client.conn.WriteMessage(ws.TextMessage, message)
			client.mu.Unlock()
			
			if err != nil {
				log.Printf("❌ Write error: %v", err)
				h.unregisterClient(client)
				return
			}
		}
	}
}

// Close closes the client connection
func (c *ClientConnection) Close() {
	c.mu.Lock()
	defer c.mu.Unlock()
	
	if c.conn != nil {
		c.conn.Close()
	}
	
	close(c.send)
}
