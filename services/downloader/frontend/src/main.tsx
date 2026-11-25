import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

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

function App() {
  const [query, setQuery] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [downloads, setDownloads] = useState<Download[]>([]);
  const [storage, setStorage] = useState<Storage | null>(null);

  const [resolution, setResolution] = useState("All");
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

  async function refresh() {
    try {
      const [jobs, disk] = await Promise.all([
        api<Download[]>("downloads"),
        api<Storage>("storage"),
      ]);

      setDownloads(jobs);
      setStorage(disk);
      setConnected(true);
    } catch {
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

    if (term.length < 2) return;

    setLoading(true);
    setError("");

    try {
      const data = await api<{ results: Result[] }>(
        `search?query=${encodeURIComponent(term)}`
      );

      setResults(data.results);
      setSearchedQuery(term);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
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

  const filteredResults = results.filter(
    (file) =>
      resolution === "All" ||
      file.resolution === resolution
  );

  return (
    <main>
      <header>
        <div>
          <h1>🦖 Dinosaur Downloader</h1>
          <p>FastShare · Dinosaur NAS</p>
        </div>

        <span
          className={connected ? "online" : "offline"}
        >
          {connected
            ? "● Backend online"
            : "● Backend offline"}
        </span>
      </header>

      <div className="stats">
        <section>
          <small>Active downloads</small>
          <h2>
            {downloads.filter(
              (d) => d.status === "running"
            ).length}
          </h2>
        </section>

        <section>
          <small>Queued</small>
          <h2>
            {downloads.filter(
              (d) => d.status === "queued"
            ).length}
          </h2>
        </section>

        <section>
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

      <section className="panel">
        <h2>Search FastShare</h2>

        <form onSubmit={search}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for a video..."
            maxLength={200}
          />

          <button disabled={loading || !connected}>
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

        {error && <p className="error">{error}</p>}

        {filteredResults.map((file) => {
          const exists = downloads.some(
            (d) => d.source_id === file.id
          );

          const thumbnail =
            safeThumbnail(file.thumbnail);

          return (
            <article key={file.id}>
              <div className="result-info">
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
                disabled={exists || !connected}
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

      <section className="panel">
        <h2>Download queue</h2>

        {downloads.length === 0 && (
          <p>No downloads yet.</p>
        )}

        {downloads.map((job) => (
          <div className="download" key={job.id}>
            <div className="download-header">
              <strong>{job.filename}</strong>

              <span
                className={`status ${job.status}`}
              >
                {job.status}
              </span>
            </div>

            <progress
              value={Math.min(100, job.progress)}
              max={100}
            />

            <div className="download-header">
              <small>
                {formatSize(job.downloaded)} /{" "}
                {formatSize(job.size)}
              </small>

              <small>
                {job.progress.toFixed(1)} %
              </small>
            </div>

            {job.destination && (
              <div className="destination-info">
                <small>Destination</small>
                <div>/media/{job.destination}</div>
              </div>
            )}

            {job.import_status !== "not_requested" && (
              <div className="import-info">
                <small>Jellyfin import</small>

                <span
                  className={`status ${job.import_status}`}
                >
                  {job.import_status.replace(/_/g, " ")}
                </span>
              </div>
            )}

            {job.import_status === "imported" && (
              <p className="success-text">
                ✓ Imported · Jellyfin scan requested
              </p>
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
              <p className="error">{job.error}</p>
            )}

            {job.import_error && (
              <p className="error">
                Import error: {job.import_error}
              </p>
            )}
          </div>
        ))}
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
                <p className="error">{dialogError}</p>
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
        Dinosaur NAS · Downloader v0.3.0
      </footer>
    </main>
  );
}

createRoot(
  document.getElementById("root")!
).render(<App />);