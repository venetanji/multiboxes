# Multiboxes - Educational Multiplayer Game

A simple multiplayer physics game demonstrating key programming concepts for students:

- **Asyncio**: Concurrent programming with Python
- **OSC**: Open Sound Control for network communication  
- **PyMunk**: 2D physics simulation
- **Pygame**: Game graphics and input handling
- **Zeroconf**: Automatic network service discovery
- **Python Packaging**: How to create installable Python packages

## What This Project Teaches

### 1. Asyncio (Asynchronous Programming)
- Running multiple tasks concurrently (game loop, network, graphics)
- Using `async`/`await` keywords
- Managing event loops and coroutines
- Non-blocking I/O operations

### 2. Network Programming
- UDP communication between client and server
- OSC (Open Sound Control) message format
- Real-time multiplayer synchronization
- Automatic service discovery with Zeroconf

### 3. Game Development
- Game loop architecture (update → draw → repeat)
- Physics simulation with PyMunk
- Player input handling
- Real-time graphics with Pygame

### 4. Python Packaging
- Creating installable packages with `pyproject.toml`
- Module structure and imports
- Development vs. production dependencies

## Project Structure

```
multiboxes/
├── src/multibox/           # Main package code
│   ├── game_server.py      # Server that runs physics and coordinates players
│   ├── game_client.py      # Client that handles graphics and input
│   ├── player.py           # Player class definition
│   └── avahi_utils.py      # Network service discovery utilities
├── tests/                  # Test files
├── requirements.txt        # Project dependencies
├── pyproject.toml         # Package configuration
└── README.md              # This file
```

## How to Run

### 1. Set up the environment
```bash
# Create virtual environment with uv
uv venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
uv pip install -r requirements.txt

# Install the package in development mode
uv pip install -e .
```

### 2. Start the server
```bash
python -m multibox.game_server
```

The server will:
- Create a physics world with walls
- Listen for player connections
- Run the game loop at 60 FPS
- Broadcast player positions to all clients

### 3. Start clients (in separate terminals)
```bash
python -m multibox.game_client
```

Each client will:
- Automatically discover the server using Zeroconf
- Connect and create a player
- Display the game world
- Send keyboard input to the server

### 4. Play the game!
- **Arrow keys**: Move your player around
- **Q/E**: Rotate (basic implementation)
- **ESC** or close window: Quit

## Key Concepts Explained

### Server Architecture
The server demonstrates several important patterns:

1. **Global State Management**: Player positions and physics bodies
2. **Event-Driven Programming**: OSC message handlers
3. **Physics Simulation**: PyMunk space, bodies, and forces
4. **Network Broadcasting**: Sending updates to all connected clients

### Client Architecture
The client shows how to integrate different systems:

1. **Async Task Coordination**: Multiple concurrent coroutines
2. **Event Loop Integration**: Bridging Pygame and asyncio
3. **Network Client Pattern**: Receiving server updates
4. **Real-time Rendering**: 60 FPS graphics loop

### Network Communication
The project uses OSC messages for simplicity:

- `/connect` - Client joins the game
- `/update_velocity` - Client sends movement input
- `/update_position` - Server broadcasts player positions

### Service Discovery
Instead of hardcoding IP addresses, the project uses Zeroconf:

1. Server registers itself as a network service
2. Clients automatically discover available servers
3. No manual network configuration needed

## Learning Exercises

Try these modifications to learn more:

### Beginner
1. Change player colors or sizes
2. Modify movement speed or physics properties
3. Add sound effects using pygame.mixer
4. Display player names or scores

### Intermediate  
1. Add collision detection between players
2. Implement power-ups or collectible items
3. Add different game modes (team vs team)
4. Save and load game state

### Advanced
1. Add interpolation for smoother movement
2. Implement client-side prediction
3. Add lag compensation techniques
4. Create a matchmaking system

## Common Issues

### "No server found"
- Make sure the server is running first
- Check that both client and server are on the same network
- Firewall might be blocking UDP traffic

### Import errors
- Make sure you activated the virtual environment
- Run `uv pip install -e .` to install in development mode
- Check that all dependencies are installed

### Game runs slowly
- Physics calculations can be CPU intensive
- Try reducing the number of connected clients
- Lower the FPS in the game loop if needed

## Dependencies Explained

- **pygame**: Graphics, input, and game loop
- **pymunk**: 2D physics simulation engine
- **python-osc**: OSC message protocol implementation
- **zeroconf**: Network service discovery (like Bonjour/Avahi)
- **pytest**: Testing framework
- **asyncio**: Built into Python, provides async/await
