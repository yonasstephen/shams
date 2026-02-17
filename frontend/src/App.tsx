/**
 * Main App component with routing
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LeagueProvider } from './context/LeagueContext';
import { WaiverWireProvider } from './context/WaiverWireContext';
import { MatchupProvider } from './context/MatchupContext';
import { Home } from './pages/Home';
import { Login } from './pages/Login';
import { PlayerSearch } from './pages/PlayerSearch';
import { WaiverWire } from './pages/WaiverWire';
import { Matchup } from './pages/Matchup';
import { BoxScores } from './pages/BoxScores';
import { CacheDebug } from './pages/CacheDebug';
import { AuthCallback } from './components/AuthCallback';

function App() {
  return (
    <BrowserRouter>
      <LeagueProvider>
        <WaiverWireProvider>
          <MatchupProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/auth/callback" element={<AuthCallback />} />
              <Route path="/auth/success" element={<AuthCallback />} />
              <Route path="/" element={<Home />} />
              <Route path="/player" element={<PlayerSearch />} />
              <Route path="/waiver" element={<WaiverWire />} />
              <Route path="/matchup" element={<Matchup />} />
              <Route path="/boxscores" element={<BoxScores />} />
              <Route path="/cache-debug" element={<CacheDebug />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </MatchupProvider>
        </WaiverWireProvider>
      </LeagueProvider>
    </BrowserRouter>
  );
}

export default App;

