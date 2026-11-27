import { useEffect, useState } from "react";

type SeasonStatus = {
  number: number;
  name: string;
  aired: number;
  available: number[];
  missing: number[];
  upcoming: number[];
  unknown: number[];
  complete: boolean;
};

type SeriesStatus = {
  matched: boolean;
  title?: string;
  seasons: SeasonStatus[];
};

export default function SeriesLibraryStatus({
  tmdbId,
  title,
  onEpisodeSearch,
  searchDisabled,
}: {
  tmdbId: number;
  title: string;
  onEpisodeSearch: (
    season: number,
    episode: number
  ) => void;
  searchDisabled: boolean;
}) {

  const [data, setData] =
    useState<SeriesStatus | null>(null);

  const [error, setError] = useState("");

  useEffect(() => {

    const controller = new AbortController();

    setData(null);
    setError("");

    async function load() {
      try {
        const response = await fetch(
          `/api/discover/library/series/${tmdbId}`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          throw new Error("Library status unavailable");
        }

        const result: SeriesStatus =
          await response.json();

        if (!controller.signal.aborted) {
          setData(result);
        }

      } catch {
        if (!controller.signal.aborted) {
          setError("LIBRARY STATUS UNAVAILABLE");
        }
      }
    }

    void load();

    return () => controller.abort();

  }, [tmdbId]);

  return (
    <section className="series-library-panel">

      <h2>SERIES LIBRARY STATUS</h2>

      <div className="series-library-title">
        {title.toUpperCase()}
      </div>

      {error && (
        <p className="series-unavailable">{error}</p>
      )}

      {!data && !error && (
        <p>CHECKING EPISODES...</p>
      )}

      {data && !data.matched && (
        <p className="series-unavailable">
          NO TMDB ID MATCH IN JELLYFIN
        </p>
      )}

      {data?.matched && data.seasons.map(season => {

        const episodes = [
          ...season.available.map(number => ({
            number, state: "available",
          })),
          ...season.missing.map(number => ({
            number, state: "missing",
          })),
          ...season.upcoming.map(number => ({
            number, state: "upcoming",
          })),
          ...season.unknown.map(number => ({
            number, state: "unknown",
          })),
        ].sort((a, b) => a.number - b.number);

        const percentage = season.aired
          ? season.available.length / season.aired * 100
          : 0;

        return (
          <details
            key={season.number}
            className="series-season"
          >
            <summary>
              <span>
                SEASON {String(season.number)
                  .padStart(2, "0")}
              </span>

              <span className={
                season.complete
                  ? "complete"
                  : "incomplete"
              }>
                {season.available.length} / {season.aired}
                {" "}EPISODES
              </span>
            </summary>

            <div className="series-progress">
              <div style={{ width: `${percentage}%` }} />
            </div>

            <div className="series-episode-grid">
              {episodes.map(ep => {
                const label =
                  `E${String(ep.number).padStart(2, "0")}`;

                const code =
                  `S${String(season.number).padStart(2, "0")}${label}`;

                if (ep.state === "missing") {
                  return (
                    <button
                      key={ep.number}
                      type="button"
                      className="series-episode missing searchable"
                      title={`Search ${title} ${code}`}
                      aria-label={`Search missing episode ${code}`}
                      disabled={searchDisabled}
                      onClick={() =>
                        onEpisodeSearch(
                          season.number,
                          ep.number
                        )
                      }
                    >
                      {label}
                    </button>
                  );
                }

                return (
                  <span
                    key={ep.number}
                    className={`series-episode ${ep.state}`}
                    title={ep.state.toUpperCase()}
                  >
                    {label}
                  </span>
                );
              })}
            </div>

            <div className="series-season-info">
              {season.complete
                ? "ALL AIRED EPISODES AVAILABLE"
                : `${season.missing.length} MISSING${
                    season.missing.length
                      ? " // CLICK EPISODE TO SEARCH"
                      : ""
                  }`}

              {season.upcoming.length > 0 &&
                ` / ${season.upcoming.length} UPCOMING`}

              {season.unknown.length > 0 &&
                ` / ${season.unknown.length} UNKNOWN`}
            </div>
          </details>
        );
      })}

      {data?.matched && (
        <div className="series-legend">
          <span className="available">■ AVAILABLE</span>
          <span className="missing">■ MISSING</span>
          <span className="upcoming">■ UPCOMING</span>
          <span className="unknown">■ UNKNOWN</span>
        </div>
      )}

    </section>
  );
}
