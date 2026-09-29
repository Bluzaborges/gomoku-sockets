import socket
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

import numpy as np
import pygame

from protocol import receive_message, send_message


WIDTH = 600
HEIGHT = 700
BOARD_ROWS = 15
BOARD_COLUMNS = 15
CELL_SIZE = 40
BOARD_LINE_WIDTH = 1
WINNING_LINE_WIDTH = 3
BACKGROUND_COLOR = (248, 248, 255)
LINE_COLOR = (128, 128, 128)
TEXT_COLOR = (0, 0, 0)
WAITING_BACKGROUND_COLOR = (0, 0, 0)
WAITING_TEXT_COLOR = (255, 255, 255)


class GameState:
    def __init__(self, player, player_name, player_color):
        self.player = player
        self.player_name = player_name
        self.player_color = player_color
        self.player_names = {1: "Player 1", 2: "Player 2"}
        self.player_colors = {1: "white", 2: "black"}
        self.board = np.zeros((BOARD_ROWS, BOARD_COLUMNS))
        self.current_player = 1
        self.started = False
        self.game_over = (False, 0, 0, 0, "")
        self.board_full = False
        self.restart_status = None
        self.restart_requester_name = ""
        self.closing_message = None
        self.close_at = None

    def has_ended(self):
        return self.game_over[0] or self.board_full


def receive_server_messages(connection, messages):
    try:
        while True:
            message = receive_message(connection)
            if message is None:
                break

            messages.put(message)
    except (ConnectionError, OSError, ValueError):
        pass
    finally:
        messages.put({"type": "disconnected"})


def is_position_available(board, row, column):
    return board[row][column] == 0


def draw_vertical_winning_line(screen, row, column):
    pos_y = row * CELL_SIZE
    pos_x = column * CELL_SIZE + CELL_SIZE / 2
    pygame.draw.line(
        screen,
        TEXT_COLOR,
        (pos_x, pos_y),
        (pos_x, pos_y + CELL_SIZE * 5),
        WINNING_LINE_WIDTH)


def draw_horizontal_winning_line(screen, row, column):
    pos_y = row * CELL_SIZE + CELL_SIZE / 2
    pos_x = column * CELL_SIZE
    pygame.draw.line(
        screen,
        TEXT_COLOR,
        (pos_x, pos_y),
        (pos_x + CELL_SIZE * 5, pos_y),
        WINNING_LINE_WIDTH)


def draw_ascending_diagonal_winning_line(screen, row, column):
    pos_y = row * CELL_SIZE
    pos_x = column * CELL_SIZE + CELL_SIZE
    pygame.draw.line(
        screen,
        TEXT_COLOR,
        (pos_x, pos_y),
        (pos_x - CELL_SIZE * 5, pos_y + CELL_SIZE * 5),
        WINNING_LINE_WIDTH)


def draw_descending_diagonal_winning_line(screen, row, column):
    pos_y = row * CELL_SIZE
    pos_x = column * CELL_SIZE
    pygame.draw.line(
        screen,
        TEXT_COLOR,
        (pos_x, pos_y),
        (pos_x + CELL_SIZE * 5, pos_y + CELL_SIZE * 5),
        WINNING_LINE_WIDTH)


def draw_centered_text(screen, font, text, center, color):
    rendered_text = font.render(text, True, color)
    screen.blit(rendered_text, rendered_text.get_rect(center=center))


def draw_waiting_screen(screen, font, message):
    screen.fill(WAITING_BACKGROUND_COLOR)
    draw_centered_text(
        screen,
        font,
        message,
        (WIDTH / 2, HEIGHT / 2),
        WAITING_TEXT_COLOR)


