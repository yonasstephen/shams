/**
 * Custom Dropdown Component
 * Provides consistent cross-browser dropdown styling
 */

import { useState, useRef, useEffect } from 'react';

interface DropdownOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

interface DropdownProps {
  value: string | number;
  onChange: (value: string | number) => void;
  options: DropdownOption[];
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  id?: string;
  title?: string;
}

export function Dropdown({
  value,
  onChange,
  options,
  disabled = false,
  placeholder = 'Select...',
  className = '',
  id,
  title,
}: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const optionsRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find(opt => opt.value === value);
  const displayText = selectedOption?.label || placeholder;

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Scroll highlighted option into view
  useEffect(() => {
    if (isOpen && highlightedIndex >= 0 && optionsRef.current) {
      const highlightedElement = optionsRef.current.children[highlightedIndex] as HTMLElement;
      if (highlightedElement && typeof highlightedElement.scrollIntoView === 'function') {
        highlightedElement.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [highlightedIndex, isOpen]);

  const handleToggle = () => {
    if (!disabled) {
      setIsOpen(!isOpen);
      if (!isOpen) {
        // Set highlighted to current selection when opening
        const currentIndex = options.findIndex(opt => opt.value === value);
        setHighlightedIndex(currentIndex);
      }
    }
  };

  const handleSelect = (optionValue: string | number) => {
    onChange(optionValue);
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (disabled) return;

    switch (event.key) {
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          const currentIndex = options.findIndex(opt => opt.value === value);
          setHighlightedIndex(currentIndex);
        } else if (highlightedIndex >= 0) {
          const option = options[highlightedIndex];
          if (!option.disabled) {
            handleSelect(option.value);
          }
        }
        break;
      case 'Escape':
        event.preventDefault();
        setIsOpen(false);
        setHighlightedIndex(-1);
        break;
      case 'ArrowDown':
        event.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          const currentIndex = options.findIndex(opt => opt.value === value);
          setHighlightedIndex(currentIndex);
        } else {
          setHighlightedIndex(prev => {
            let next = prev + 1;
            while (next < options.length && options[next].disabled) {
              next++;
            }
            return next < options.length ? next : prev;
          });
        }
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (!isOpen) {
          setIsOpen(true);
          const currentIndex = options.findIndex(opt => opt.value === value);
          setHighlightedIndex(currentIndex);
        } else {
          setHighlightedIndex(prev => {
            let next = prev - 1;
            while (next >= 0 && options[next].disabled) {
              next--;
            }
            return next >= 0 ? next : prev;
          });
        }
        break;
      case 'Home':
        event.preventDefault();
        if (isOpen) {
          let firstEnabled = 0;
          while (firstEnabled < options.length && options[firstEnabled].disabled) {
            firstEnabled++;
          }
          if (firstEnabled < options.length) {
            setHighlightedIndex(firstEnabled);
          }
        }
        break;
      case 'End':
        event.preventDefault();
        if (isOpen) {
          let lastEnabled = options.length - 1;
          while (lastEnabled >= 0 && options[lastEnabled].disabled) {
            lastEnabled--;
          }
          if (lastEnabled >= 0) {
            setHighlightedIndex(lastEnabled);
          }
        }
        break;
    }
  };

  return (
    <div
      ref={dropdownRef}
      className={`relative ${className}`}
      id={id}
      title={title}
    >
      <button
        type="button"
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        className={`
          w-full px-3 py-2 text-sm text-left bg-white border border-gray-200 rounded-xl
          focus:outline-none focus:ring-2 focus:ring-neutral-900 focus:border-transparent
          transition-all flex items-center justify-between
          ${disabled ? 'opacity-50 cursor-not-allowed bg-gray-50' : 'cursor-pointer hover:border-gray-300'}
        `}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="block truncate">{displayText}</span>
        <svg
          className={`w-4 h-4 ml-2 transition-transform ${isOpen ? 'transform rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && !disabled && (
        <div
          ref={optionsRef}
          className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-xl shadow-lg max-h-60 overflow-auto"
          role="listbox"
        >
          {options.map((option, index) => {
            const isSelected = option.value === value;
            const isHighlighted = index === highlightedIndex;

            return (
              <div
                key={option.value}
                onClick={() => !option.disabled && handleSelect(option.value)}
                className={`
                  px-3 py-2 text-sm cursor-pointer transition-colors
                  ${option.disabled ? 'opacity-50 cursor-not-allowed' : ''}
                  ${isSelected ? 'bg-neutral-900 text-white font-medium' : ''}
                  ${!isSelected && isHighlighted ? 'bg-neutral-100' : ''}
                  ${!isSelected && !isHighlighted && !option.disabled ? 'hover:bg-neutral-50' : ''}
                `}
                role="option"
                aria-selected={isSelected}
                aria-disabled={option.disabled}
              >
                {option.label}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

