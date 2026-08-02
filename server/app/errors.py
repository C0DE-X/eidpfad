class RuleViolation(ValueError):
    """A client intent that is syntactically valid but illegal in game state."""


class ContentViolation(ValueError):
    """A checked-in content catalog is malformed or internally inconsistent."""
