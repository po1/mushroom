

def test_player_can_look(player, client):
    player.location.description = "test-description"
    client.handle_input("look")
    assert "hôpital" in client.outputs[0]
    assert "test-description" in client.outputs[0]
