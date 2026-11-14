import { useEffect, useId, useMemo, useRef, useState } from "react";
import { copy } from "../../lib/copy";
import {
  filterModelChoices,
  modelInputLabel,
  supportsTextAndImage,
  type ModelChoice,
} from "../../lib/modelCapabilities";

export default function ModelPicker({
  models,
  value,
  onChange,
  favorites,
  imageOnly,
  onImageOnlyChange,
}: {
  models: ModelChoice[];
  value: string;
  onChange: (id: string) => void;
  favorites: string[];
  imageOnly: boolean;
  onImageOnlyChange: (checked: boolean) => void;
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
    return filterModelChoices(models, query, imageOnly, favorites);
  }, [models, query, imageOnly, favorites]);
  useEffect(() => setHighlight(0), [imageOnly]);
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
  function choose(model: ModelChoice) {
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
        title={
          selected
            ? `${selected.name} · ${modelInputLabel(selected)}`
            : undefined
        }
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
                event.key === "ArrowUp"
                  ? Math.max(
                      0,
                      filterModelChoices(models, "", imageOnly, favorites)
                        .length - 1,
                    )
                  : 0,
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
        {selected ? ` · ${modelInputLabel(selected)}` : ""}
      </span>
      {open && (
        <div className="model-popup">
          <label className="model-image-filter">
            <input
              type="checkbox"
              checked={imageOnly}
              onChange={(event) => {
                setHighlight(0);
                onImageOnlyChange(event.target.checked);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.preventDefault();
                if (event.key === "Escape") {
                  event.preventDefault();
                  event.stopPropagation();
                  input.current?.focus();
                  setOpen(false);
                }
              }}
            />
            {copy.imageModelsOnly}
          </label>
          {imageOnly && selected && !supportsTextAndImage(selected) && (
            <p className="model-filter-notice">
              {copy.selectedOutsideImageFilter}
            </p>
          )}
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
                  <small className="model-input-badge">
                    {modelInputLabel(model)}
                  </small>
                </div>
              );
            })}
          </div>
          <p role="status">
            {filtered.length
              ? copy.modelCount(filtered.length)
              : imageOnly
                ? copy.noMatchingImageModels
                : copy.noMatchingModels}
          </p>
        </div>
      )}
    </div>
  );
}
