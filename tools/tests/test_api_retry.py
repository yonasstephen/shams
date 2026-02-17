"""Tests for API retry logic with exponential backoff."""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest

from tools.utils.api_retry import retry_with_backoff


@pytest.mark.unit
def test_retry_success_first_try():
    """Test that successful function returns immediately."""
    mock_func = Mock(return_value="success")

    @retry_with_backoff(max_retries=3)
    def test_function():
        return mock_func()

    result = test_function()

    assert result == "success"
    assert mock_func.call_count == 1


@pytest.mark.unit
def test_retry_success_after_failures():
    """Test that function retries and eventually succeeds."""
    call_count = 0

    def failing_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Temporary error")
        return "success"

    @retry_with_backoff(max_retries=5, base_delay=0.01)
    def test_function():
        return failing_function()

    result = test_function()

    assert result == "success"
    assert call_count == 3


@pytest.mark.unit
def test_retry_max_retries_exceeded():
    """Test that function raises after max retries."""
    mock_func = Mock(side_effect=ValueError("Persistent error"))

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def test_function():
        return mock_func()

    with pytest.raises(ValueError, match="Persistent error"):
        test_function()

    # Should try initial + 3 retries = 4 total attempts
    assert mock_func.call_count == 4


@pytest.mark.unit
def test_retry_exponential_backoff():
    """Test that retry delays increase exponentially."""
    call_count = 0

    def failing_function():
        nonlocal call_count
        call_count += 1
        raise ValueError("Always fails")

    @retry_with_backoff(max_retries=3, base_delay=0.1, exponential_base=2.0)
    def test_function():
        failing_function()

    start_time = time.time()

    with pytest.raises(ValueError):
        test_function()

    total_time = time.time() - start_time

    # Expected delays: 0.1, 0.2, 0.4 = 0.7 seconds total (approximately)
    # Allow some tolerance for execution time
    assert total_time >= 0.6  # Should take at least 0.6 seconds
    assert total_time < 1.0  # But not too long


@pytest.mark.unit
def test_retry_max_delay():
    """Test that delay is capped at max_delay."""
    call_count = 0

    def failing_function():
        nonlocal call_count
        call_count += 1
        raise ValueError("Always fails")

    @retry_with_backoff(
        max_retries=5, base_delay=1.0, max_delay=0.2, exponential_base=2.0
    )
    def test_function():
        failing_function()

    start_time = time.time()

    with pytest.raises(ValueError):
        test_function()

    total_time = time.time() - start_time

    # With max_delay=0.2, all retries should use 0.2 seconds
    # 5 retries * 0.2 = 1.0 seconds (approximately)
    assert total_time >= 0.9
    assert total_time < 1.5


@pytest.mark.unit
def test_retry_specific_exception_type():
    """Test retrying only specific exception types."""
    call_count = 0

    def mixed_exception_function():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Retryable")
        else:
            raise TypeError("Not retryable")

    @retry_with_backoff(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
    def test_function():
        mixed_exception_function()

    # Should catch ValueError and retry, then encounter TypeError
    with pytest.raises(TypeError, match="Not retryable"):
        test_function()

    assert call_count == 2


@pytest.mark.unit
def test_retry_silent_mode():
    """Test that silent mode suppresses retry messages."""
    mock_func = Mock(
        side_effect=[ValueError("Error 1"), ValueError("Error 2"), "success"]
    )

    @retry_with_backoff(max_retries=3, base_delay=0.01, silent=True)
    def test_function():
        return mock_func()

    # Should succeed without printing warnings
    result = test_function()

    assert result == "success"
    assert mock_func.call_count == 3


@pytest.mark.unit
def test_retry_with_progress_display():
    """Test retry with progress display integration."""
    mock_progress = Mock()
    mock_func = Mock(side_effect=[ValueError("Error"), "success"])

    from tools.utils import api_retry

    api_retry.set_progress_display(mock_progress)

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def test_function():
        return mock_func()

    result = test_function()

    assert result == "success"
    # Progress display should have been called for retry warning
    assert mock_progress.add_line.called

    # Reset
    api_retry.set_progress_display(None)


@pytest.mark.unit
def test_retry_preserves_function_name():
    """Test that decorator preserves original function name."""

    @retry_with_backoff(max_retries=3)
    def my_custom_function():
        return "test"

    assert my_custom_function.__name__ == "my_custom_function"


@pytest.mark.unit
def test_retry_with_args_and_kwargs():
    """Test that decorator works with function arguments."""

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def function_with_args(a, b, c=None):
        if a < 5:
            raise ValueError("a too small")
        return f"{a}-{b}-{c}"

    result = function_with_args(10, "test", c="value")

    assert result == "10-test-value"


@pytest.mark.unit
def test_retry_zero_retries():
    """Test behavior with zero retries (no retry, just initial attempt)."""
    mock_func = Mock(side_effect=ValueError("Error"))

    @retry_with_backoff(max_retries=0, base_delay=0.01)
    def test_function():
        return mock_func()

    with pytest.raises(ValueError):
        test_function()

    # Should only try once (no retries)
    assert mock_func.call_count == 1


@pytest.mark.unit
def test_retry_returns_none_on_failure():
    """Test edge case where function might return None after all retries."""
    call_count = 0

    def function_with_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("Always fails")

    @retry_with_backoff(max_retries=2, base_delay=0.01)
    def test_function():
        try:
            function_with_error()
        except ValueError:
            if call_count >= 3:
                raise
            else:
                raise

    with pytest.raises(ValueError):
        test_function()
