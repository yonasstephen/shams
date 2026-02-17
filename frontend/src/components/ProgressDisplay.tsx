/**
 * Progress Display Component
 * Shows completed steps and current operation with spinner
 */

interface ProgressDisplayProps {
  completedSteps: string[];
  currentStep: string | null;
  isComplete: boolean;
}

export function ProgressDisplay({ completedSteps, currentStep, isComplete }: ProgressDisplayProps) {
  return (
    <div className="space-y-2">
      {/* Completed steps */}
      {completedSteps.map((step, index) => (
        <div key={index} className="flex items-start gap-2 text-sm">
          <span className="text-green-600 font-bold flex-shrink-0 mt-0.5">✓</span>
          <span className="text-gray-700">{step}</span>
        </div>
      ))}
      
      {/* Current step with spinner */}
      {currentStep && !isComplete && (
        <div className="flex items-start gap-2 text-sm">
          <div className="flex-shrink-0 mt-0.5">
            <svg 
              className="animate-spin h-4 w-4 text-blue-600" 
              xmlns="http://www.w3.org/2000/svg" 
              fill="none" 
              viewBox="0 0 24 24"
            >
              <circle 
                className="opacity-25" 
                cx="12" 
                cy="12" 
                r="10" 
                stroke="currentColor" 
                strokeWidth="4"
              />
              <path 
                className="opacity-75" 
                fill="currentColor" 
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>
          <span className="text-gray-600">{currentStep}</span>
        </div>
      )}
      
      {/* Completion message */}
      {isComplete && currentStep && (
        <div className="flex items-start gap-2 text-sm mt-3 pt-3 border-t border-gray-200">
          <span className="text-green-600 font-bold flex-shrink-0 mt-0.5">✓</span>
          <span className="text-green-700 font-medium">{currentStep}</span>
        </div>
      )}
    </div>
  );
}

