/**
 * Main app layout with navigation
 */

import { Link, useLocation } from 'react-router-dom';
import { useLeague } from '../context/LeagueContext';
import { LeagueSelector } from './LeagueSelector';
import { BottomNavigation } from './BottomNavigation';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { defaultLeagueKey } = useLeague();

  const isActive = (path: string) => location.pathname === path;

  const navLinkClass = (path: string) =>
    `px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
      isActive(path)
        ? 'bg-neutral-900 text-white'
        : 'text-gray-700 hover:bg-neutral-150 hover:text-neutral-900'
    }`;

  return (
    <div className="min-h-screen bg-neutral-100">
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-[1800px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-2">
              <div className="flex-shrink-0 flex items-center">
                <Link to="/" className="text-xl md:text-2xl font-bold text-neutral-900">
                  Shams
                </Link>
              </div>
              {/* Show navigation links only when a league is selected - hidden on mobile (use bottom nav instead) */}
              {defaultLeagueKey && (
                <div className="hidden md:ml-6 md:flex md:gap-2">
                  <Link to="/player" className={navLinkClass('/player')}>
                    Players
                  </Link>
                  <Link to="/waiver" className={navLinkClass('/waiver')}>
                    Waiver Wire
                  </Link>
                  <Link to="/matchup" className={navLinkClass('/matchup')}>
                    Matchup
                  </Link>
                  <Link to="/boxscores" className={navLinkClass('/boxscores')}>
                    Box Scores
                  </Link>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 md:gap-3">
              {/* League selector dropdown - always show so users can select a league */}
              <div className="w-40 md:w-64">
                <LeagueSelector />
              </div>
              <Link
                to="/logout"
                className="hidden md:block px-4 py-2 rounded-xl text-sm font-medium text-gray-700 hover:bg-neutral-150 transition-colors"
              >
                Logout
              </Link>
              {/* Mobile logout icon */}
              <Link
                to="/logout"
                className="md:hidden p-2 rounded-xl text-gray-700 hover:bg-neutral-150 transition-colors"
                title="Logout"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-[1800px] mx-auto py-4 md:py-8 sm:px-6 lg:px-8 pb-20 md:pb-8">
        {children}
      </main>

      {/* Bottom navigation for mobile */}
      <BottomNavigation />
    </div>
  );
}

