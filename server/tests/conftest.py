import pytest

from mushroom.client import Client
from mushroom.game import Game
from mushroom.world import Player, Room


class FakeClient(Client):
    def __init__(self, game):
        self.cmds = []
        self.game = game
        self.outputs = []
        self.player = None

    def send(self, output):
        self.outputs.append(output)


@pytest.fixture
def game():
    return Game.get_instance()


@pytest.fixture
def client(game):
    return FakeClient(game)


@pytest.fixture
def room(game):
    theroom = Room("hôpital")
    theroom.desctiption = "où on emmène ceux qui ont du bobo"
    game.db.add(theroom)
    return theroom


@pytest.fixture
def player(client, game, room):
    theplayer = Player("léon")
    theplayer.location = room
    theplayer.play(client, game)
    client.player = theplayer
    game.db.add(theplayer)
    return theplayer
