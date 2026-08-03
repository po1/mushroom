from mushroom import util


def test_is_player(player):
    assert util.is_player(player) is True


def test_is_room(room):
    assert util.is_room(room) is True
