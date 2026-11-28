import { useEffect, useRef, useState } from "react";

type CsfdRating = {
  csfd_rating: number | null;
  csfd_id: number | null;
  csfd_url: string | null;
  status: string;
};

const VISIBILITY_DELAY = 1200;

export default function useCsfdRating(
  mediaType: "movie" | "tv",
  tmdbId: number,
) {
  const cardRef = useRef<HTMLButtonElement>(null);

  const [result, setResult] =
    useState<CsfdRating | null>(null);

  useEffect(() => {
    setResult(null);

    const element = cardRef.current;

    if (
      !element ||
      typeof IntersectionObserver === "undefined"
    ) return;

    const controller = new AbortController();

    let visible = false;
    let started = false;
    let timer: number | undefined;

    function cancelTimer() {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
    }

    async function loadRating() {
      if (
        started ||
        !visible ||
        document.hidden ||
        controller.signal.aborted
      ) return;

      started = true;

      try {
        const response = await fetch(
          `/api/discover/ratings/csfd/${mediaType}/${tmdbId}`,
          {
            signal: controller.signal,
            cache: "no-store",
          },
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data: CsfdRating = await response.json();

        if (!controller.signal.aborted) {
          setResult(data);
        }

      } catch {
        if (!controller.signal.aborted) {
          setResult({
            csfd_rating: null,
            csfd_id: null,
            csfd_url: null,
            status: "unavailable",
          });
        }
      }
    }

    function schedule() {
      cancelTimer();

      if (
        visible &&
        !started &&
        !document.hidden
      ) {
        timer = window.setTimeout(() => {
          timer = undefined;
          void loadRating();
        }, VISIBILITY_DELAY);
      }
    }

    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0];

        visible =
          entry.isIntersecting &&
          entry.intersectionRatio >= 0.5;

        schedule();
      },
      { threshold: 0.5 },
    );

    observer.observe(element);

    document.addEventListener(
      "visibilitychange", schedule
    );

    return () => {
      cancelTimer();
      controller.abort();
      observer.disconnect();

      document.removeEventListener(
        "visibilitychange", schedule
      );
    };
  }, [mediaType, tmdbId]);

  return { cardRef, result };
}
