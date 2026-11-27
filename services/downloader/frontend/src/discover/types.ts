export type MediaType = "all" | "movie" | "tv";

export type Platform = {
  id: number;
  name: string;
  logo: string | null;
};

export type MediaItem = {
  detected_at?: string;
  streaming_additions?: StreamingAddition[];
  id: number;
  key: string;
  media_type: "movie" | "tv";
  title: string;
  original_title: string;
  year: string;
  release_date: string;
  first_air_date?: string;
  season_number?: number | null;
  release_kind?: "new_movie" | "new_series" | "new_season";
  overview: string;
  poster: string | null;
  backdrop: string | null;
  tmdb_rating: number | null;
  tmdb_votes: number;
  csfd_rating: number | null;
  popularity: number;
  providers: Platform[];
};

export type CatalogResponse = {
  region: string;
  count: number;
  date_type: string;
  truncated: boolean;
  page_limit: number;
  max_pages: number;
  has_more: boolean;
  errors: {
    provider: string;
    media_type: string;
    error: string;
  }[];
  items: MediaItem[];
};

export type ProviderResponse = {
  region: string;
  movie: Platform[];
  tv: Platform[];
};

export type StreamingAddition = {
  provider_id: number;
  provider: string;
  detected_at: string;
};

export type StreamingCatalog = {
  provider_id: number;
  provider: string;
  media_type: "movie" | "tv";
  initialized: boolean;
  titles: number;
  pending_added: number;
  pending_removed: number;
  scanned_at: string | null;
};

export type StreamingStatus = {
  region: string;
  initialized_catalogs: number;
  total_catalogs: number;
  baseline_complete: boolean;
  tracked_entries: number;
  catalogs: StreamingCatalog[];
};

export type StreamingResponse = {
  region: string;
  total: number;
  count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  items: MediaItem[];
  errors: {
    media_type: string;
    tmdb_id: number;
    error: string;
  }[];
};
