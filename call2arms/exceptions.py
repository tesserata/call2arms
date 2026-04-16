class ChannelNotFoundException(Exception):
    def __init__(self, channel_id: int) -> None:
        super().__init__(
            f"Channel with id {channel_id} was not found in the server or cannot be sent messages to"
        )


class RoleNotFoundException(Exception):
    def __init__(self, role_id: int) -> None:
        super().__init__(f"Role with id {role_id} was not found in the server")
