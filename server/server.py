import asyncio
import logging

import websockets

from utils import (
    GameEndType,
    GamePlayType,
    generic_event
)

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("websockets.server").setLevel(logging.INFO)
logging.getLogger("asyncio").setLevel(logging.INFO)


def new_client_event():
    return generic_event("clients_update",
                         {
                             "connected_clients": len(Client.connected_sockets),
                             "waiting": len(Client.single_clients)
                         })


def new_game_event(play: GamePlayType):
    return generic_event("game_play",
                         {
                             "play_type": play.value
                         })


def game_end_event(end: GameEndType):
    return generic_event("game_end",
                         {
                             "end_type": end.value
                         })


def new_partner_event():
    return generic_event("new_partner",
                         "New partner!")


lock = asyncio.Lock()
count = 0  # debug


class Client:
    connected_sockets = set()
    single_clients = set()

    def __init__(self, connection: websockets.WebSocketCommonProtocol):
        self.connection = connection
        self.connected_sockets.add(connection)
        self.current_play: GamePlayType = None
        self.partner: Client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.remove_partner()
        self.connected_sockets.remove(self.connection)
        self.not_single()
        websockets.broadcast(Client.connected_sockets, new_client_event())

    async def send_websocket(self, message):
        await self.connection.send(message)

    async def seeking_partner(self):
        async with lock:
            if self.single_clients:
                # noinspection PyAsyncCall
                await self.add_partner(self.single_clients.pop())
            else:
                self.single_clients.add(self)

    def not_single(self):
        try:
            self.single_clients.remove(self.connection)
        except KeyError:
            pass

    async def add_partner(self, partner, cascade=True):
        if partner is self:
            return

        await self.remove_partner()
        self.partner = partner

        await self.send_websocket(new_partner_event())
        await self.send_websocket(new_client_event())

        if cascade:
            await partner.add_partner(self, False)

        self.not_single()

    async def remove_partner(self, cascade=True):
        old_partner = self.partner

        if old_partner is None:
            return

        self.partner = None

        if cascade:
            await old_partner.remove_partner(False)

        await self.seeking_partner()


async def handler(websocket: websockets.WebSocketCommonProtocol, path):
    global count

    async with Client(websocket) as new_cli:
        await new_cli.seeking_partner()
        websockets.broadcast(Client.connected_sockets, new_client_event())
        logging.debug(f"Clients seeking connections: {Client.single_clients}")
        try:
            async for message in websocket:
                if message.lstrip("-").isdigit():
                    code = int(message)

                    match code:
                        case GamePlayType.ROCK.value:
                            new_cli.current_play = GamePlayType.ROCK
                        case GamePlayType.PAPER.value:
                            new_cli.current_play = GamePlayType.PAPER
                        case GamePlayType.SCISSORS.value:
                            new_cli.current_play = GamePlayType.SCISSORS
                        case _:
                            new_cli.current_play = None

                    if new_cli.partner is not None:
                        if new_cli.partner.current_play is not None and new_cli.current_play is not None:
                            cli_play = new_cli.current_play
                            partner_play = new_cli.partner.current_play

                            if cli_play is partner_play:
                                await new_cli.send_websocket(game_end_event(GameEndType.DRAW))
                                await new_cli.partner.send_websocket(game_end_event(GameEndType.DRAW))
                            elif (cli_play is GamePlayType.ROCK and partner_play is GamePlayType.SCISSORS) or \
                                (cli_play is GamePlayType.PAPER and partner_play is GamePlayType.ROCK) or \
                                (cli_play is GamePlayType.SCISSORS and partner_play is GamePlayType.PAPER):
                                await new_cli.send_websocket(game_end_event(GameEndType.WIN))
                                await new_cli.partner.send_websocket(game_end_event(GameEndType.LOSE))
                            else:
                                await new_cli.send_websocket(game_end_event(GameEndType.LOSE))
                                await new_cli.partner.send_websocket(game_end_event(GameEndType.WIN))

                            await new_cli.remove_partner()
                else:
                    # Debug
                    if message == "a":
                        count -= 1
                        await new_cli.send_websocket(str(count))
                    elif message == "s":
                        count += 1
                        await new_cli.send_websocket(str(count))
                    else:
                        logging.debug(f"Err: {message}")
        except Exception as e:
            logging.error(f"Exception: {e}")

    logging.info("Closing!")


async def main():
    async with websockets.serve(handler, "localhost", 6789):
        logging.info("Started!")
        try:
            await asyncio.Future()  # run forever
        except asyncio.exceptions.CancelledError as e:
            logging.warning(f"Cancelled: {e}")


if __name__ == "__main__":
    # python -m websockets ws://localhost:6789
    asyncio.run(main())
