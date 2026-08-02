from mushroom.world import powers


def test_setattr_dbref(player, client, game):
    player.powers.append(powers.Tinkerer())
    client.handle_input("setattr me blarg #0")
    assert hasattr(player, "blarg")
    assert player.blarg == game.db.get(0)
