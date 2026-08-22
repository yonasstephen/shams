/**
 * Draft room — second screen for the live draft assistant.
 *
 * The Chrome extension reads Yahoo's draft room and pushes state to the
 * backend; this page polls the most recent board. It is a mirror, not a second
 * brain: every number comes from the same endpoint the side panel uses, so the
 * two can never disagree.
 *
 * Useful when you have a second monitor, and as the fallback if the side panel
 * misbehaves mid-draft.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Layout } from '../components/Layout';
import { api } from '../services/api';
import type { DraftBoardResponse, DraftRecommendation } from '../types/api';

/** Fast enough to feel live on a 30s clock, slow enough to be free on localhost. */
const POLL_MS = 2000;

const signed = (value: number | null | undefined, digits = 2): string =>
  value === null || value === undefined
    ? '—'
    : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;

/** Drop the flex slots; they add width without adding information. */
const realPositions = (positions: string[]): string =>
  positions.filter((p) => !['Util', 'G', 'F'].includes(p)).join('/');

function GapLabel({ rec }: { rec: DraftRecommendation }) {
  if (!rec.gap_label || !['steal', 'value', 'reach', 'big reach'].includes(rec.gap_label)) {
    return null;
  }
  const good = rec.gap_label === 'steal' || rec.gap_label === 'value';
  return (
    <span
      className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
        good ? 'bg-emerald-900/40 text-emerald-400' : 'bg-rose-900/40 text-rose-400'
      }`}
    >
      {rec.gap_label}
    </span>
  );
}

function PlayerRow({ rec, rank }: { rec: DraftRecommendation; rank: number }) {
  const bits = [realPositions(rec.positions), rec.nba_team];
  if (rec.average_pick) bits.push(`ADP ${rec.average_pick.toFixed(0)}`);
  if (rec.survival !== null) bits.push(`${Math.round(rec.survival * 100)}% to last`);

  return (
    <tr className="border-b border-gray-800 hover:bg-gray-800/40">
      <td className="py-2 pr-3 text-right text-xs tabular-nums text-gray-500">{rank}</td>
      <td className="py-2 pr-3">
        <div className="font-semibold text-gray-100">
          {rec.name}
          <GapLabel rec={rec} />
          {rec.injury && (
            <span className="ml-2 rounded bg-amber-900/40 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-400">
              {rec.injury}
            </span>
          )}
        </div>
        <div className="text-xs text-gray-500">{bits.filter(Boolean).join(' · ')}</div>
      </td>
      <td className="py-2 pr-3 text-right font-semibold tabular-nums text-gray-100">
        {signed(rec.marginal_value)}
      </td>
      <td className="py-2 pr-3 text-right text-xs tabular-nums text-gray-400">
        {rec.standings_delta === null ? '—' : signed(rec.standings_delta)}
      </td>
      <td className="py-2 text-xs text-gray-400">{rec.reason}</td>
    </tr>
  );
}

function ScarcityCard({ board }: { board: DraftBoardResponse }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h2 className="mb-1 text-xs font-bold uppercase tracking-wider text-gray-500">
        Category scarcity
      </h2>
      <p className="mb-3 text-xs text-gray-500">
        Elite sources left versus teams that still need them.
      </p>
      <div className="space-y-2">
        {board.supply.map((s) => (
          <div
            key={s.name}
            className={`rounded border-l-2 bg-gray-800/50 px-3 py-2 ${
              s.is_supply_crunch
                ? 'border-rose-500'
                : s.is_weakness
                ? 'border-amber-500'
                : 'border-gray-700'
            }`}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-bold text-gray-100">{s.display_name}</span>
              <span className="text-xs text-gray-500">
                #{s.my_rank || '—'} of {board.num_teams} · {signed(s.deficit, 1)}
              </span>
            </div>
            <div className="mt-0.5 text-xs text-gray-400">
              {s.elite_remaining} elite left · {s.elite_surviving.toFixed(1)} survive to your
              pick · {s.teams_below_mean} teams needy
              {s.cliff_in_picks ? ` · next cliff ${s.cliff_in_picks} deep` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function HeatMap({ board }: { board: DraftBoardResponse }) {
  const scale = Math.max(1, ...board.supply.map((s) => Math.abs(s.deficit)));
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-500">
        Category standing vs. an average team
      </h2>
      <div className="space-y-1">
        {board.supply.map((s) => (
          <div key={s.name} className="grid grid-cols-[3rem_1fr_3rem] items-center gap-2 text-xs">
            <span className="text-gray-300">{s.display_name}</span>
            <div className="relative h-3.5 rounded bg-gray-800">
              <div
                className={`absolute top-0 bottom-0 rounded ${
                  s.deficit >= 0 ? 'left-1/2 bg-emerald-500' : 'right-1/2 bg-rose-500'
                }`}
                style={{ width: `${(Math.abs(s.deficit) / scale) * 50}%` }}
              />
              <div className="absolute top-0 bottom-0 left-1/2 w-px bg-gray-600" />
            </div>
            <span className="text-right tabular-nums text-gray-400">{signed(s.deficit, 1)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DraftRoom() {
  const [board, setBoard] = useState<DraftBoardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  // Ref rather than state: the poll loop reads it without re-subscribing.
  const boardRef = useRef<DraftBoardResponse | null>(null);

  const poll = useCallback(async () => {
    try {
      const next = await api.getLatestDraftBoard();
      setError(null);
      if (!next) return;
      // Only re-render when something actually moved.
      const previous = boardRef.current;
      if (
        previous &&
        previous.current_pick === next.current_pick &&
        previous.headline?.player_id === next.headline?.player_id &&
        previous.seconds_remaining === next.seconds_remaining
      ) {
        return;
      }
      boardRef.current = next;
      setBoard(next);
      setLastUpdate(new Date());
    } catch (err) {
      setError('Cannot reach the Shams backend. Is it running on port 8000?');
    }
  }, []);

  useEffect(() => {
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => clearInterval(timer);
  }, [poll]);

  if (error) {
    return (
      <Layout>
        <div className="rounded-lg border border-rose-800 bg-rose-950/40 p-6 text-rose-300">
          {error}
        </div>
      </Layout>
    );
  }

  if (!board) {
    return (
      <Layout>
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-8 text-center text-gray-400">
          <p className="mb-2 text-lg font-semibold text-gray-200">Waiting for a draft</p>
          <p className="text-sm">
            Open your Yahoo draft room with the Shams extension installed. This page mirrors
            whatever the extension is reading.
          </p>
        </div>
      </Layout>
    );
  }

  const headline = board.headline;

  return (
    <Layout>
      <div className="space-y-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold text-gray-100">
              {board.league_name || 'Draft room'}
              {board.is_mock && (
                <span className="ml-2 rounded bg-gray-800 px-2 py-0.5 text-xs uppercase text-gray-400">
                  mock
                </span>
              )}
            </h1>
            <p className="text-sm text-gray-500">
              {board.num_teams} teams · {board.total_rounds} rounds · pick {board.current_pick + 1}
              {board.picks_until_my_turn !== null && !board.is_my_turn
                ? ` · ${board.picks_until_my_turn} until your turn`
                : ''}
            </p>
          </div>
          <div className="text-right">
            {board.seconds_remaining !== null && (
              <div
                className={`text-2xl font-bold tabular-nums ${
                  board.seconds_remaining <= 10 ? 'text-rose-400' : 'text-gray-200'
                }`}
              >
                0:{String(board.seconds_remaining).padStart(2, '0')}
              </div>
            )}
            <div className="text-xs text-gray-600">
              {lastUpdate ? `updated ${lastUpdate.toLocaleTimeString()}` : ''}
            </div>
          </div>
        </div>

        {board.warnings.length > 0 && (
          <div className="rounded-lg border border-amber-800 bg-amber-950/40 px-4 py-2 text-sm text-amber-300">
            {board.warnings.join(' · ')}
          </div>
        )}

        {board.is_my_turn && (
          <div className="rounded-lg border border-emerald-700 bg-emerald-950/40 px-4 py-2 font-bold text-emerald-300">
            You're on the clock.
          </div>
        )}

        {headline && (
          <div className="rounded-lg border border-gray-800 border-l-4 border-l-indigo-500 bg-gray-900 p-5">
            <div className="text-2xl font-bold text-gray-50">{headline.name}</div>
            <div className="text-sm text-gray-500">
              {[realPositions(headline.positions), headline.nba_team, headline.injury]
                .filter(Boolean)
                .join(' · ')}
            </div>
            <div className="mt-3 text-gray-200">{headline.reason}</div>
            <div className="mt-4 flex flex-wrap gap-8">
              <div>
                <div className="text-xl font-bold tabular-nums text-gray-100">
                  {signed(headline.marginal_value)}
                </div>
                <div className="text-xs text-gray-500">above replacement</div>
              </div>
              {headline.standings_delta !== null && (
                <div>
                  <div
                    className={`text-xl font-bold tabular-nums ${
                      headline.standings_delta >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {signed(headline.standings_delta)}
                  </div>
                  <div className="text-xs text-gray-500">projected category wins</div>
                </div>
              )}
              {headline.survival !== null && (
                <div>
                  <div className="text-xl font-bold tabular-nums text-gray-100">
                    {Math.round(headline.survival * 100)}%
                  </div>
                  <div className="text-xs text-gray-500">survives to your next pick</div>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <ScarcityCard board={board} />
          <div className="space-y-4">
            <HeatMap board={board} />
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
              <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-gray-500">
                Build
              </h2>
              <div className="text-sm text-gray-200">
                <span className="font-bold text-indigo-400">{board.punt?.label ?? 'no punt'}</span>
                {' · '}
                {board.projected_category_wins.toFixed(1)} projected category wins
              </div>
              {Object.keys(board.positional_gaps).length > 0 && (
                <div className="mt-2 text-xs text-gray-400">
                  Still need:{' '}
                  {Object.entries(board.positional_gaps)
                    .map(([pos, n]) => (n > 1 ? `${pos} x${n}` : pos))
                    .join(', ')}
                </div>
              )}
              <div className="mt-2 text-xs text-gray-600">
                {board.projected_players} projections from {board.projection_source}
                {board.schedule_available ? ' · schedule-aware' : ' · schedule not cached'}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
          <h2 className="mb-3 text-xs font-bold uppercase tracking-wider text-gray-500">
            Best available
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="pb-2 pr-3 text-right">#</th>
                  <th className="pb-2 pr-3">Player</th>
                  <th className="pb-2 pr-3 text-right">Above repl.</th>
                  <th className="pb-2 pr-3 text-right">Cat wins</th>
                  <th className="pb-2">Why</th>
                </tr>
              </thead>
              <tbody>
                {board.board.map((rec, index) => (
                  <PlayerRow key={rec.player_id} rec={rec} rank={index + 1} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Layout>
  );
}
