import { useEffect, useRef, useState } from "react";
import type { GenreOption } from "./types";

export default function GenreFilter({
  options,
  selected,
  onChange,
  disabled,
}: {
  options: GenreOption[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);

  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;

    searchInput.current?.focus();

    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function keyboard(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }

    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", keyboard);

    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", keyboard);
    };
  }, [open]);

  useEffect(() => {
    setOpen(false);
  }, [options]);

  const filtered = options.filter(option =>
    option.label.toLowerCase().includes(
      search.trim().toLowerCase()
    )
  );

  const label = selected.length === 0
    ? "All genres"
    : selected.length === 1
      ? options.find(g => g.id === selected[0])?.label
        ?? "1 genre"
      : `${selected.length} genres selected`;

  function apply() {
    onChange([...draft].sort());
    setOpen(false);
    trigger.current?.focus();
  }

  return (
    <div className="discover-genre-filter" ref={root}>
      <span className="discover-field-label">GENRES</span>

      <button
        ref={trigger}
        type="button"
        className="discover-genre-trigger"
        aria-expanded={open}
        aria-controls="discover-genre-menu"
        disabled={disabled}
        onClick={() => {
          if (!open) {
            setDraft([...selected]);
            setSearch("");
          }
          setOpen(value => !value);
        }}
      >
        <span>{label}</span>
        <span aria-hidden="true">{open ? "⌃" : "⌄"}</span>
      </button>

      {open && (
        <div
          className="discover-genre-menu"
          id="discover-genre-menu"
          role="group"
          aria-label="Select genres"
        >
          <input
            ref={searchInput}
            type="search"
            placeholder="Search genres..."
            aria-label="Search genres"
            value={search}
            onChange={event => setSearch(event.target.value)}
          />

          <div className="discover-genre-options">
            {filtered.map(genre => (
              <label key={genre.id}>
                <input
                  type="checkbox"
                  checked={draft.includes(genre.id)}
                  onChange={() => {
                    setDraft(previous =>
                      previous.includes(genre.id)
                        ? previous.filter(id => id !== genre.id)
                        : [...previous, genre.id]
                    );
                  }}
                />
                <span>{genre.label}</span>
              </label>
            ))}

            {!filtered.length && (
              <small>No matching genres</small>
            )}
          </div>

          <div className="discover-genre-menu-actions">
            <button
              type="button"
              onClick={() => setDraft([])}
            >
              Clear all
            </button>

            <button
              type="button"
              className="discover-genre-apply"
              onClick={apply}
            >
              Apply
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
