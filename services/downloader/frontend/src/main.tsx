import { useRef as useTransferRef } from "react";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import dinosaurLogo from "./dinosaur.svg";

type Library = "movies" | "series" | "downloads";

type Result = {
  id: string;
  filename: string;
  resolution: string;
  size: number;
  duration: string;
  thumbnail: string | null;
};

type Download = {
  id: string;
  source_id: string;
  filename: string;
  size: number;
  downloaded: number;
  progress: number;
  status: string;
  error: string | null;
  destination: string | null;
  import_status: string;
  import_error: string | null;
};

type Storage = {
  total: number;
  used: number;
  free: number;
};

type Selection = {
  mode: "download" | "import";
  id: string;
  filename: string;
  query?: string;
};

function formatSize(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
}

type TransferFilter =
  "all" | "active" | "queued" | "completed" | "failed";

type TransferSample = {
  at: number;
  rate: number | null;
};

type TransferTelemetry = {
  rates: Record<string, number>;
  total: number | null;
  samples: TransferSample[];
};

function formatRate(rate: number | undefined | null) {
  if (rate == null) return "—";

  if (rate < 1024 * 1024) {
    return `${(rate / 1024).toFixed(1)} KiB/s`;
  }

  return `${(rate / 1024 ** 2).toFixed(2)} MiB/s`;
}

function formatETA(remaining: number, rate?: number) {
  if (!rate || rate <= 0) return "—";

  const seconds = Math.ceil(Math.max(0, remaining) / rate);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;

  return hours > 0
    ? `${hours}h ${minutes}m`
    : `${minutes}m ${String(rest).padStart(2, "0")}s`;
}

function canRemoveTransfer(job: Download) {
  return (
    ["failed", "interrupted"].includes(job.status) ||
    (
      job.status === "completed" &&
      ["imported", "not_requested"].includes(job.import_status)
    )
  );
}

function canClearTransfer(job: Download) {
  return canRemoveTransfer(job) &&
    (
      job.status !== "completed" ||
      job.import_status === "imported"
    );
}

function transferCategory(job: Download): TransferFilter {
  if (
    ["failed", "interrupted", "cancelled", "canceled"]
      .includes(job.status) ||
    ["failed", "error"].includes(job.import_status)
  ) {
    return "failed";
  }

  if (job.status === "running") return "active";
  if (job.status === "queued") return "queued";
  if (job.status === "completed") return "completed";

  return "all";
}

