import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AttachmentPreview } from "../src/features/attachments/AttachmentPicker";
import type { AttachmentInfo } from "../src/lib/api";

const image: AttachmentInfo = {
  id: "preview-one",
  display_name: "first-capture.png",
  kind: "image",
  mime: "image/webp",
  size: 100,
  original_size: 100,
  status: "ready",
  extracted_characters: 0,
  preview: "",
  preview_truncated: false,
  warnings: [],
  width: 1200,
  height: 800,
};
const originalShow = Object.getOwnPropertyDescriptor(
  HTMLDialogElement.prototype,
  "showModal",
);
const originalClose = Object.getOwnPropertyDescriptor(
  HTMLDialogElement.prototype,
  "close",
);

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = true;
      this.querySelector<HTMLButtonElement>("button")?.focus();
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = false;
    },
  });
  vi.spyOn(Element.prototype, "clientWidth", "get").mockReturnValue(600);
  vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(400);
});
afterEach(() => {
  cleanup();
  for (const [key, descriptor] of [
    ["showModal", originalShow],
    ["close", originalClose],
  ] as const) {
    if (descriptor)
      Object.defineProperty(HTMLDialogElement.prototype, key, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, key);
  }
  document.body.style.overflow = "";
});

function loadPreview() {
  const dialog = screen.getByRole("dialog", { name: image.display_name });
  const photo = within(dialog).getByRole("img", { hidden: true });
  Object.defineProperties(photo, {
    naturalWidth: { value: 1200 },
    naturalHeight: { value: 800 },
  });
  fireEvent.load(photo);
  return { dialog, photo };
}

test("draft and historical thumbnails open authenticated previews without submitting or removing files", () => {
  const submit = vi.fn((event) => event.preventDefault()),
    remove = vi.fn();
  document.body.style.overflow = "auto";
  render(
    <form onSubmit={submit}>
      <textarea aria-label="Draft" defaultValue="Keep my prompt" />
      <AttachmentPreview items={[image]} onRemove={remove} />
    </form>,
  );
  const trigger = screen.getByRole("button", {
    name: `Preview image: ${image.display_name}`,
  });
  fireEvent.click(trigger);
  const { dialog, photo } = loadPreview();
  expect(photo).toHaveAttribute("src", "/api/attachments/preview-one");
  expect(dialog.parentElement).toBe(document.body);
  expect(document.body.style.overflow).toBe("hidden");
  expect(
    within(dialog).getByRole("button", { name: "Close image preview" }),
  ).toHaveFocus();
  fireEvent.click(within(dialog).getByRole("button", { name: "Actual size" }));
  expect(within(dialog).getByLabelText("Zoom level")).toHaveTextContent("100%");
  fireEvent.click(within(dialog).getByRole("button", { name: "Zoom in" }));
  expect(within(dialog).getByLabelText("Zoom level")).toHaveTextContent("150%");
  for (let step = 0; step < 3; step++)
    fireEvent.click(within(dialog).getByRole("button", { name: "Zoom in" }));
  expect(within(dialog).getByLabelText("Zoom level")).toHaveTextContent("400%");
  expect(
    within(dialog).getByRole("button", { name: "Zoom in" }),
  ).toBeDisabled();
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Fit to screen" }),
  );
  expect(within(dialog).getByLabelText("Zoom level")).toHaveTextContent("50%");
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Close image preview" }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(document.body.style.overflow).toBe("auto");
  expect(screen.getByLabelText("Draft")).toHaveValue("Keep my prompt");
  expect(submit).not.toHaveBeenCalled();
  expect(remove).not.toHaveBeenCalled();
});

test("unavailable images show a local error, disable zoom and can close with Escape", () => {
  render(<AttachmentPreview items={[image]} />);
  const trigger = screen.getByRole("button", {
    name: `Preview image: ${image.display_name}`,
  });
  fireEvent.click(trigger);
  const dialog = screen.getByRole("dialog", { name: image.display_name });
  fireEvent.error(within(dialog).getByRole("img", { hidden: true }));
  expect(within(dialog).getByRole("alert")).toHaveTextContent(
    "image is unavailable",
  );
  expect(
    within(dialog).getByRole("button", { name: "Zoom in" }),
  ).toBeDisabled();
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(
    screen.queryByRole("button", { name: /Remove from draft/ }),
  ).not.toBeInTheDocument();
});

test("removing an open attachment closes its preview and restoring the item never reopens it automatically", async () => {
  const { rerender, unmount } = render(<AttachmentPreview items={[image]} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: `Preview image: ${image.display_name}`,
    }),
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await act(async () => rerender(<AttachmentPreview items={[]} />));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe("");
  rerender(<AttachmentPreview items={[image]} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", {
      name: `Preview image: ${image.display_name}`,
    }),
  );
  unmount();
  expect(document.body.style.overflow).toBe("");
});

test("each selected image uses its own stored source and documents retain their text preview", () => {
  const second = {
    ...image,
    id: "preview-two",
    display_name: "second-capture.png",
  };
  const document = {
    ...image,
    id: "doc",
    display_name: "notes.txt",
    kind: "document" as const,
    mime: "text/plain",
    width: null,
    height: null,
    preview: "Saved document text",
  };
  render(<AttachmentPreview items={[image, second, document]} />);
  fireEvent.click(
    screen.getByRole("button", {
      name: `Preview image: ${second.display_name}`,
    }),
  );
  const dialog = screen.getByRole("dialog", { name: second.display_name });
  expect(within(dialog).getByRole("img", { hidden: true })).toHaveAttribute(
    "src",
    "/api/attachments/preview-two",
  );
  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", {
      name: `Preview image: ${second.display_name}`,
    }),
  ).toHaveFocus();
  expect(
    screen.queryByRole("button", { name: "Preview image: notes.txt" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Saved document text")).toBeInTheDocument();
});
