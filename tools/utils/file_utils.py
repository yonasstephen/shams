"""File utilities for safe file operations."""

import os
import tempfile
from pathlib import Path
from typing import Union


def sanitize_env_file(file_path: Union[str, Path]) -> None:
    """Sanitize a .env file by removing malformed lines.

    The yfpy library has a bug where it doesn't handle lines without '=' properly.
    This function removes any lines that don't have the proper KEY=value format,
    preventing the library from crashing.

    Args:
        file_path: Path to the .env file to sanitize
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return
    
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
    except Exception:
        return
    
    # Filter out malformed lines
    valid_lines = []
    seen_keys = set()
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        # Must have '=' to be valid
        if '=' not in line:
            continue
        
        # Extract key and check for duplicates (keep first occurrence)
        key = line.split('=', 1)[0]
        if key in seen_keys:
            continue
        
        seen_keys.add(key)
        valid_lines.append(line)
    
    # Rewrite the file atomically if we removed any lines
    if len(valid_lines) != len([l for l in lines if l.strip() and not l.strip().startswith('#')]):
        content = '\n'.join(valid_lines) + '\n'
        atomic_write(file_path, content)


def atomic_write(file_path: Union[str, Path], content: str) -> None:
    """Write content to a file atomically to prevent corruption from concurrent writes.

    This function writes to a temporary file first, then atomically renames it to the
    target path. This ensures that:
    1. The file is never partially written
    2. Concurrent writes don't corrupt the file
    3. Readers always see a complete file

    Args:
        file_path: Path to the target file
        content: Content to write to the file
    """
    file_path = Path(file_path)
    
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create a temporary file in the same directory as the target
    # This ensures the rename operation is atomic (same filesystem)
    fd, temp_path = tempfile.mkstemp(
        dir=file_path.parent,
        prefix=f".{file_path.name}.",
        suffix=".tmp"
    )
    
    try:
        # Write content to temporary file
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        
        # Atomic rename - this is atomic on POSIX systems
        os.replace(temp_path, file_path)
    except Exception:
        # Clean up temp file if something went wrong
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def write_env_file(file_path: Union[str, Path], env_vars: dict) -> None:
    """Write environment variables to a .env file atomically.

    Args:
        file_path: Path to the .env file
        env_vars: Dictionary of environment variable names to values
    """
    lines = []
    for key, value in env_vars.items():
        # Quote values that might have special characters
        if isinstance(value, str) and ('"' not in value):
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f'{key}={value}')
    
    content = '\n'.join(lines) + '\n'
    atomic_write(file_path, content)

