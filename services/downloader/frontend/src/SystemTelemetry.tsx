import { useEffect, useState } from "react";
import "@fontsource/share-tech-mono";

type SystemMetrics = {
  cpu_temp: number | null;
  gpu_temp: number | null;
  ram_usage: number | null;
};

const emptyMetrics: SystemMetrics = {
  cpu_temp: null,
  gpu_temp: null,
  ram_usage: null,
};

const timeFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Bratislava",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Bratislava",
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric",
});

function formatDate(date: Date) {
  const parts = dateFormatter.formatToParts(date);
  const get = (type: string) =>
    parts.find(part => part.type === type)?.value ?? "";

  return (
    `${get("weekday")} / ${get("day")} ` +
    `${get("month")} ${get("year")}`
  ).toUpperCase();
}

function Metric({
  label,
  value,
  unit,
  warning,
  critical,
}: {
  label: string;
  value: number | null;
  unit: string;
  warning: number;
  critical: number;
}) {
  const state =
    value == null ? "unavailable" :
    value >= critical ? "critical" :
    value >= warning ? "warning" :
    "normal";

  return (
    <div className="hardware-metric">
      <span className="hardware-label">{label}</span>
      <span className={`hardware-value ${state}`}>
        {value == null ? "—" : `${Math.round(value)}${unit}`}
      </span>
    </div>
  );
}

export default function SystemTelemetry({
  connected,
}: {
  connected: boolean;
}) {
  const [now, setNow] = useState(new Date());
  const [metrics, setMetrics] =
    useState<SystemMetrics>(emptyMetrics);

  useEffect(() => {
    const timer = window.setInterval(
      () => setNow(new Date()),
      1000
    );

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!connected) {
      setMetrics(emptyMetrics);
      return;
    }

    let stopped = false;
    let timer: number | undefined;
    let controller: AbortController | undefined;

    async function poll() {
      controller = new AbortController();

      const timeout = window.setTimeout(
        () => controller?.abort(),
        10000
      );

      try {
        const response = await fetch("/api/system/metrics", {
          signal: controller.signal,
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error("Metrics unavailable");
        }

        const data: SystemMetrics = await response.json();

        if (!stopped) {
          setMetrics(data);
        }
      } catch {
        if (!stopped) {
          setMetrics(emptyMetrics);
        }
      } finally {
        window.clearTimeout(timeout);

        if (!stopped) {
          timer = window.setTimeout(poll, 15000);
        }
      }
    }

    void poll();

    return () => {
      stopped = true;
      window.clearTimeout(timer);
      controller?.abort();
    };
  }, [connected]);

  return (
    <div className="dino-system">

      <div className="dino-status-row">
        <div
          className={`dino-status ${
            connected ? "online" : "offline"
          }`}
        >
          <span className="dino-status-dot" />
          <span>
            DINOSAUR {connected ? "ONLINE" : "OFFLINE"}
          </span>
        </div>

        <div className="dino-clock">
          <time className="dino-clock-time">
            {timeFormatter.format(now)}
          </time>

          <span className="dino-clock-date">
            {formatDate(now)}
          </span>
        </div>
      </div>

      <div className="hardware-telemetry">
        <Metric
          label="CPU TEMP"
          value={metrics.cpu_temp}
          unit="°C"
          warning={75}
          critical={85}
        />

        <Metric
          label="GPU TEMP"
          value={metrics.gpu_temp}
          unit="°C"
          warning={75}
          critical={85}
        />

        <Metric
          label="RAM USAGE"
          value={metrics.ram_usage}
          unit="%"
          warning={80}
          critical={95}
        />
      </div>
    </div>
  );
}
