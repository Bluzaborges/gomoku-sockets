# Gomoku Sockets

A two-player Gomoku game built with Python, Pygame Community Edition, and TCP sockets. A central server maintains the shared 15 × 15 board, validates winning sequences, and synchronizes each move between two graphical clients.

The first client to connect becomes Player 1. The player with the white pieces takes the opening turn. Players alternate placing pieces until one completes an uninterrupted sequence of five pieces horizontally, vertically, or diagonally, or until the board is full.

## Requirements

- Python 3.10 or later
- Pygame Community Edition
- NumPy

## Installation

Clone the repository and install the dependencies from its root directory:

```bash
python -m pip install -r requirements.txt
```

## Running

The game requires three running processes: one server and two clients. Start them in this order.

### 1. Start the server

Open the first terminal in the repository root and run:

```bash
python src/server.py
```

The server listens on TCP port `5000` and waits for both players.

### 2. Start the first client

Open a second terminal and run:

```bash
python src/client.py 127.0.0.1 5000
```

The first client becomes Player 1 and displays a waiting screen until Player 2 connects.

### 3. Start the second client

Open a third terminal and run the same command:

```bash
python src/client.py 127.0.0.1 5000
```

The second client becomes Player 2, and the match begins automatically.

Each player can optionally provide a display name as the final argument:

```bash
python src/client.py 127.0.0.1 5000 Alice
python src/client.py 127.0.0.1 5000 Bob
```

If no name is provided, the clients use `Player 1` and `Player 2`.

For a game across different computers, replace `127.0.0.1` with the server computer's IP address. The server firewall must allow incoming TCP connections on port `5000`.

## License

This project is licensed under the [MIT License](LICENSE).
