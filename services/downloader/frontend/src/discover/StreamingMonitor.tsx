import type {
  StreamingStatus,
  ProviderResponse,
} from "./types";

const PLATFORMS = [
  { id: 8, name: "Netflix" },
  { id: 119, name: "Prime Video" },
  { id: 337, name: "Disney+" },
  { id: 350, name: "Apple TV" },
  { id: 1899, name: "HBO Max" },
  { id: 1773, name: "SkyShowtime" },
];

export default function StreamingMonitor({
  status,
  providers,
  additions,
  error,
}: {
  status: StreamingStatus | null;
  providers: ProviderResponse | null;
  additions: number | null;
  error: string;
}) {
  const initialized = status?.initialized_catalogs ?? 0;
  const total = status?.total_catalogs ?? 12;

  const progress = initialized / total * 100;

  const logos = new Map(
    [
      ...(providers?.movie ?? []),
      ...(providers?.tv ?? []),
    ].map(p => [p.id, p.logo])
  );

  const lastScan = (status?.catalogs ?? [])
    .map(c => c.scanned_at)
    .filter((v): v is string => v !== null)
    .sort()
    .pop();

  const metrics = [
    {
      label: "TRACKED",
      value: status?.tracked_entries.toLocaleString("sk-SK") ?? "—",
    },
    {
      label: "CATALOGS",
      value: status ? `${initialized}/${total}` : "—",
    },
    {
      label: "ADDITIONS",
      value: additions ?? "—",
    },
    {
      label: "REGION",
      value: status?.region ?? "SK",
    },
  ];

  return (
    <section className="streaming-monitor">

      <div className="streaming-monitor-header">
        <strong>STREAMING MONITOR</strong>

        <span className={`streaming-state ${
          error ? "failed" :
          status?.baseline_complete ? "ready" :
          "pending"
        }`}>
          ● {error ? "UNAVAILABLE" :
            !status ? "CONNECTING" :
            status.baseline_complete
              ? "BASELINE READY"
              : "INITIALIZING"}
        </span>
      </div>

      <div className="streaming-metrics">
        {metrics.map(metric => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

      <div
        className="streaming-progress"
        role="progressbar"
        aria-label="Initialized catalogs"
        aria-valuenow={initialized}
        aria-valuemax={total}
      >
        <div style={{ width: `${progress}%` }} />
      </div>

      <div className="streaming-platforms">
        {PLATFORMS.map(platform => {
          const rows = (status?.catalogs ?? [])
            .filter(c => c.provider_id === platform.id);

          const ready = rows.filter(c => c.initialized);
          const count = ready.reduce(
            (sum, c) => sum + c.titles, 0
          );

          const state =
            ready.length === 2 ? "ready" :
            ready.length === 1 ? "pending" :
            "waiting";

          const logo = logos.get(platform.id);

          return (
            <div
              key={platform.id}
              className={`streaming-platform ${state}`}
              title={`${platform.name}: ${ready.length}/2 catalogs`}
            >
              {logo ? (
                <img src={logo} alt={platform.name} />
              ) : (
                <span className="streaming-logo-fallback">
                  {platform.name}
                </span>
              )}

              <span className="streaming-platform-state">
                ● {!status ? "—" :
                  ready.length === 0 ? "WAIT" :
                  ready.length === 1 ? "PARTIAL" :
                  count.toLocaleString("sk-SK")}
              </span>
            </div>
          );
        })}
      </div>

      {error && (
        <div className="discover-error">{error}</div>
      )}

      <details className="streaming-details">
        <summary>
          <span>
            LAST SCAN: {lastScan
              ? new Date(lastScan).toLocaleString("sk-SK")
              : "—"}
          </span>

          <strong>DETAILS</strong>
        </summary>

        <div className="streaming-detail-list">
          {PLATFORMS.map(platform => {
            const rows = status?.catalogs.filter(
              c => c.provider_id === platform.id
            ) ?? [];

            const movies = rows.find(
              c => c.media_type === "movie"
            );

            const tv = rows.find(
              c => c.media_type === "tv"
            );

            return (
              <div key={platform.id}>
                <span>{platform.name.toUpperCase()}</span>

                <strong>
                  MOVIES {movies?.initialized
                    ? movies.titles : "—"}
                  {" / "}
                  TV {tv?.initialized ? tv.titles : "—"}
                </strong>
              </div>
            );
          })}
        </div>
      </details>
    </section>
  );
}
