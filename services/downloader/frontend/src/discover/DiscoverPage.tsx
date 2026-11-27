import { useEffect, useMemo, useState } from "react";
import GenreFilter from "./GenreFilter";
import MediaCard from "./MediaCard";
import StreamingResults from "./StreamingResults";
import dinosaurLogo from "../dinosaur.svg";
import tmdbLogo from "./tmdb-logo.svg";

import type {
  MediaType,
  MediaItem,
  Platform,
  CatalogResponse,
  ProviderResponse,
  GenreOption,
  GenreResponse,
} from "./types";

import "./discover.css";

const CONTENT_TYPES: {
  value: MediaType;
  label: string;
  icon: string;
}[] = [
  { value: "all", label: "ALL", icon: "▦" },
  { value: "movie", label: "MOVIES", icon: "▤" },
  { value: "tv", label: "TV SERIES", icon: "▣" },
];

const DEFAULT_DAYS = 90;
const DEFAULT_RATING = 50;

const PROVIDER_ORDER = [
  8, 119, 337, 350, 1899, 1773
];

async function request<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(
    `/api/discover/${path}`,
    { signal }
  );

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

export default function DiscoverPage({
  onBack,
  onSearch,
}: {
  onBack: () => void;
  onSearch: (item: MediaItem) => void;
}) {

  const [mediaType, setMediaType] =
    useState<MediaType>("all");

  const [mode, setMode] =
    useState<"releases" | "streaming">("releases");

  const [providerId, setProviderId] = useState(0);
  const [days, setDays] = useState(DEFAULT_DAYS);
  const [rating, setRating] = useState(DEFAULT_RATING);
  const [sort, setSort] = useState("newest");
  const [pageLimit, setPageLimit] = useState(2);

  const [genreOptions, setGenreOptions] =
    useState<GenreOption[]>([]);

  const [selectedGenres, setSelectedGenres] =
    useState<string[]>([]);

  const [genreError, setGenreError] = useState("");

  const availableGenres = useMemo(
    () => genreOptions.filter(genre =>
      mediaType === "all" || genre[mediaType].length > 0
    ),
    [genreOptions, mediaType],
  );

  const streamingGenreIds = selectedGenres.length
    ? {
        movie: genreOptions
          .filter(g => selectedGenres.includes(g.id))
          .flatMap(g => g.movie),
        tv: genreOptions
          .filter(g => selectedGenres.includes(g.id))
          .flatMap(g => g.tv),
      }
    : null;

  function changeGenres(ids: string[]) {
    setPageLimit(2);
    setSelectedGenres([...ids].sort());
  }

  const filterKey = JSON.stringify([
    mediaType, providerId, days, rating, sort,
    selectedGenres,
  ]);

  const [providers, setProviders] =
    useState<ProviderResponse | null>(null);

  const [loadedCatalog, setLoadedCatalog] =
    useState<{
      key: string;
      data: CatalogResponse;
    } | null>(null);

  const catalog =
    loadedCatalog?.key === filterKey
      ? loadedCatalog.data
      : null;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [providerError, setProviderError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [hideOwned, setHideOwned] = useState(false);

  const [libraryKeys, setLibraryKeys] =
    useState<Set<string> | null>(null);

  const [libraryError, setLibraryError] =
    useState(false);

  useEffect(() => {
    const controller = new AbortController();

    setLibraryError(false);
    setLibraryKeys(null);

    request<{ keys: string[] }>(
      "library",
      controller.signal,
    )
      .then(data => {
        if (!controller.signal.aborted) {
          setLibraryKeys(new Set(data.keys));
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setLibraryError(true);
        }
      });

    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();

    setProviderError("");

    request<ProviderResponse>(
      "providers",
      controller.signal,
    )
      .then(setProviders)
      .catch(err => {
        if (!controller.signal.aborted) {
          setProviderError(err.message);
        }
      });

    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();

    setGenreError("");

    request<GenreResponse>("genres", controller.signal)
      .then(data => {
        if (!controller.signal.aborted) {
          setGenreOptions(data.genres);
        }
      })
      .catch(err => {
        if (!controller.signal.aborted) {
          setGenreError(err.message);
        }
      });

    return () => controller.abort();
  }, [refresh]);

  useEffect(() => {
    if (mode !== "releases") return;

    const controller = new AbortController();

    setLoading(true);
    setError("");

    const timer = window.setTimeout(async () => {
      try {
        const params = new URLSearchParams({
          media_type: mediaType,
          provider_id: String(providerId),
          days: String(days),
          min_rating: String(rating),
          min_votes: "5",
          genres: selectedGenres.join(","),
          page_limit: String(pageLimit),
          sort,
        });

        const data = await request<CatalogResponse>(
          `releases?${params}`,
          controller.signal,
        );

        if (!controller.signal.aborted) {
          setLoadedCatalog({
            key: filterKey,
            data,
          });
        }

      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : String(err)
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }, 450);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [
    mode,
    mediaType,
    providerId,
    days,
    rating,
    sort,
    pageLimit,
    selectedGenres,
    filterKey,
    refresh,
  ]);

  const platformMap = new Map<number, Platform>();

  const availableProviders =
    mediaType === "movie" ? providers?.movie :
    mediaType === "tv" ? providers?.tv :
    [...(providers?.movie ?? []),
     ...(providers?.tv ?? [])];

  for (const provider of availableProviders ?? []) {
    platformMap.set(provider.id, provider);
  }

  const platforms = PROVIDER_ORDER
    .map(id => platformMap.get(id))
    .filter((p): p is Platform => p !== undefined);

  const allItems = catalog?.items ?? [];

  const visibleItems = allItems.filter(item =>
    !(
      hideOwned &&
      libraryKeys?.has(item.key) &&
      item.media_type === "movie"
    )
  );

  const hiddenCount = allItems.length - visibleItems.length;

  function resetFilters() {
    setPageLimit(2);
    setHideOwned(false);
    setMediaType("all");
    setProviderId(0);
    setDays(DEFAULT_DAYS);
    setRating(DEFAULT_RATING);
    setSelectedGenres([]);
    setSort("newest");
  }

  return (
    <section className="discover-page">

      <div className="discover-heading">
        <div>
          <h1 className="brand discover-brand">
            <button
              type="button"
              className="dino-home"
              onClick={onBack}
              title="Back to Downloader"
              aria-label="Back to Downloader"
            >
              <img
                src={dinosaurLogo}
                className="dinosaur-logo"
                alt=""
              />
            </button>
            DINOSAUR DISCOVER
          </h1>
          <p>
            STREAMING RELEASE RADAR // SK REGION
          </p>
        </div>

        <button
          type="button"
          className="discover-back"
          onClick={onBack}
        >
          ← DOWNLOADER
        </button>
      </div>

      <div className="discover-mode-tabs">
        <button
          type="button"
          className={mode === "releases" ? "active" : ""}
          aria-pressed={mode === "releases"}
          onClick={() => setMode("releases")}
        >
          NEW RELEASES
        </button>

        <button
          type="button"
          className={mode === "streaming" ? "active" : ""}
          aria-pressed={mode === "streaming"}
          onClick={() => setMode("streaming")}
        >
          NEW ON STREAMING
        </button>
      </div>

      <div className="discover-filters">

        <div className="discover-section-label">
          01 / CONTENT TYPE
        </div>

        <div className="discover-type-grid">
          {CONTENT_TYPES.map(type => (
            <button
              type="button"
              key={type.value}
              aria-pressed={mediaType === type.value}
              className={
                mediaType === type.value
                  ? "active"
                  : ""
              }
              onClick={() => {
                setPageLimit(2);
                setMediaType(type.value);
                setProviderId(0);
                setSelectedGenres(previous =>
                  previous.filter(id => {
                    const genre = genreOptions.find(
                      g => g.id === id
                    );
                    return type.value === "all" ||
                      !!genre?.[type.value].length;
                  })
                );
              }}
            >
              <span className="discover-type-icon">
                {type.icon}
              </span>
              {type.label}
            </button>
          ))}
        </div>

        <div className="discover-section-label">
          02 / STREAMING PLATFORM
        </div>

        {providerError && (
          <p className="discover-error">
            {providerError}
          </p>
        )}

        <div className="discover-platform-grid">

          <button
            type="button"
            aria-pressed={providerId === 0}
            className={
              providerId === 0 ? "active" : ""
            }
            onClick={() => {
              setPageLimit(2);
              setProviderId(0);
            }}
          >
            <span className="discover-platform-all">
              ▦
            </span>
            <span>ALL PLATFORMS</span>
          </button>

          {platforms.map(platform => (
            <button
              type="button"
              key={platform.id}
              aria-pressed={providerId === platform.id}
              className={
                providerId === platform.id
                  ? "active"
                  : ""
              }
              onClick={() => {
                setPageLimit(2);
                setProviderId(platform.id);
              }}
            >
              {platform.logo && (
                <img
                  src={platform.logo}
                  alt=""
                />
              )}
              <span>{platform.name}</span>
            </button>
          ))}
        </div>

        <div className="discover-filter-heading">
          <div className="discover-section-label">
            03 / {mode === "streaming"
              ? "AVAILABILITY FILTERS"
              : "DISCOVER FILTERS"}
          </div>

          <button
            type="button"
            className="discover-reset-link"
            onClick={resetFilters}
          >
            ↻ RESET
          </button>
        </div>

        <div className="discover-filter-grid">

          <label>
            <span>{mode === "streaming"
              ? "DETECTION PERIOD"
              : "RELEASE PERIOD"}</span>
            <select
              value={days}
              onChange={event => {
                setPageLimit(2);
                setDays(Number(event.target.value));
              }}
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </label>

          <GenreFilter
            options={availableGenres}
            selected={selectedGenres}
            onChange={changeGenres}
            disabled={!genreOptions.length}
          />

          <label>
            <span>SORT BY {mode === "streaming"
              ? "(LOADED TITLES)" : ""}</span>
            <select
              value={sort}
              onChange={event => {
                setPageLimit(2);
                setSort(event.target.value);
              }}
            >
              <option value="newest">
                Newest first
              </option>
              <option value="rating">
                Highest rated
              </option>
              <option value="popular">
                Most popular
              </option>
            </select>
          </label>
        </div>

        {genreError && (
          <div className="discover-warning">
            Genres unavailable: {genreError}
          </div>
        )}

        {selectedGenres.length > 0 && (
          <div className="discover-genre-chips">
            {selectedGenres.map(id => (
              <button
                type="button"
                key={id}
                aria-label={`Remove genre ${id}`}
                onClick={() => changeGenres(
                  selectedGenres.filter(value => value !== id)
                )}
              >
                {genreOptions.find(g => g.id === id)?.label ?? id}
                <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
        )}

        {mode === "streaming" && (
          <small className="discover-loaded-filter-note">
            Genre, rating and sorting apply to loaded titles.
          </small>
        )}

        <div className="discover-rating-filter">

          <label htmlFor="discover-min-rating">
            MINIMUM TMDB RATING
            {mode === "streaming" ? " (LOADED TITLES)" : ""}
          </label>

          <strong>
            {rating === 0 ? "ALL" : `${rating}%`}
          </strong>

          <input
            id="discover-min-rating"
            type="range"
            min={0}
            max={100}
            step={5}
            value={rating}
            onChange={event => {
              setPageLimit(2);
              setRating(Number(event.target.value));
            }}
          />

          <div className="discover-range-labels">
            <span>Any rating</span>
            <span>100%</span>
          </div>
        </div>

        <div className="discover-filter-actions">
          <div className="discover-owned-filter">
            <div>
              <strong>HIDE OWNED MOVIES</strong>
              <small>Hide movies already in Jellyfin</small>
            </div>

            <button
              type="button"
              role="switch"
              aria-label="Hide owned movies"
              aria-checked={hideOwned}
              disabled={!libraryKeys}
              className={`discover-switch ${
                hideOwned ? "active" : ""
              }`}
              onClick={() => setHideOwned(value => !value)}
            >
              <span />
            </button>
          </div>


        </div>
      </div>

      <div className="discover-library-sync">
        <span className={
          libraryKeys ? "connected" : "unavailable"
        }>
          {libraryKeys
            ? "● LIBRARY CONNECTED"
            : libraryError
              ? "● LIBRARY UNAVAILABLE"
              : "● CHECKING LIBRARY"}
        </span>
      </div>

      {mode === "streaming" ? (
        <StreamingResults
          key={JSON.stringify([
            mediaType, providerId, days, refresh
          ])}
          mediaType={mediaType}
          providerId={providerId}
          providers={providers}
          days={days}
          rating={rating}
          genreIds={streamingGenreIds}
          sort={sort}
          hideOwned={hideOwned}
          libraryKeys={libraryKeys}
          onSearch={onSearch}
        />
      ) : (
        <>
      <div className="discover-results-heading">
        <h2>04 / NEW RELEASES</h2>

        <span>
          {loading
            ? "SCANNING..."
            : `${visibleItems.length} TITLES${hiddenCount ? ` / ${hiddenCount} HIDDEN` : ""}`}
        </span>
      </div>

      {error && (
        <div className="discover-error">
          <p>{error}</p>

          <button
            type="button"
            onClick={() => setRefresh(v => v + 1)}
          >
            RETRY
          </button>
        </div>
      )}

      {loading && !catalog && (
        <div
          className="discover-message"
          role="status"
        >
          SCANNING STREAMING CATALOGS...
        </div>
      )}

      {catalog && (
        <>
          {catalog.errors.length > 0 && (
            <div className="discover-warning">
              SOME PLATFORMS ARE TEMPORARILY UNAVAILABLE
            </div>
          )}

          {catalog.truncated && !catalog.has_more && (
            <div className="discover-warning">
              SEARCH LIMIT REACHED.
              TRY NARROWER FILTERS.
            </div>
          )}

          {visibleItems.length === 0 ? (
            <div className="discover-message">
              NO TITLES FOUND.
              TRY DIFFERENT FILTERS.
            </div>
          ) : (
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
          )}
        </>
      )}

      {catalog?.has_more && (
        <div className="discover-pagination">
          <button
            type="button"
            className="discover-load-more"
            disabled={loading || !!error}
            onClick={() => {
              setLoading(true);
              setPageLimit(current =>
                Math.min(
                  current + 2,
                  catalog.max_pages
                )
              );
            }}
          >
            {loading
              ? "SCANNING MORE RELEASES..."
              : "+ LOAD MORE"}
          </button>

          <span className="discover-pagination-info">
            {catalog.page_limit} / {catalog.max_pages}
            {" "}PAGE LIMIT PER PLATFORM / TYPE
          </span>
        </div>
      )}

        </>
      )}

      <footer className="discover-attribution">
        <div className="discover-attribution-logos">
          <a
            href="https://www.themoviedb.org/"
            target="_blank"
            rel="noreferrer"
          >
            <img
              src={tmdbLogo}
              alt="The Movie Database"
              className="discover-tmdb-logo"
            />
          </a>
        </div>
        <p>
          Movie and TV metadata:
          {" "}
          <a
            href="https://www.themoviedb.org/"
            target="_blank"
            rel="noreferrer"
          >
            TMDB
          </a>
          {" "} / Streaming data:
          {" "}
          <a
            href="https://www.justwatch.com/sk"
            target="_blank"
            rel="noreferrer"
          >
            JustWatch
          </a>
        </p>

        <p>
          This application uses TMDB and the TMDB APIs
          but is not endorsed, certified, or otherwise approved by TMDB.
        </p>

        <p>
          {mode === "streaming"
            ? "Dates represent detected availability changes, not official platform addition dates."
            : "Dates represent title premieres, not streaming catalog addition dates."}
        </p>
      </footer>

    </section>
  );
}
