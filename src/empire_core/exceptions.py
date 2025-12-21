class EmpireError(Exception):
    """Base class for all EmpireCore exceptions."""

    pass


class NetworkError(EmpireError):
    """Raised when a network operation fails."""

    pass


class LoginError(EmpireError):
    """Raised when the login sequence fails."""

    pass


class LoginCooldownError(LoginError):
    """Raised when the server rejects login due to rate limiting."""

    def __init__(self, cooldown: int, message: str = "Login cooldown active"):
        self.cooldown = cooldown
        super().__init__(f"{message}: Retry in {cooldown}s")


class PacketError(EmpireError):
    """Raised when packet parsing fails."""

    pass


class TimeoutError(EmpireError):
    """Raised when an operation times out."""

    pass


class ActionError(EmpireError):
    """Raised when a game action fails."""

    pass
