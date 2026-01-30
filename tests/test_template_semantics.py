"""Tests for template_semantics module."""

from custom_components.autodoctor.template_semantics import ArgSpec, Signature


def test_argspec_creation():
    """Test ArgSpec dataclass creation."""
    arg = ArgSpec(name="default", required=False)
    assert arg.name == "default"
    assert arg.required is False


def test_argspec_required():
    """Test required ArgSpec."""
    arg = ArgSpec(name="amount", required=True)
    assert arg.name == "amount"
    assert arg.required is True


def test_signature_creation():
    """Test Signature dataclass creation."""
    sig = Signature(
        name="multiply",
        min_args=1,
        max_args=2,
        arg_specs=(ArgSpec("amount", True), ArgSpec("default", False)),
    )
    assert sig.name == "multiply"
    assert sig.min_args == 1
    assert sig.max_args == 2
    assert len(sig.arg_specs) == 2


def test_signature_unlimited_args():
    """Test Signature with unlimited max args."""
    sig = Signature(name="join", min_args=0, max_args=None)
    assert sig.max_args is None
