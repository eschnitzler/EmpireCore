"""MkDocs hooks for the documentation site."""

from griffe_pydantic._internal import common, static

# Two griffe-pydantic gaps, patched until it handles them itself.
_process_validator = common._process_function
_process_attribute = static._process_attribute


def _process_validator_of_known_fields(func, cls, fields):
    # A check_fields=False validator on a base names fields only its subclasses define.
    _process_validator(func, cls, [field for field in fields if field == "*" or field in cls.all_members])


def _process_annotated_attribute(attr, cls, **kwargs):
    # Pydantic fields are annotated; a bare `command = "gaa"` overrides the base's ClassVar.
    if attr.annotation is not None:
        _process_attribute(attr, cls, **kwargs)


common._process_function = _process_validator_of_known_fields
static._process_attribute = _process_annotated_attribute
