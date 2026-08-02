from mushroom.world import powers
from mushroom.world.objects import Config, Object, Thing
from mushroom.world.player import Player
from mushroom.world.room import Room

__all__ = [
    "Config",
    "Object",
    "PlayerRoom",
    "Thing",
    "powers",
]

MRPlayer = Player
MRRoom = Room
MRThing = Thing
MRObject = Object

MRPower = powers.Power
God = powers.God
Engineer = powers.Engineer
Examiner = powers.Examiner
Digger = powers.Digger
Tinkerer = powers.Tinkerer
