import type { MediaItem } from "./types";
import useCsfdRating from "./useCsfdRating";

export default function MediaCard({
  item,
  onSelect,
  libraryMatch,
}: {
  item: MediaItem;
  onSelect: (item: MediaItem) => void;
  libraryMatch: boolean | null;
}) {
  const rating = item.tmdb_rating;

  const { cardRef, result: csfd } =
    useCsfdRating(item.media_type, item.id);

  const csfdRating = csfd?.csfd_rating ?? null;

  const ratingClass =
    rating == null ? "unknown" :
    rating >= 80 ? "excellent" :
    rating >= 70 ? "good" :
    rating >= 50 ? "average" :
    "poor";

  return (
    <button
      type="button"
      ref={cardRef}
      className="discover-media-card"
      onClick={() => onSelect(item)}
      aria-label={`Search for ${item.title}`}
    >
      <div className="discover-poster">

        {item.poster ? (
          <img
            src={item.poster}
            alt={item.title}
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="discover-no-poster">
            NO POSTER
          </div>
        )}

        <span
          className={`discover-media-type ${item.media_type}`}
        >
          {item.media_type === "movie"
            ? "MOVIE"
            : "TV SERIES"}
        </span>

        <span
          className={`discover-rating ${ratingClass}`}
          title={`${item.tmdb_votes} TMDB votes`}
        >
          {rating == null ? "—" : `${Math.round(rating)}%`}
        </span>

        <div className="discover-poster-action">
          SEARCH IN DOWNLOADER
        </div>
      </div>

      {libraryMatch !== null && (
        <div className={
          `discover-library-status ${
            libraryMatch
              ? item.media_type === "movie"
                ? "owned"
                : "series"
              : "missing"
          }`
        }>
          {libraryMatch
            ? item.media_type === "movie"
              ? "✓ IN LIBRARY"
              : "✓ SERIES FOUND"
            : "NO ID MATCH"}
        </div>
      )}

      <div className="discover-card-body">

        <div
          className="discover-card-title"
          title={item.title}
        >
          {item.title}
        </div>

        <div className={
          `discover-release-kind ${
            item.release_kind ?? ""
          }`
        }>
          {item.streaming_additions?.length
            ? "NEW ON STREAMING"
            : item.release_kind === "new_season"
            ? `NEW SEASON / S${String(
                item.season_number ?? 0
              ).padStart(2, "0")}`
            : item.media_type === "movie"
              ? "NEW MOVIE"
              : "NEW SERIES"}
        </div>

        <div className="discover-card-year">
          {item.release_date || item.year || "—"}
        </div>

        {!!item.streaming_additions?.length && (
          <div className="streaming-card-additions">
            {item.streaming_additions.map(addition => (
              <span key={addition.provider_id}>
                + {addition.provider.toUpperCase()}
              </span>
            ))}

            {item.detected_at && (
              <small>
                DETECTED: {new Date(
                  item.detected_at
                ).toLocaleDateString("sk-SK")}
              </small>
            )}
          </div>
        )}

        <div className="discover-card-platforms">
          {item.providers.map(provider => (
            provider.logo ? (
              <img
                key={provider.id}
                src={provider.logo}
                alt={provider.name}
                title={provider.name}
                loading="lazy"
              />
            ) : (
              <span key={provider.id}>
                {provider.name}
              </span>
            )
          ))}
        </div>

        <div className="discover-card-ratings">
          <span>
            TMDB {rating == null
              ? "—"
              : `${Math.round(rating)}%`}
          </span>

          <span
            className="discover-csfd-rating"
            title="ČSFD rating provided by CZDB"
          >
            ČSFD {csfdRating == null
              ? "—"
              : `${csfdRating}%`}
          </span>
        </div>

      </div>
    </button>
  );
}
