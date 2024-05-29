from dataclasses import dataclass


@dataclass
class Config:
    """Instances of this class serve as global config."""

    listen_address: str = ""  # empty means to listen on all addresses
    listen_port: int = 1337

    motd_file: str = "MOTD"
    db_file: str = "world.sav"

    op_password: str = "lol"
    op_command_prefix: str = "@"

    # whether to send exceptions to the player
    debug: bool = True

    log_file: str = "server.log"

    autosave_period: int = 300
