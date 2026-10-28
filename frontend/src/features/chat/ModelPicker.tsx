import { useEffect, useId, useMemo, useRef, useState } from "react";
import { copy } from "../../lib/copy";

type Choice = { id: string; name: string };
export default function ModelPicker({
  models,
  value,
  onChange,
  favorites,
}: {
  models: Choice[];
  value: string;
  onChange: (id: string) => void;
  favorites: string[];
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const id = useId();
  const selected = models.find((model) => model.id === value);
  const filtered = useMemo(() => {
    const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return models
      .filter((model) =>
        terms.every((term) =>
          `${model.name} ${model.id}`.toLocaleLowerCase().includes(term),
        ),
      )
      .sort(
        (a, b) =>
          Number(favorites.includes(b.id)) - Number(favorites.includes(a.id)),
      );
  }, [models, query, favorites]);
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);
  useEffect(() => {
    if (open)
      list.current
        ?.querySelector('[data-highlighted="true"]')
        ?.scrollIntoView({ block: "nearest" });
  }, [open, highlight, query]);
  function show() {
    setQuery("");
    setHighlight(0);
    setOpen(true);
  }
  function choose(model: Choice) {
    onChange(model.id);
    setOpen(false);
    setQuery("");
  }
  return (
    <div
      className="model-picker"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <label className="sr-only" htmlFor={id}>
        {copy.model}
      </label>
      <input
        id={id}
        ref={input}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-activedescendant={
          open && filtered[highlight] ? `${id}-${highlight}` : undefined
        }
        aria-describedby={`${id}-selected`}
        autoComplete="off"
        spellCheck={false}
        disabled={!models.length}
        placeholder={copy.modelSearch}
        value={
          open
            ? query
            : selected
              ? selected.name.slice(
                  selected.name.indexOf(": ") >= 0
                    ? selected.name.indexOf(": ") + 2
                    : 0,
                )
              : value
        }
        title={selected?.name}
        onFocus={show}
        onClick={() => {
          if (!open) show();
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setHighlight(0);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) {
              show();
              setHighlight(
                event.key === "ArrowUp" ? Math.max(0, models.length - 1) : 0,
              );
            } else
              setHighlight((current) =>
                Math.max(
                  0,
                  Math.min(
                    filtered.length - 1,
                    current + (event.key === "ArrowDown" ? 1 : -1),
                  ),
                ),
              );
          } else if (event.key === "Enter") {
            event.preventDefault();
            event.stopPropagation();
            if (open && filtered[highlight]) choose(filtered[highlight]);
          } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
          }
        }}
      />
      <svg
        className="model-search-icon"
        viewBox="0 0 24 24"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <circle cx="10" cy="10" r="6" />
        <path d="m14.5 14.5 6 6" />
      </svg>
      <span className="sr-only" id={`${id}-selected`}>
        {copy.model}: {selected?.name ?? value}
      </span>
      {open && (
        <div className="model-popup">
          <div
            id={`${id}-list`}
            role="listbox"
            aria-label={copy.model}
            ref={list}
          >
            {filtered.map((model, index) => {
              const colon = model.name.indexOf(": ");
              const publisher =
                colon >= 0
                  ? model.name.slice(0, colon)
                  : model.id.split("/")[0];
              const name =
                colon >= 0 ? model.name.slice(colon + 2) : model.name;
              return (
                <div
                  key={model.id}
                  id={`${id}-${index}`}
                  role="option"
                  aria-selected={index === highlight}
                  data-highlighted={index === highlight}
                  className={model.id === value ? "selected-model" : ""}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    choose(model);
                    input.current?.blur();
                  }}
                >
                  <strong>
                    {favorites.includes(model.id) ? `${copy.favorites}: ` : ""}
                    {name}
                  </strong>
                  <small>
                    {publisher} · {model.id}
                  </small>
                </div>
              );
            })}
          </div>
          <p role="status">
            {filtered.length
              ? copy.modelCount(filtered.length)
              : copy.noMatchingModels}
          </p>
        </div>
      )}
    </div>
  );
}
