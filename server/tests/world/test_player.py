from mushroom.game import Game
from mushroom.world import Player, Room


class FakeClient:
    def __init__(self):
        self.outputs = []

    def send(self, output):
        self.outputs.append(output)


def test_player_can_look():
    client = FakeClient()
    player = Player("léon")
    player.play(client, Game.get_instance())
    room = Room("hôpital")
    room.description = "test-description"
    player.location = room

    look_cmd = next(cmd for cmd in player.cmds if cmd.name == "look")
    look_cmd.match(player, "look")
    assert "hôpital" in client.outputs[0]
    assert "test-description" in client.outputs[0]
