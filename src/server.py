import socket
import threading
from queue import Queue

import numpy as np

from protocol import receive_message, send_message


PLAYER_COUNT = 2
BOARD_ROWS = 15
BOARD_COLUMNS = 15
HOST = ""
PORT = 5000
EMPTY_GAME_RESULT = (False, 0, 0, 0, "")
WINNING_DIRECTIONS = (
    (0, 1, "horizontal"),
    (1, 0, "vertical"),
    (1, 1, "diag_desc"),
    (1, -1, "diag_asc")
)


def is_board_full(board):
    return not np.any(board == 0)


def is_winning_sequence(board, row, column, row_step, column_step):
    player = board[row][column]

    for offset in range(1, 5):
        next_row = row + row_step * offset
        next_column = column + column_step * offset

        if not (0 <= next_row < BOARD_ROWS):
            return False
        if not (0 <= next_column < BOARD_COLUMNS):
            return False
        if board[next_row][next_column] != player:
            return False

    return True


def check_winner(board):
    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            if board[row][column] == 0:
                continue

            for row_step, column_step, orientation in WINNING_DIRECTIONS:
                if is_winning_sequence(board, row, column, row_step, column_step):
                    return (True, row, column, int(board[row][column]), orientation)

    return EMPTY_GAME_RESULT


def receive_client_messages(player, connection, messages):
    try:
        while True:
            message = receive_message(connection)
            if message is None:
                break

            messages.put((player, message))
    except (ConnectionError, OSError, ValueError):
        pass
    finally:
        messages.put((player, {"type": "disconnect"}))


def broadcast(clients, message):
    for connection in clients.values():
        send_message(connection, message)


def game_state(board, current_player, game_over, board_full):
    return {
        "type": "state",
        "board": board.tolist(),
        "current_player": current_player,
        "game_over": game_over,
        "board_full": board_full
    }


def get_player_colors(white_player):
    return [
        "white" if white_player == 1 else "black",
        "white" if white_player == 2 else "black"
    ]


def create_restart_state(white_player):
    next_white_player = white_player % 2 + 1
    board = np.zeros((BOARD_ROWS, BOARD_COLUMNS))
    return board, next_white_player, next_white_player


def restart_game(clients, white_player):
    board, white_player, current_player = create_restart_state(white_player)
    broadcast(clients, {
        "type": "restarted",
        "board": board.tolist(),
        "current_player": current_player,
        "colors": get_player_colors(white_player)
    })
    return board, white_player, current_player


def accept_players(server_socket):
    clients = {}
    player_names = {}

    for player in range(1, PLAYER_COUNT + 1):
        connection, address = server_socket.accept()
        join_message = receive_message(connection)

        if join_message is None or join_message.get("type") != "join":
            connection.close()
            return None, None

        requested_name = str(join_message.get("name", "")).strip()
        player_name = requested_name or f"Player {player}"
        clients[player] = connection
        player_names[player] = player_name

        send_message(connection, {
            "type": "assigned",
            "player": player,
            "name": player_name,
            "color": "white" if player == 1 else "black"
        })

        print(f"{player_name} connected from {address[0]}:{address[1]} "
              f"as Player {player}.")

    return clients, player_names


def start_message_receivers(clients):
    messages = Queue()

    for player, connection in clients.items():
        threading.Thread(
            target=receive_client_messages,
            args=(player, connection, messages),
            daemon=True).start()

    return messages


def notify_opponent_that_player_left(player, clients, player_names):
    opponent = player % 2 + 1
    if opponent not in clients:
        return

    try:
        send_message(clients[opponent], {
            "type": "opponent_left",
            "name": player_names[player]
        })
    except OSError:
        pass


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(PLAYER_COUNT)

    clients = {}
    print(f"Server listening on port {PORT}. Waiting for two players...")

    try:
        accepted_clients, player_names = accept_players(server_socket)
        if accepted_clients is None:
            return

        clients = accepted_clients

        board = np.zeros((BOARD_ROWS, BOARD_COLUMNS))
        white_player = 1
        current_player = white_player
        game_over = EMPTY_GAME_RESULT
        board_full = False
        match_ended = False
        restart_requester = None

        broadcast(clients, {
            "type": "start",
            "names": [player_names[1], player_names[2]],
            "colors": get_player_colors(white_player),
            "board": board.tolist(),
            "current_player": current_player
        })

        messages = start_message_receivers(clients)

        while True:
            player, message = messages.get()
            message_type = message.get("type")

            if message_type in ("quit", "disconnect"):
                notify_opponent_that_player_left(player, clients, player_names)
                break

            if message_type == "move" and not match_ended and player == current_player:
                row = int(message["row"])
                column = int(message["column"])

                if not (0 <= row < BOARD_ROWS and 0 <= column < BOARD_COLUMNS):
                    continue

                if board[row][column] != 0:
                    continue

                board[row][column] = player
                game_over = check_winner(board)
                board_full = is_board_full(board)
                match_ended = game_over[0] or board_full
                current_player = current_player % 2 + 1

                broadcast(clients, game_state(board, current_player, game_over, board_full))

                continue

            if message_type == "restart_request" and match_ended:
                if restart_requester is None:
                    restart_requester = player
                    opponent = player % 2 + 1

                    send_message(clients[player], {"type": "restart_pending"})
                    send_message(clients[opponent], {
                        "type": "restart_requested",
                        "name": player_names[player]
                    })
                elif restart_requester != player:
                    board, white_player, current_player = restart_game(clients, white_player)
                    game_over = EMPTY_GAME_RESULT
                    board_full = False
                    match_ended = False
                    restart_requester = None
                continue

            if message_type == "restart_response" and match_ended:
                if restart_requester is None or restart_requester == player:
                    continue

                if message.get("accepted"):
                    board, white_player, current_player = restart_game(clients, white_player)
                    game_over = EMPTY_GAME_RESULT
                    board_full = False
                    match_ended = False
                else:
                    broadcast(clients, {"type": "restart_declined"})

                restart_requester = None
    finally:
        for connection in clients.values():
            connection.close()

        server_socket.close()


if __name__ == "__main__":
    main()
