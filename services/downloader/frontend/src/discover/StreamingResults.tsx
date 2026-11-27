import { useEffect, useState } from "react";

import MediaCard from "./MediaCard";
import StreamingMonitor from "./StreamingMonitor";

import type {
  MediaType,
  MediaItem,
  ProviderResponse,
  StreamingStatus,
  StreamingResponse,
} from "./types";

const PAGE_SIZE = 24;

async function request<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(
    `/api/discover/streaming/${path}`,
    { signal }
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

export default function StreamingResults({
  mediaType,
  providerId,
  providers,
  days,
  rating,
  genreIds,
  sort,
  hideOwned,
  libraryKeys,
  onSearch,
}: {
  mediaType: MediaType;
  providerId: number;
  providers: ProviderResponse | null;
  days: number;
  rating: number;
  genreIds: {
    movie: number[];
    tv: number[];
  } | null;
  sort: string;
  hideOwned: boolean;
  libraryKeys: Set<string> | null;
  onSearch: (item: MediaItem) => void;
}) {
  const [status, setStatus] =
    useState<StreamingStatus | null>(null);

  const [statusError, setStatusError] = useState("");

  const [items, setItems] = useState<MediaItem[]>([]);

  const [result, setResult] =
    useState<StreamingResponse | null>(null);

  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [metadataError, setMetadataError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    setStatusError("");

    request<StreamingStatus>("status", controller.signal)
      .then(data => {
        if (!controller.signal.aborted) {
          setStatus(data);
        }
      })
      .catch(err => {
        if (!controller.signal.aborted) {
          setStatusError(err.message);
        }
      });

    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    const controller = new AbortController();

    setLoading(true);
    setError("");

    const params = new URLSearchParams({
      media_type: mediaType,
      provider_id: String(providerId),
      days: String(days),
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });

    request<StreamingResponse>(
      `additions?${params}`,
      controller.signal,
    )
      .then(data => {
        if (controller.signal.aborted) return;

        setResult(data);

        setMetadataError(previous =>
          offset === 0
            ? data.errors.length > 0
            : previous || data.errors.length > 0
        );

        setItems(previous => {
          const merged = new Map<string, MediaItem>();

          if (offset > 0) {
            previous.forEach(item =>
              merged.set(item.key, item)
            );
          }

          data.items.forEach(item =>
            merged.set(item.key, item)
          );

          return Array.from(merged.values());
        });
      })
      .catch(err => {
        if (!controller.signal.aborted) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [mediaType, providerId, days, offset, retry]);

  const visibleItems = items.filter(item => {

    if (
      genreIds &&
      !genreIds[item.media_type].some(
        id => item.genre_ids?.includes(id)
      )
    ) return false;

    if (
      rating > 0 &&
      (item.tmdb_rating == null ||
        item.tmdb_rating < rating)
    ) return false;

    return !(
      hideOwned &&
      item.media_type === "movie" &&
      libraryKeys?.has(item.key)
    );
  });

  visibleItems.sort((a, b) => {
    if (sort === "rating") {
      return (b.tmdb_rating ?? 0) - (a.tmdb_rating ?? 0);
    }

    if (sort === "popular") {
      return b.popularity - a.popularity;
    }

    return (b.detected_at ?? "")
      .localeCompare(a.detected_at ?? "");
  });

  return (
    <>
      <StreamingMonitor
        status={status}
        providers={providers}
        additions={result?.total ?? null}
        error={statusError}
      />

      <div className="discover-results-heading">
        <h2>04 / NEW ON STREAMING</h2>
        <span>
          {loading ? "LOADING..." :
            `${visibleItems.length} VISIBLE / ${result?.total ?? 0} ADDITIONS`}
        </span>
      </div>

      {(error || statusError) && (
        <div className="discover-error">
          {error || statusError}
          <button
            type="button"
            onClick={() => setRetry(v => v + 1)}
          >
            RETRY
          </button>
        </div>
      )}

      {metadataError && (
        <div className="discover-warning">
          SOME TITLE METADATA IS TEMPORARILY UNAVAILABLE
        </div>
      )}

      {loading && !items.length && (
        <div className="discover-message">
          LOADING STREAMING ADDITIONS...
        </div>
      )}

      {!loading && !error && result?.total === 0 && (
        <div className="streaming-empty">
          <strong>
            {status?.baseline_complete
              ? "AWAITING CATALOG CHANGES"
              : "BUILDING CATALOG BASELINE"}
          </strong>

          <span>No confirmed streaming additions yet.</span>
        </div>
      )}

      {!loading && items.length > 0 &&
        visibleItems.length === 0 && (
          <div className="discover-message">
            NO LOADED TITLES MATCH THE FILTERS.
          </div>
        )}

      <div className="discover-media-grid">
        {visibleItems.map(item => (
          <MediaCard
            key={item.key}
            item={item}
            onSelect={onSearch}
            libraryMatch={
              libraryKeys
                ? libraryKeys.has(item.key)
                : null
            }
          />
        ))}
      </div>

      {result?.has_more && (
        <div className="discover-pagination">
          <button
            type="button"
            className="discover-load-more"
            disabled={loading || !!error}
            onClick={() => {
              setLoading(true);
              setOffset(result.offset + result.limit);
            }}
          >
            {loading ? "LOADING..." : "+ LOAD MORE"}
          </button>

          <span className="discover-pagination-info">
            {items.length} / {result.total} ADDITIONS LOADED
          </span>
        </div>
      )}
    </>
  );
}
