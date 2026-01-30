"""Template semantics registry for Jinja2 validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArgSpec:
    """Specification for a single argument."""

    name: str
    required: bool


@dataclass(frozen=True)
class Signature:
    """Signature for a filter or test."""

    name: str
    min_args: int
    max_args: int | None  # None = unlimited
    arg_specs: tuple[ArgSpec, ...] = ()


# Filter signatures for Home Assistant template filters
FILTER_SIGNATURES: dict[str, Signature] = {
    # Type conversion
    "float": Signature("float", 0, 1, (ArgSpec("default", False),)),
    "int": Signature(
        "int", 0, 2, (ArgSpec("default", False), ArgSpec("base", False))
    ),
    "bool": Signature("bool", 0, 1, (ArgSpec("default", False),)),
    # Arithmetic
    "multiply": Signature(
        "multiply", 1, 2, (ArgSpec("amount", True), ArgSpec("default", False))
    ),
    "add": Signature("add", 1, 2, (ArgSpec("amount", True), ArgSpec("default", False))),
    "round": Signature(
        "round",
        0,
        3,
        (
            ArgSpec("precision", False),
            ArgSpec("method", False),
            ArgSpec("default", False),
        ),
    ),
    # Math functions
    "log": Signature("log", 0, 2, (ArgSpec("base", False), ArgSpec("default", False))),
    "sin": Signature("sin", 0, 0),
    "cos": Signature("cos", 0, 0),
    "tan": Signature("tan", 0, 0),
    "sqrt": Signature("sqrt", 0, 1, (ArgSpec("default", False),)),
    "clamp": Signature(
        "clamp",
        2,
        3,
        (ArgSpec("min", True), ArgSpec("max", True), ArgSpec("default", False)),
    ),
    # Statistical
    "average": Signature("average", 0, 0),
    "median": Signature("median", 0, 0),
    "statistical_mode": Signature("statistical_mode", 0, 0),
    # Conditional
    "iif": Signature(
        "iif",
        1,
        3,
        (ArgSpec("if_true", False), ArgSpec("if_false", False), ArgSpec("if_none", False)),
    ),
    # JSON
    "to_json": Signature(
        "to_json",
        0,
        3,
        (
            ArgSpec("ensure_ascii", False),
            ArgSpec("pretty_print", False),
            ArgSpec("sort_keys", False),
        ),
    ),
    "from_json": Signature("from_json", 0, 1, (ArgSpec("default", False),)),
    # Regex
    "regex_match": Signature(
        "regex_match", 1, 2, (ArgSpec("pattern", True), ArgSpec("ignorecase", False))
    ),
    "regex_search": Signature(
        "regex_search", 1, 2, (ArgSpec("pattern", True), ArgSpec("ignorecase", False))
    ),
    "regex_replace": Signature(
        "regex_replace",
        2,
        3,
        (ArgSpec("find", True), ArgSpec("replace", True), ArgSpec("ignorecase", False)),
    ),
    "regex_findall": Signature("regex_findall", 1, 1, (ArgSpec("pattern", True),)),
    "regex_findall_index": Signature(
        "regex_findall_index", 1, 2, (ArgSpec("pattern", True), ArgSpec("index", False))
    ),
    # Encoding
    "base64_encode": Signature("base64_encode", 0, 0),
    "base64_decode": Signature("base64_decode", 0, 0),
    # Hashing
    "md5": Signature("md5", 0, 0),
    "sha1": Signature("sha1", 0, 0),
    "sha256": Signature("sha256", 0, 0),
    "sha512": Signature("sha512", 0, 0),
    # String
    "slugify": Signature("slugify", 0, 0),
    # Timestamp
    "as_timestamp": Signature("as_timestamp", 0, 0),
    "as_datetime": Signature("as_datetime", 0, 0),
    "as_local": Signature("as_local", 0, 0),
}