def draw_board(screen, board, piece_images, player_colors):
    screen.fill(BACKGROUND_COLOR)

    for position in range(CELL_SIZE, WIDTH + 1, CELL_SIZE):
        offset = position - CELL_SIZE / 2
        pygame.draw.line(
            screen,
            LINE_COLOR,
            (CELL_SIZE / 2, offset),
            (WIDTH - CELL_SIZE / 2, offset),
            BOARD_LINE_WIDTH)
        pygame.draw.line(
            screen,
            LINE_COLOR,
            (offset, CELL_SIZE / 2),
            (offset, HEIGHT - 100 - CELL_SIZE / 2),
            BOARD_LINE_WIDTH)

    for row in range(BOARD_ROWS):
        for column in range(BOARD_COLUMNS):
            piece = int(board[row][column])
            if piece in player_colors:
                piece_color = player_colors[piece]
                position = (column * CELL_SIZE + 4, row * CELL_SIZE + 4)
                screen.blit(piece_images[piece_color], position)


def draw_winning_line(screen, game_over):
    won, row, column, winner, orientation = game_over
    if not won:
        return

    if orientation == "horizontal":
        draw_horizontal_winning_line(screen, row, column)
    elif orientation == "vertical":
        draw_vertical_winning_line(screen, row, column)
    elif orientation == "diag_desc":
        draw_descending_diagonal_winning_line(screen, row, column)
    elif orientation == "diag_asc":
        draw_ascending_diagonal_winning_line(screen, row, column)


def send_quit(connection):
    try:
        send_message(connection, {"type": "quit"})
    except OSError:
        pass


def set_player_appearance(state, piece_images):
    title = f"Gomoku — {state.player_name} ({state.player_color.title()})"
    pygame.display.set_caption(title)
    pygame.display.set_icon(piece_images[state.player_color])


def handle_end_game_key(event, connection, state):
    if event.key == pygame.K_ESCAPE:
        send_quit(connection)
        return False

    if event.key == pygame.K_r and state.restart_status in (None, "declined"):
        send_message(connection, {"type": "restart_request"})
        state.restart_status = "pending"

    elif event.key == pygame.K_y and state.restart_status == "requested":
        send_message(connection, {
            "type": "restart_response",
            "accepted": True
        })
        state.restart_status = "pending"

    elif event.key == pygame.K_n and state.restart_status == "requested":
        send_message(connection, {
            "type": "restart_response",
            "accepted": False
        })
        state.restart_status = "declined"

    return True


def try_to_play(event, connection, board):
    row = event.pos[1] // CELL_SIZE
    column = event.pos[0] // CELL_SIZE

    if row >= BOARD_ROWS or column >= BOARD_COLUMNS:
        return
    if not is_position_available(board, row, column):
        return

    send_message(connection, {
        "type": "move",
        "row": row,
        "column": column
    })


def get_result_message(state):
    if state.board_full and not state.game_over[0]:
        return "Draw"

    winner = int(state.game_over[3])
    return f"{state.player_names[winner]} won!"


def get_restart_message(state):
    if state.restart_status == "requested":
        return (f"{state.restart_requester_name} requests a rematch — "
                "Y accept / N decline")
    if state.restart_status == "pending":
        return "Waiting for the other player to accept the rematch..."
    if state.restart_status == "declined":
        return "Rematch declined — R request again / Esc quit"

    return "R request rematch / Esc quit"


def draw_match_status(screen, font, small_font, state):
    if state.has_ended():
        draw_winning_line(screen, state.game_over)
        draw_centered_text(
            screen,
            font,
            get_result_message(state),
            (WIDTH / 2, 620),
            TEXT_COLOR)
        draw_centered_text(
            screen,
            small_font,
            get_restart_message(state),
            (WIDTH / 2, 665),
            TEXT_COLOR)
        return

    turn_message = (
        "Your turn"
        if state.current_player == state.player
        else f"{state.player_names[state.current_player]}'s turn")
    draw_centered_text(screen, font, turn_message, (450, 620), TEXT_COLOR)


