/**
 * Yahoo OAuth callback handler
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLeague } from '../context/LeagueContext';

export function AuthCallback() {
  const navigate = useNavigate();
  const { refreshLeagues } = useLeague();
  const [error] = useState<string | null>(null);

  useEffect(() => {
    // The backend handles the OAuth callback and sets the session cookie
    // Then redirects to /auth/success
    // Load leagues and redirect to the home page
    const loadAndRedirect = async () => {
      try {
        await refreshLeagues();
      } catch (err) {
        console.error('Failed to load leagues after auth:', err);
      }
      navigate('/');
    };

    const timer = setTimeout(loadAndRedirect, 1000);

    return () => clearTimeout(timer);
  }, [navigate, refreshLeagues]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-red-600 mb-4">Authentication Failed</h2>
            <p className="text-gray-600">{error}</p>
            <button
              onClick={() => navigate('/login')}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Authentication Successful</h2>
          <p className="text-gray-600">Redirecting to app...</p>
        </div>
      </div>
    </div>
  );
}

