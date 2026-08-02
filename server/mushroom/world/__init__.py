from mushroom.world.objects import Config
from mushroom.world.objects import Object
from mushroom.world.objects import Thing
from mushroom.world.player import Player
from mushroom.world.room import Room
from mushroom.world import powers

__all__ = [
    "Config",
    "Object",
    "Player" "Room",
    "Thing",
    "powers",
]

MRPlayer = Player
MRRoom = Room
MRThing = Thing

God = powers.God