function ThroughputGraph({
  samples
}: {
  samples: TransferSample[]
}) {
  const end = samples.length
    ? samples[samples.length - 1].at
    : 0;

  const maximum = Math.max(
    1024 ** 2,
    ...samples.map(sample => sample.rate ?? 0)
  );

  let drawing = false;

  const line = samples.map(sample => {
    if (sample.rate === null) {
      drawing = false;
      return "";
    }

    const x = 320 - (end - sample.at) / 60000 * 320;
    const y = 60 - sample.rate / maximum * 54;
    const command = drawing ? "L" : "M";

    drawing = true;

    return `${command}${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");

  return (
    <div className="throughput-graph">
      <div className="graph-heading">
        <small>LIVE THROUGHPUT / 60 SEC</small>
        <small>MAX {formatRate(maximum)}</small>
      </div>

      <svg
        viewBox="0 0 320 64"
        preserveAspectRatio="none"
        role="img"
        aria-label="Transfer speed over the last 60 seconds"
      >
        {[6, 24, 42, 60].map(y => (
          <line
            key={y}
            x1="0"
            x2="320"
            y1={y}
            y2={y}
            stroke="#263326"
            strokeWidth="0.5"
          />
        ))}

        <path
          d={line}
          fill="none"
          stroke="#a3e635"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <div className="graph-heading">
        <small>-60s</small>
        <small>NOW</small>
      </div>
    </div>
  );
}

function fileTitle(filename: string) {
  return filename.replace(/\.[^.]+$/, "");
}

function safeThumbnail(url: string | null) {
  if (!url) return undefined;

  try {
    const parsed = new URL(url);

    if (
      parsed.protocol === "https:" &&
      parsed.host === "img.fastshare.cloud"
    ) {
      return parsed.href;
    }
  } catch {
    return undefined;
  }

  return undefined;
}

async function api<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`/api/${path}`, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `HTTP ${response.status}`
    );
  }

  return data;
}


function publicError(message: string) {
  if (/fast[\s._-]*share|https?:\/\//i.test(message)) {
    return "Remote service request failed. Please try again.";
  }

  return message;
}

function App() {
  const [query, setQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchMessage, setBatchMessage] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [downloads, setDownloads] = useState<Download[]>([]);

  const [transferFilter, setTransferFilter] =
    useState<TransferFilter>("all");

  const [telemetry, setTelemetry] = useState<TransferTelemetry>({
    rates: {},
    total: null,
    samples: [],
  });

  const previousTransfer = useTransferRef<{
    at: number;
    jobs: Download[];
  } | null>(null);

  const refreshSequence = useTransferRef(0);
  const searchGeneration = useTransferRef(0);

  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [storage, setStorage] = useState<Storage | null>(null);

  const [resolution, setResolution] = useState("All");
  const [sortOrder, setSortOrder] = useState<
    "default" | "size-desc" | "size-asc"
  >("default");
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

  const [selection, setSelection] =
    useState<Selection | null>(null);

  const [library, setLibrary] =
    useState<Library>("movies");

  const [title, setTitle] = useState("");
  const [season, setSeason] = useState(1);
  const [episode, setEpisode] = useState(1);

  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState("");

  function updateTelemetry(jobs: Download[]) {
    const now = performance.now();
    const previous = previousTransfer.current;

    if (previous && now - previous.at < 1000) return;

    previousTransfer.current = { at: now, jobs };

    const rates: Record<string, number> = {};
    const active = jobs.filter(job => job.status === "running");

    const elapsed = previous
      ? (now - previous.at) / 1000
      : 0;

    if (previous && elapsed > 0 && elapsed <= 15) {
      for (const job of active) {
        const old = previous.jobs.find(item => item.id === job.id);

        if (!old) continue;

        const delta = job.downloaded - old.downloaded;

        if (delta < 0) continue;

        rates[job.id] = delta / elapsed;
      }
    }

    const total = active.length === 0
      ? 0
      : active.every(job => rates[job.id] !== undefined)
        ? active.reduce((sum, job) => sum + rates[job.id], 0)
        : null;

    setTelemetry(current => ({
      rates,
      total,
      samples: [
        ...current.samples.filter(
          sample => now - sample.at <= 60000
        ),
        { at: now, rate: total }
      ],
    }));
  }

  async function refresh() {
    const sequence = ++refreshSequence.current;

    try {
      const [jobs, disk] = await Promise.all([
        api<Download[]>("downloads"),
        api<Storage>("storage"),
      ]);

      if (sequence !== refreshSequence.current) return;

      updateTelemetry(jobs);
      setDownloads(jobs);
      setStorage(disk);
      setConnected(true);
    } catch {
      if (sequence !== refreshSequence.current) return;

      previousTransfer.current = null;

      setTelemetry({
        rates: {},
        total: null,
        samples: [],
      });

      setConnected(false);
    }
  }

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      await refresh();

      if (!stopped) {
        timer = setTimeout(poll, 2000);
      }
    }

    void poll();

    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);

  async function search(event: React.FormEvent) {
    event.preventDefault();

    const term = query.trim();

    if (term.length < 2 || batchBusy || loading) return;

    const generation = ++searchGeneration.current;

    setLoading(true);
    setError("");

    try {
      const data = await api<{ results: Result[] }>(
        `search?query=${encodeURIComponent(term)}`
      );

      if (generation !== searchGeneration.current) return;

      setResults(data.results);
      setSelectedIds([]);
      setBatchMessage("");
      setSearchedQuery(term);
    } catch (err) {
      if (generation === searchGeneration.current) {
        setError(String(err));
      }
    } finally {
      if (generation === searchGeneration.current) {
        setLoading(false);
      }
    }
  }

  function toggleFile(id: string) {
    setSelectedIds(previous =>
      previous.includes(id)
        ? previous.filter(item => item !== id)
        : [...previous, id]
    );
  }

  async function queueSelected() {
    if (batchBusy || loading || !connected) return;

    const files = results.filter(file =>
      selectedIds.includes(file.id) &&
      !downloads.some(job => job.source_id === file.id)
    );

    if (!files.length) return;

    const generation = searchGeneration.current;

    setBatchBusy(true);
    setBatchMessage("");
    setError("");

    let queued = 0;
    const failed: string[] = [];

    try {
      for (const file of files) {
        try {
          await api("downloads", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              query: searchedQuery,
              file_id: file.id,
              library: "downloads",
              title: null,
              season: null,
              episode: null,
            }),
          });

          queued++;

          setSelectedIds(previous =>
            previous.filter(id => id !== file.id)
          );
        } catch (err) {
          failed.push(
            `${file.filename}: ${publicError(String(err))}`
          );
        }
      }

      if (generation === searchGeneration.current) {
        setBatchMessage(`${queued} / ${files.length} files queued`);

        if (failed.length) {
          setError(failed.join("\n"));
        }
      }

      await refresh();
    } finally {
      setBatchBusy(false);
    }
  }

  function openDownload(file: Result) {
    setSelection({
      mode: "download",
      id: file.id,
      filename: file.filename,
      query: searchedQuery,
    });

    setLibrary("movies");
    setTitle(fileTitle(file.filename));
    setSeason(1);
    setEpisode(1);
    setDialogError("");
  }

  function openImport(job: Download) {
    setSelection({
      mode: "import",
      id: job.id,
      filename: job.filename,
    });

    setLibrary("movies");
    setTitle(fileTitle(job.filename));
    setSeason(1);
    setEpisode(1);
    setDialogError("");
  }

  async function submitSelection(
    event: React.FormEvent
  ) {
    event.preventDefault();

    if (!selection || submitting) return;

    if (
      library !== "downloads" &&
      !title.trim()
    ) {
      setDialogError("Media title is required");
      return;
    }

    setSubmitting(true);
    setDialogError("");

    const importOptions = {
      library,
      title:
        library === "downloads"
          ? null
          : title.trim(),
      season:
        library === "series" ? season : null,
      episode:
        library === "series" ? episode : null,
    };

    try {
      if (selection.mode === "download") {
        await api("downloads", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            query: selection.query,
            file_id: selection.id,
            ...importOptions,
          }),
        });
      } else {
        await api(
          `downloads/${selection.id}/import`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(importOptions),
          }
        );
      }

      setSelection(null);
      await refresh();
    } catch (err) {
      setDialogError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  function destinationPreview() {
    if (!selection) return "";

    const extension =
      selection.filename.match(/\.[^.]+$/)?.[0]
        ?.toLowerCase() || "";

    if (library === "movies") {
      return `/media/movies/${title}/${title}${extension}`;
    }

    if (library === "series") {
      const s = String(season).padStart(2, "0");
      const e = String(episode).padStart(2, "0");

      return (
        `/media/series/${title}/Season ${s}/` +
        `${title} S${s}E${e}${extension}`
      );
    }

    return (
      `/media/downloads/<job-id>/` +
      selection.filename
    );
  }

  const filteredResults = results
    .filter(
      (file) =>
        resolution === "All" ||
        file.resolution === resolution
    )
    .sort((a, b) => {
      if (sortOrder === "size-desc") {
        return b.size - a.size;
      }

      if (sortOrder === "size-asc") {
        return a.size - b.size;
      }

      return 0;
    });

  const selectedCount = selectedIds.filter(id =>
    !downloads.some(job => job.source_id === id)
  ).length;

  async function removeTransfer(job: Download) {
    if (historyBusy || !canRemoveTransfer(job)) return;

    const warning = job.import_status === "not_requested" &&
      job.status === "completed"
      ? "\\nManual import from Downloader will no longer be available."
      : "";

    if (!window.confirm(
      `Remove ${job.filename} from history?\\n` +
      "Files on NAS will not be deleted." + warning
    )) return;

    setHistoryBusy(true);
    setHistoryError("");

    try {
      await api(`downloads/${encodeURIComponent(job.id)}`, {
        method: "DELETE",
      });

      await refresh();
    } catch (err) {
      setHistoryError(String(err));
    } finally {
      setHistoryBusy(false);
    }
  }

  async function clearHistory() {
    if (historyBusy) return;

    if (!window.confirm(
      "Clear imported and failed transfers from history?\\n" +
      "Files on NAS will not be deleted."
    )) return;

    setHistoryBusy(true);
    setHistoryError("");

    try {
      await api("downloads/history", {
        method: "DELETE",
      });

      await refresh();
    } catch (err) {
      setHistoryError(String(err));
    } finally {
      setHistoryBusy(false);
    }
  }

  const clearableCount = downloads.filter(
    canClearTransfer
  ).length;

  const transferCounts: Record<TransferFilter, number> = {
    all: downloads.length,
    active: downloads.filter(
      job => transferCategory(job) === "active"
    ).length,
    queued: downloads.filter(
      job => transferCategory(job) === "queued"
    ).length,
    completed: downloads.filter(
      job => transferCategory(job) === "completed"
    ).length,
    failed: downloads.filter(
      job => transferCategory(job) === "failed"
    ).length,
  };

  const transferTabs: TransferFilter[] = [
    "all", "active", "queued", "completed", "failed"
  ];

  const visibleDownloads = downloads
    .filter(job =>
      transferFilter === "all" ||
      transferCategory(job) === transferFilter
    )
    .sort((a, b) => {
      const order: TransferFilter[] = [
        "active", "queued", "failed", "completed", "all"
      ];

      return order.indexOf(transferCategory(a)) -
        order.indexOf(transferCategory(b));
    });

  function goHome() {
    searchGeneration.current++;

    setQuery("");
    setSearchedQuery("");
    setResults([]);
    setSelectedIds([]);
    setBatchMessage("");
    setResolution("All");
    setSortOrder("default");
    setError("");
    setLoading(false);

    scrollToSection("file-search");
  }

  function scrollToSection(id: string) {
    const section = document.getElementById(id);

    section?.focus({ preventScroll: true });

    section?.scrollIntoView({
      behavior: window.matchMedia(
        "(prefers-reduced-motion: reduce)"
      ).matches ? "auto" : "smooth",
      block: "start",
    });
  }

  function openTransfers(filter: TransferFilter) {
    setTransferFilter(filter);
    scrollToSection("transfer-monitor");
  }

  return (
    <main>
      <header>
        <div>
          <h1 className="brand">
            <button
              type="button"
              className="dino-home"
              title="Home"
              aria-label="Go to file search"
              onClick={goHome}
            >
              <img
                src={dinosaurLogo}
                alt=""
                className="dinosaur-logo"
              />
            </button>
            <span>DINOSAUR DOWNLOADER</span>
          </h1>
          <p>FILE TRANSFER SYSTEM // Dinosaur - NAS</p>
        </div>

        <span
          className={connected ? "online" : "offline"}
        >
          {connected
            ? "● SYSTEM ONLINE"
            : "● SYSTEM OFFLINE"}
        </span>
      </header>

      <div className="stats">
        <section className="quick-nav-card">
          <button
            type="button"
            className="quick-nav-button"
            aria-label="Active downloads: open transfer monitor"
            onClick={() => openTransfers("active")}
          />
          <small>Active downloads</small>
          <h2>
            {downloads.filter(
              (d) => d.status === "running"
            ).length}
          </h2>
        </section>

        <section className="quick-nav-card">
          <button
            type="button"
            className="quick-nav-button"
            aria-label="Queued: open transfer monitor"
            onClick={() => openTransfers("queued")}
          />
          <small>Queued</small>
          <h2>
            {downloads.filter(
              (d) => d.status === "queued"
            ).length}
          </h2>
        </section>

        <section className="quick-nav-card">
          <button
            type="button"
            className="quick-nav-button"
            aria-label="Available storage: open transfer monitor"
            onClick={() => openTransfers("all")}
          />
          <small>Available storage</small>
          <h2>
            {storage
              ? `${(
                  storage.free / 1024 ** 4
                ).toFixed(2)} TiB`
              : "—"}
          </h2>
        </section>
      </div>

      <section
        className="panel"
        id="file-search"
        tabIndex={-1}
      >
        <h2>NAS / Movie Search</h2>

        <form onSubmit={search}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search files..."
            maxLength={200}
          />

          <button disabled={loading || batchBusy || !connected}>
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        <div className="filters">
          {["All", "2160p", "1080p", "720p"].map(
            (r) => (
              <button
                key={r}
                className={
                  resolution === r ? "selected" : ""
                }
                onClick={() => setResolution(r)}
              >
                {r}
              </button>
            )
          )}
        </div>

        {results.length > 0 && (
          <div className="sort-toolbar">
            <label htmlFor="result-sort">SORT BY</label>

            <select
              id="result-sort"
              value={sortOrder}
              onChange={(event) =>
                setSortOrder(
                  event.target.value as typeof sortOrder
                )
              }
            >
              <option value="default">Default order</option>
              <option value="size-desc">Size: largest first</option>
              <option value="size-asc">Size: smallest first</option>
            </select>
          </div>
        )}

        {results.length > 0 && (
          <div className="batch-toolbar">
            <span className="selection-counter">
              {selectedCount} FILES SELECTED
            </span>

            <button
              type="button"
              className="secondary-button"
              disabled={batchBusy || loading}
              onClick={() => setSelectedIds(previous =>
                Array.from(new Set([
                  ...previous,
                  ...filteredResults
                    .filter(file =>
                      !downloads.some(job => job.source_id === file.id)
                    )
                    .map(file => file.id)
                ]))
              )}
            >
              Select visible
            </button>

            <button
              type="button"
              className="secondary-button"
              disabled={batchBusy}
              onClick={() => setSelectedIds([])}
            >
              Clear
            </button>

            <button
              type="button"
              disabled={
                batchBusy || loading ||
                !connected || selectedCount === 0
              }
              onClick={queueSelected}
            >
              {batchBusy
                ? "Queuing..."
                : `↓ Queue selected (${selectedCount})`}
            </button>
          </div>
        )}

        {batchMessage && (
          <p className="success-text" role="status">
            {batchMessage}
          </p>
        )}

        {error && (
          <p className="error batch-error">
            {publicError(error)}
          </p>
        )}

        {filteredResults.map((file) => {
          const exists = downloads.some(
            (d) => d.source_id === file.id
          );

          const thumbnail =
            safeThumbnail(file.thumbnail);

          return (
            <article
              key={file.id}
              className={
                !exists && selectedIds.includes(file.id)
                  ? "result-selected"
                  : ""
              }
            >
              <div className="result-info">
                <label className="file-select">
                  <input
                    type="checkbox"
                    className="file-checkbox"
                    aria-label={`Select ${file.filename}`}
                    checked={
                      !exists && selectedIds.includes(file.id)
                    }
                    disabled={
                      exists || batchBusy ||
                      loading || !connected
                    }
                    onChange={() => toggleFile(file.id)}
                  />
                </label>
                {thumbnail && (
                  <img
                    className="thumbnail"
                    src={thumbnail}
                    alt=""
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    onError={(e) => {
                      e.currentTarget.style.display =
                        "none";
                    }}
                  />
                )}

                <div>
                  <strong>{file.filename}</strong>

                  <p>
                    {file.resolution || "Unknown"} ·{" "}
                    {formatSize(file.size)} ·{" "}
                    {file.duration}
                  </p>
                </div>
              </div>

              <button
                disabled={exists || batchBusy || loading || !connected}
                onClick={() => openDownload(file)}
              >
                {exists ? "Added" : "↓ Download"}
              </button>
            </article>
          );
        })}

        {searchedQuery &&
          filteredResults.length === 0 && (
            <p>No matching results.</p>
          )}
      </section>

      <section
        className="panel transfer-monitor"
        id="transfer-monitor"
        tabIndex={-1}
      >
        <div className="transfer-heading">
          <h2>02 / TRANSFER MONITOR</h2>
          <div className="transfer-throughput">
            {connected && transferCounts.active > 0 && (
              <div className="transfer-dino-track" aria-hidden="true">
                <img src={dinosaurLogo} alt="" />
              </div>
            )}

            <span>
              ↓ {formatRate(telemetry.total)}
            </span>
          </div>
        </div>

        <ThroughputGraph samples={telemetry.samples} />

        <div
          className="transfer-tabs"
          aria-label="Filter transfers"
        >
          {transferTabs.map(tab => (
            <button
              key={tab}
              type="button"
              className={transferFilter === tab ? "selected" : ""}
              aria-pressed={transferFilter === tab}
              onClick={() => setTransferFilter(tab)}
            >
              {tab} ({transferCounts[tab]})
            </button>
          ))}
        </div>

        <div className="history-actions">
          <button
            type="button"
            className="clear-history"
            disabled={
              !connected ||
              historyBusy ||
              clearableCount === 0
            }
            onClick={clearHistory}
          >
            Clear history ({clearableCount})
          </button>
        </div>

        {historyError && (
          <p className="error">
            {publicError(historyError)}
          </p>
        )}

        {visibleDownloads.length === 0 && (
          <p className="transfer-empty">
            No matching transfers.
          </p>
        )}

        <div
          className="transfer-list"
          role="region"
          aria-label="Transfer history"
          tabIndex={0}
        >
        {visibleDownloads.map((job) => (
          <div className="download" key={job.id}>
            <div className="download-header">
              <strong>{job.filename}</strong>

              <div className="transfer-status-actions">
                <span className={`status ${job.status}`}>
                  {job.status}
                </span>

                {canRemoveTransfer(job) && (
                  <button
                    type="button"
                    className="remove-transfer"
                    title="Remove from history"
                    aria-label={`Remove ${job.filename} from history`}
                    disabled={!connected || historyBusy}
                    onClick={() => removeTransfer(job)}
                  >
                    ×
                  </button>
                )}
              </div>
            </div>

            <progress
              value={Math.min(100, job.progress)}
              max={100}
            />

            <div className="transfer-meta">
              <small>
                {job.status === "completed"
                  ? formatSize(job.size)
                  : `${formatSize(job.downloaded)} / ${formatSize(job.size)}`}
                {" · "}
                {Math.min(100, job.progress).toFixed(1)}%
              </small>

              {job.status === "completed" &&
               job.import_status !== "not_requested" && (
                <span className={`status ${job.import_status}`}>
                  {job.import_status === "imported"
                    ? "✓ Jellyfin imported"
                    : `Import: ${job.import_status.replace(/_/g, " ")}`}
                </span>
              )}
            </div>

            {job.status === "running" && (
              <div className="transfer-live">
                <span>
                  ↓ {formatRate(telemetry.rates[job.id])}
                </span>
                <span>
                  ETA {formatETA(
                    job.size - job.downloaded,
                    telemetry.rates[job.id]
                  )}
                </span>
              </div>
            )}

            {job.status === "completed" &&
              job.import_status === "not_requested" && (
                <button
                  className="import-button"
                  disabled={!connected}
                  onClick={() => openImport(job)}
                >
                  Import to Jellyfin
                </button>
              )}

            {job.error && (
              <p className="error">{publicError(job.error)}</p>
            )}

            {job.import_error && (
              <p className="error">
                Import error: {publicError(job.import_error)}
              </p>
            )}
          </div>
        ))}
        </div>
      </section>

      {selection && (
        <div className="modal-overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onKeyDown={(e) => {
              if (e.key === "Escape" && !submitting) {
                setSelection(null);
              }
            }}
          >
            <div className="modal-header">
              <h2 id="modal-title">
                {selection.mode === "download"
                  ? "Add download"
                  : "Import to Jellyfin"}
              </h2>

              <button
                className="secondary-button"
                disabled={submitting}
                onClick={() => setSelection(null)}
              >
                ✕
              </button>
            </div>

            <div className="selected-file">
              {selection.filename}
            </div>

            <form
              className="modal-form"
              onSubmit={submitSelection}
            >
              <label>Destination library</label>

              <div className="library-options">
                <button
                  type="button"
                  className={
                    library === "movies"
                      ? "selected"
                      : ""
                  }
                  onClick={() => setLibrary("movies")}
                >
                  Movies
                </button>

                <button
                  type="button"
                  className={
                    library === "series"
                      ? "selected"
                      : ""
                  }
                  onClick={() => setLibrary("series")}
                >
                  TV Shows
                </button>

                {selection.mode === "download" && (
                  <button
                    type="button"
                    className={
                      library === "downloads"
                        ? "selected"
                        : ""
                    }
                    onClick={() =>
                      setLibrary("downloads")
                    }
                  >
                    Downloads only
                  </button>
                )}
              </div>

              {library !== "downloads" && (
                <>
                  <label htmlFor="media-title">
                    {library === "movies"
                      ? "Movie title and year"
                      : "Series name"}
                  </label>

                  <input
                    id="media-title"
                    autoFocus
                    required
                    maxLength={180}
                    value={title}
                    onChange={(e) =>
                      setTitle(e.target.value)
                    }
                    placeholder={
                      library === "movies"
                        ? "Movie Title (2026)"
                        : "Series Name"
                    }
                  />
                </>
              )}

              {library === "series" && (
                <div className="episode-fields">
                  <div>
                    <label htmlFor="season">
                      Season
                    </label>
                    <input
                      id="season"
                      type="number"
                      min={0}
                      max={999}
                      required
                      value={season}
                      onChange={(e) =>
                        setSeason(Number(e.target.value))
                      }
                    />
                  </div>

                  <div>
                    <label htmlFor="episode">
                      Episode
                    </label>
                    <input
                      id="episode"
                      type="number"
                      min={1}
                      max={999}
                      required
                      value={episode}
                      onChange={(e) =>
                        setEpisode(Number(e.target.value))
                      }
                    />
                  </div>
                </div>
              )}

              <div className="destination-preview">
                <small>Destination preview</small>
                <div>{destinationPreview()}</div>
              </div>

              {library !== "downloads" && (
                <p className="success-text">
                  ✓ Automatically refresh Jellyfin
                </p>
              )}

              {dialogError && (
                <p className="error">{publicError(dialogError)}</p>
              )}

              <div className="modal-actions">
                <button
                  type="button"
                  className="secondary-button"
                  disabled={submitting}
                  onClick={() => setSelection(null)}
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={submitting || !connected}
                >
                  {submitting
                    ? "Processing..."
                    : selection.mode === "download"
                      ? "↓ Start download"
                      : "Import to Jellyfin"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      <footer>
        DINOSAUR NAS // TRANSFER SYSTEM // V0.5.4
      </footer>
    </main>
  );
}

createRoot(
  document.getElementById("root")!
).render(<App />);