def process_server_message(message, state, piece_images):
    message_type = message.get("type")

    if message_type == "start":
        state.player_names = {
            1: message["names"][0],
            2: message["names"][1]
        }
        state.player_colors = {
            1: message["colors"][0],
            2: message["colors"][1]
        }
        state.player_color = state.player_colors[state.player]
        state.board = np.array(message["board"])
        state.current_player = int(message["current_player"])
        state.started = True
        set_player_appearance(state, piece_images)

    elif message_type == "state":
        state.board = np.array(message["board"])
        state.current_player = int(message["current_player"])
        state.game_over = tuple(message["game_over"])
        state.board_full = bool(message["board_full"])

    elif message_type == "restart_pending":
        state.restart_status = "pending"

    elif message_type == "restart_requested":
        state.restart_status = "requested"
        state.restart_requester_name = message["name"]

    elif message_type == "restart_declined":
        state.restart_status = "declined"

    elif message_type == "restarted":
        state.board = np.array(message["board"])
        state.current_player = int(message["current_player"])
        state.player_colors = {
            1: message["colors"][0],
            2: message["colors"][1]
        }
        state.player_color = state.player_colors[state.player]
        state.game_over = (False, 0, 0, 0, "")
        state.board_full = False
        state.restart_status = None
        state.restart_requester_name = ""
        set_player_appearance(state, piece_images)

    elif message_type == "opponent_left":
        state.closing_message = f"{message['name']} left the game."
        state.close_at = pygame.time.get_ticks() + 2000

    elif message_type == "disconnected" and state.closing_message is None:
        state.closing_message = "Connection to the server was closed."
        state.close_at = pygame.time.get_ticks() + 2000


def main():
    if len(sys.argv) not in (3, 4):
        print(f"Usage: {sys.argv[0]} <ip> <port> [player-name]")
        return 1

    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    requested_name = sys.argv[3].strip() if len(sys.argv) == 4 else ""

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((server_ip, server_port))
    send_message(client_socket, {"type": "join", "name": requested_name})

    assignment = receive_message(client_socket)
    if assignment is None or assignment.get("type") != "assigned":
        client_socket.close()
        print("The server did not assign a player number.")
        return 1

    state = GameState(
        int(assignment["player"]),
        assignment["name"],
        assignment["color"])

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    font = pygame.font.SysFont("Consolas", 20, True)
    small_font = pygame.font.SysFont("Consolas", 16, True)
    clock = pygame.time.Clock()

    assets_directory = Path(__file__).resolve().parent.parent / "assets"
    piece_images = {
        "white": pygame.image.load(assets_directory / "white.png"),
        "black": pygame.image.load(assets_directory / "black.png")
    }
    set_player_appearance(state, piece_images)

    messages = Queue()
    threading.Thread(
        target=receive_server_messages,
        args=(client_socket, messages),
        daemon=True).start()

    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                send_quit(client_socket)
                running = False

            elif event.type == pygame.KEYDOWN and state.has_ended():
                running = handle_end_game_key(event, client_socket, state)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if not state.started or state.has_ended():
                    continue
                if state.current_player != state.player:
                    continue

                try_to_play(event, client_socket, state.board)

        while True:
            try:
                message = messages.get_nowait()
            except Empty:
                break

            process_server_message(message, state, piece_images)

        if state.closing_message is not None:
            draw_waiting_screen(screen, font, state.closing_message)
            if pygame.time.get_ticks() >= state.close_at:
                running = False
        elif not state.started:
            draw_waiting_screen(screen, font, "Waiting for Player 2 to connect...")
        else:
            draw_board(
                screen,
                state.board,
                piece_images,
                state.player_colors)

            draw_centered_text(
                screen,
                small_font,
                f"{state.player_name} — {state.player_color.title()}",
                (120, 620),
                TEXT_COLOR)

            draw_match_status(screen, font, small_font, state)

        pygame.display.flip()
        clock.tick(60)

    client_socket.close()
    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
