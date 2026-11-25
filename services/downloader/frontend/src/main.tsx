import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Result = {
  id: string;
  filename: string;
  resolution: string;
  size: number;
  duration: string;
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
};

type Storage = {
  total: number;
  used: number;
  free: number;
};

function formatSize(bytes: number) {
  return `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
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
  const [adding, setAdding] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

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
    void refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
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

  async function download(file: Result) {
    setError("");
    setAdding(file.id);

    try {
      await api("downloads", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: searchedQuery,
          file_id: file.id,
        }),
      });

      await refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setAdding(null);
    }
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

        <span className={connected ? "online" : "offline"}>
          {connected ? "● Backend online" : "● Backend offline"}
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
              ? `${(storage.free / 1024 ** 4).toFixed(2)} TiB`
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
          />

          <button disabled={loading}>
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        <div className="filters">
          {["All", "2160p", "1080p", "720p"].map((r) => (
            <button
              key={r}
              className={resolution === r ? "selected" : ""}
              onClick={() => setResolution(r)}
            >
              {r}
            </button>
          ))}
        </div>

        {error && <p className="error">{error}</p>}

        {filteredResults.map((file) => {
          const exists = downloads.some(
            (d) => d.source_id === file.id
          );

          return (
            <article key={file.id}>
              <div>
                <strong>{file.filename}</strong>
                <p>
                  {file.resolution || "Unknown resolution"} ·{" "}
                  {formatSize(file.size)} · {file.duration}
                </p>
              </div>

              <button
                disabled={exists || adding !== null}
                onClick={() => download(file)}
              >
                {exists
                  ? "Added"
                  : adding === file.id
                    ? "Adding..."
                    : "↓ Download"}
              </button>
            </article>
          );
        })}

        {searchedQuery && filteredResults.length === 0 && (
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
              <span className={`status ${job.status}`}>
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

              <small>{job.progress.toFixed(1)} %</small>
            </div>

            {job.error && (
              <p className="error">{job.error}</p>
            )}
          </div>
        ))}
      </section>

      <footer>Dinosaur NAS · Downloader v0.1.0</footer>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <App />
);