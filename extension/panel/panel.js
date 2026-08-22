/**
 * Side panel renderer.
 *
 * Renders whatever the service worker last received. It holds no analysis logic
 * of its own — every number here comes from the backend, so the panel and the
 * Shams web app can never disagree.
 */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const fmt = (value, digits = 2) =>
    value === null || value === undefined ? "—" : value.toFixed(digits);
  const signed = (value, digits = 2) =>
    value === null || value === undefined
      ? "—"
      : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;

  // ---- tabs ----------------------------------------------------------

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("is-active"));
      document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
      tab.classList.add("is-active");
      document.querySelector(`.view[data-view="${tab.dataset.tab}"]`).classList.add("is-active");
    });
  });

  // ---- rendering -----------------------------------------------------

  const playerRow = (rec, showDelta = true) => {
    const li = el("li", "row");

    const who = el("div", "who");
    const name = el("div", "n", rec.name);
    if (rec.gap_label && ["steal", "value", "reach", "big reach"].includes(rec.gap_label)) {
      name.appendChild(el("span", `tag ${rec.gap_label.replace(" ", "-")}`, rec.gap_label));
    }
    if (rec.injury) name.appendChild(el("span", "tag inj", rec.injury));
    who.appendChild(name);

    const bits = [rec.positions.filter((p) => !["Util", "G", "F"].includes(p)).join("/")];
    if (rec.nba_team) bits.push(rec.nba_team);
    if (rec.average_pick) bits.push(`ADP ${rec.average_pick.toFixed(0)}`);
    if (rec.survival !== null && rec.survival !== undefined) {
      bits.push(`${Math.round(rec.survival * 100)}% to last`);
    }
    who.appendChild(el("div", "meta2", bits.filter(Boolean).join(" · ")));
    li.appendChild(who);

    const val = el("div", "val", signed(rec.marginal_value));
    if (showDelta && rec.standings_delta !== null && rec.standings_delta !== undefined) {
      val.appendChild(el("small", null, `${signed(rec.standings_delta)} cat`));
    }

    // Fallback for when the adapter misses a pick: take him off the board by
    // hand rather than letting the whole board drift out of sync.
    const mark = el("button", "mark", "\u2715");
    mark.title = `Mark ${rec.name} as drafted`;
    mark.addEventListener("click", (event) => {
      event.stopPropagation();
      chrome.runtime.sendMessage({ type: "MARK_DRAFTED", playerId: rec.player_id });
    });
    val.appendChild(mark);

    li.appendChild(val);
    return li;
  };

  const renderHeadline = (board) => {
    const node = $("headline");
    node.innerHTML = "";
    const rec = board.headline;
    if (!rec) {
      node.className = "headline empty";
      node.textContent = board.warnings?.length
        ? board.warnings[0]
        : "No players available.";
      return;
    }
    node.className = "headline";

    node.appendChild(el("div", "name", rec.name));
    const sub = [rec.positions.filter((p) => !["Util", "G", "F"].includes(p)).join("/"), rec.nba_team]
      .filter(Boolean)
      .join(" · ");
    node.appendChild(el("div", "sub", sub + (rec.injury ? ` · ${rec.injury}` : "")));
    node.appendChild(el("div", "reason", rec.reason));

    // Each stat renders as a large value over a small label.
    const stats = el("div", "stats");
    const mk = (label, value, tone) => {
      const s = el("div", "stat");
      s.appendChild(el("b", tone || "", value));
      s.appendChild(document.createTextNode(label));
      return s;
    };
    stats.appendChild(mk("above replacement", signed(rec.marginal_value)));
    if (rec.standings_delta !== null && rec.standings_delta !== undefined) {
      stats.appendChild(
        mk("cat wins", signed(rec.standings_delta), rec.standings_delta >= 0 ? "pos" : "neg")
      );
    }
    if (rec.survival !== null && rec.survival !== undefined) {
      stats.appendChild(
        mk("survives", `${Math.round(rec.survival * 100)}%`, rec.survival < 0.35 ? "neg" : "")
      );
    }
    node.appendChild(stats);
  };

  const renderTurn = (board) => {
    const node = $("turn");
    node.className = "turn";
    if (board.is_my_turn) {
      node.classList.add("is-my-turn");
      node.textContent = "You're on the clock.";
    } else if (board.picks_until_my_turn === null || board.picks_until_my_turn === undefined) {
      node.textContent = "No picks remaining.";
    } else {
      node.innerHTML = `<strong>${board.picks_until_my_turn}</strong> picks until your turn · pick ${
        board.current_pick + 1
      }`;
    }
  };

  const renderSupply = (board) => {
    const list = $("supply");
    list.innerHTML = "";
    const maxSources = Math.max(1, ...board.supply.map((s) => s.elite_remaining));

    board.supply.forEach((s) => {
      const li = el("li");
      if (s.is_supply_crunch) li.classList.add("is-crunch");
      else if (s.is_weakness) li.classList.add("is-weak");

      const head = el("div", "head");
      head.appendChild(el("span", "cat", s.display_name));
      head.appendChild(
        el("span", "rank", `${s.my_rank ? `#${s.my_rank}` : "—"} of ${board.num_teams} · ${signed(s.deficit, 1)}`)
      );
      li.appendChild(head);

      li.appendChild(
        el(
          "div",
          "detail",
          `${s.elite_remaining} elite left · ${fmt(s.elite_surviving, 1)} survive to your pick · ` +
            `${s.teams_below_mean} teams needy` +
            (s.cliff_in_picks ? ` · next cliff ${s.cliff_in_picks} deep` : "")
        )
      );

      const bars = el("div", "bars");
      const supplyBar = el("div", "bar");
      supplyBar.style.width = `${Math.max(2, (s.elite_remaining / maxSources) * 55)}px`;
      const demandBar = el("div", "bar demand");
      demandBar.style.width = `${Math.max(2, (s.teams_below_mean / Math.max(1, board.num_teams)) * 55)}px`;
      bars.appendChild(supplyBar);
      bars.appendChild(demandBar);
      bars.appendChild(el("span", "legend", "supply / demand"));
      li.appendChild(bars);

      list.appendChild(li);
    });
  };

  const renderTeam = (board) => {
    const heat = $("heatmap");
    heat.innerHTML = "";
    const entries = board.supply.map((s) => [s.display_name, s.deficit]);
    const scale = Math.max(1, ...entries.map(([, v]) => Math.abs(v)));

    entries.forEach(([name, value]) => {
      const li = el("li");
      li.appendChild(el("span", null, name));
      const track = el("div", "track");
      const fill = el("div", `fill ${value >= 0 ? "pos" : "neg"}`);
      fill.style.width = `${(Math.abs(value) / scale) * 50}%`;
      track.appendChild(fill);
      track.appendChild(el("div", "mid"));
      li.appendChild(track);
      li.appendChild(el("span", "v", signed(value, 1)));
      heat.appendChild(li);
    });

    const punts = $("punts");
    punts.innerHTML = "";
    board.punt_options.slice(0, 6).forEach((option) => {
      const li = el("li");
      if (board.punt && option.label === board.punt.label) li.classList.add("is-best");
      li.appendChild(el("span", null, option.label));
      li.appendChild(
        el("span", "delta", `${fmt(option.category_wins, 1)} wins (${signed(option.gain)})`)
      );
      punts.appendChild(li);
    });

    const roster = $("roster");
    roster.innerHTML = "";
    if (!board.my_roster.length) {
      roster.appendChild(el("li", "row", "No picks yet."));
    }
    board.my_roster.forEach((entry) => {
      const li = el("li", "row");
      const who = el("div", "who");
      who.appendChild(el("div", "n", entry.name));
      const bits = [
        entry.positions.filter((p) => !["Util", "G", "F"].includes(p)).join("/"),
        entry.nba_team,
        entry.injury,
      ].filter(Boolean);
      who.appendChild(el("div", "meta2", bits.join(" · ")));
      li.appendChild(who);
      roster.appendChild(li);
    });
  };

  const renderGaps = (board) => {
    const node = $("gaps");
    node.innerHTML = "";
    const entries = Object.entries(board.positional_gaps || {});
    if (!entries.length) {
      node.textContent = "Every active slot is filled.";
      return;
    }
    node.appendChild(el("span", null, "Still need: "));
    entries.forEach(([position, count]) => {
      node.appendChild(el("span", "gap", count > 1 ? `${position} x${count}` : position));
    });
  };

  const render = (state) => {
    const status = $("status");
    const banner = $("banner");
    const board = state.board;

    status.className = "status";
    status.textContent = state.status?.message || "";
    if (state.status?.status === "live") status.classList.add("is-live");
    if (state.error || state.status?.status === "backend-unreachable") {
      status.classList.add("is-error");
    }

    const problems = [];
    if (state.error) problems.push(state.error);
    if (board?.warnings?.length) problems.push(...board.warnings);
    if (problems.length) {
      banner.hidden = false;
      banner.textContent = problems[0];
    } else {
      banner.hidden = true;
    }

    if (!board) return;

    const clock = $("clock");
    if (board.seconds_remaining !== null && board.seconds_remaining !== undefined) {
      clock.hidden = false;
      clock.textContent = `0:${String(board.seconds_remaining).padStart(2, "0")}`;
      clock.classList.toggle("is-urgent", board.seconds_remaining <= 10);
    } else {
      clock.hidden = true;
    }

    renderTurn(board);
    renderHeadline(board);

    const alts = $("alternatives");
    alts.innerHTML = "";
    board.alternatives.forEach((rec) => alts.appendChild(playerRow(rec)));

    const build = $("build");
    build.innerHTML = "";
    if (board.punt) {
      build.innerHTML =
        `Build: <b>${board.punt.label}</b> · ` +
        `${fmt(board.projected_category_wins, 1)} projected category wins`;
    }

    renderSupply(board);
    renderTeam(board);
    renderGaps(board);

    const list = $("board");
    list.innerHTML = "";
    board.board.forEach((rec) => list.appendChild(playerRow(rec, false)));

    $("meta").textContent = `${board.players_seen}p · ${board.compute_ms}ms`;
  };

  // ---- wiring --------------------------------------------------------

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "BOARD_UPDATED") render(message);
  });

  chrome.runtime.sendMessage({ type: "GET_BOARD" }, (state) => {
    if (state) render(state);
  });

  $("clear-manual").addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "CLEAR_MANUAL_PICKS" });
  });

  const backend = $("backend");
  chrome.storage.local.get("backendUrl").then((stored) => {
    backend.value = stored.backendUrl || "http://localhost:8000";
  });
  backend.addEventListener("change", () => {
    chrome.runtime.sendMessage({ type: "SET_BACKEND_URL", url: backend.value.trim() });
  });
})();
