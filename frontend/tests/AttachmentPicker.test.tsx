import { useRef, useState } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import AttachmentPicker, {
  AttachmentPreview,
} from "../src/features/attachments/AttachmentPicker";
import {
  ApiError,
  attachmentApi,
  type AttachmentInfo,
  type UploadLimits,
} from "../src/lib/api";

const limits: UploadLimits = {
  spend_control: "provider",
  files: 5,
  file_bytes: 100,
  total_bytes: 150,
  allowed_extensions: [".png", ".jpg", ".webp"],
  vision_allowance_microusd: 0,
};
const image: AttachmentInfo = {
  id: "synthetic-image",
  display_name: "pasted-image.png",
  kind: "image",
  mime: "image/webp",
  size: 5,
  original_size: 5,
  status: "ready",
  extracted_characters: 0,
  preview: "",
  preview_truncated: false,
  warnings: [],
  width: 3,
  height: 2,
};
const png = () => new File(["image"], "image.png", { type: "image/png" });

function fixture(
  options: {
    disabled?: boolean;
    initial?: AttachmentInfo[];
    readOnly?: boolean;
    limits?: UploadLimits;
  } = {},
) {
  const changed = vi.fn(),
    busy = vi.fn(),
    failed = vi.fn();
  vi.spyOn(attachmentApi, "limits").mockResolvedValue(options.limits ?? limits);
  const upload = vi.spyOn(attachmentApi, "upload").mockResolvedValue([image]);
  function Fixture() {
    const target = useRef<HTMLTextAreaElement>(null);
    const [items, setItems] = useState(options.initial ?? []);
    const [draft, setDraft] = useState("Keep this prompt");
    return (
      <>
        <AttachmentPicker
          compact
          items={items}
          onChange={(value) => {
            setItems(value);
            changed(value);
          }}
          disabled={options.disabled}
          pasteTarget={target}
          label="Attach files"
          onFailure={failed}
          onBusyChange={busy}
        >
          <textarea
            aria-label="Prompt"
            ref={target}
            value={draft}
            readOnly={options.readOnly}
            onChange={(event) => setDraft(event.target.value)}
          />
        </AttachmentPicker>
        <textarea aria-label="Other field" />
      </>
    );
  }
  return {
    ...render(<Fixture />),
    changed,
    busy,
    failed,
    upload,
    target: screen.getByRole("textbox", { name: "Prompt" }),
  };
}
function paste(target: HTMLElement, files: File[], filesOnly = false) {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", {
    value: {
      items: filesOnly
        ? []
        : files.map((file) => ({
            kind: "file",
            type: file.type,
            getAsFile: () => file,
          })),
      files,
      getData: () => "Unrelated rich clipboard text",
    },
  });
  fireEvent(target, event);
  return event;
}

test("an image paste uploads once, preserves the prompt and can be removed", async () => {
  const { target, upload, changed } = fixture();
  expect(paste(target, [png()]).defaultPrevented).toBe(true);
  await screen.findByRole("img", { name: image.display_name });
  expect(upload).toHaveBeenCalledTimes(1);
  const file = upload.mock.calls[0][0][0];
  expect(file.name).toMatch(/^pasted-image-.*-1\.png$/);
  expect(file.type).toBe("image/png");
  expect(file.size).toBe(png().size);
  expect(target).toHaveValue("Keep this prompt");
  await userEvent.click(
    screen.getByRole("button", { name: /Remove from draft/ }),
  );
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(changed).toHaveBeenLastCalledWith([]);
});

test("generic attachment information belongs to help while file warnings stay on the card", async () => {
  fixture({
    initial: [{ ...image, warnings: ["Synthetic file-specific warning"] }],
  });
  const help = screen.getByRole("note", {
    hidden: true,
  });
  await waitFor(() =>
    expect(help).toHaveTextContent("Uses the shared OpenRouter key budget"),
  );
  expect(help).toHaveTextContent(
    "Documents are extracted locally and sent as text",
  );
  const feedback = document.querySelector(".attachment-feedback")!;
  expect(feedback).not.toHaveTextContent("Documents are extracted locally");
  expect(feedback).not.toHaveTextContent(
    "Uses the shared OpenRouter key budget",
  );
  expect(
    within(feedback as HTMLElement).getByText(
      "Synthetic file-specific warning",
    ),
  ).toBeVisible();
});

test.each([0, 12000])(
  "application vision allowance %s stays visible without claiming a shared provider budget",
  async (allowance) => {
    fixture({
      initial: [image],
      limits: {
        ...limits,
        spend_control: "application",
        vision_allowance_microusd: allowance,
      },
    });
    const message = allowance
      ? "Configured vision allowance per model: $0.012000"
      : "Live vision requires an explicitly configured allowance for uncertain input pricing.";
    expect(await screen.findByText(message)).toBeVisible();
    expect(
      screen.queryByText(
        "Uses the shared OpenRouter key budget. Image-input pricing may be uncertain.",
      ),
    ).not.toBeInTheDocument();
  },
);

test("text paste is native and pasting outside the prompt never uploads", async () => {
  const { target, upload } = fixture();
  const user = userEvent.setup();
  await user.click(target);
  await user.keyboard("{End}");
  await user.paste(" and pasted text");
  expect(target).toHaveValue("Keep this prompt and pasted text");
  expect(
    paste(screen.getByRole("textbox", { name: "Other field" }), [png()])
      .defaultPrevented,
  ).toBe(false);
  expect(upload).not.toHaveBeenCalled();
});

test("a file-list-only clipboard accepts multiple images without duplication", async () => {
  const { target, upload } = fixture();
  upload.mockResolvedValue([
    image,
    { ...image, id: "second", display_name: "second.jpg" },
  ]);
  paste(target, [png(), new File(["jpeg"], "", { type: "image/jpeg" })], true);
  await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
  expect(upload).toHaveBeenCalledTimes(1);
  expect(upload.mock.calls[0][0].map((file) => file.type)).toEqual([
    "image/png",
    "image/jpeg",
  ]);
  expect(upload.mock.calls[0][0][1].name).toMatch(/-2\.jpg$/);
});

test.each([
  [
    "unsupported image",
    () => [new File(["svg"], "image.svg", { type: "image/svg+xml" })],
    "Paste a PNG",
  ],
  ["count limit", () => Array.from({ length: 6 }, png), "attachment count"],
  [
    "per-file size",
    () => [new File(["x".repeat(101)], "big.png", { type: "image/png" })],
    "size limit",
  ],
  [
    "batch size",
    () => [
      new File(["x".repeat(80)], "a.png", { type: "image/png" }),
      new File(["x".repeat(80)], "b.png", { type: "image/png" }),
    ],
    "size limit",
  ],
] as const)(
  "%s keeps existing attachments and draft",
  async (_, files, message) => {
    const { target, upload } = fixture({ initial: [image] });
    await waitFor(() =>
      expect(screen.getByText(/5 files/)).toBeInTheDocument(),
    );
    expect(paste(target, files()).defaultPrevented).toBe(true);
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(target).toHaveValue("Keep this prompt");
    expect(upload).not.toHaveBeenCalled();
  },
);

test("upload failure is visible and a later paste retries without clearing the draft", async () => {
  const { target, upload } = fixture();
  upload.mockRejectedValueOnce(
    new ApiError(503, "Synthetic upload unavailable"),
  );
  paste(target, [png()]);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Synthetic upload unavailable",
  );
  expect(target).toHaveValue("Keep this prompt");
  paste(target, [png()]);
  await screen.findByRole("img");
  expect(upload).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("rapid pastes share the upload lock and cannot overwrite pending files", async () => {
  const { target, upload, busy } = fixture({ initial: [image] });
  let release!: (value: AttachmentInfo[]) => void;
  upload.mockReturnValue(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  paste(target, [png()]);
  paste(target, [png()]);
  expect(upload).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "An upload is in progress",
  );
  expect(
    screen.getByRole("button", { name: /Remove from draft/ }),
  ).toBeDisabled();
  await act(async () =>
    release([{ ...image, id: "new-image", display_name: "new-image.png" }]),
  );
  expect(screen.getAllByRole("img")).toHaveLength(2);
  expect(busy.mock.calls).toEqual([[true], [false]]);
});

test("locked or read-only inputs cannot acquire new pasted files", async () => {
  const first = fixture({ disabled: true });
  paste(first.target, [png()]);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Attachments cannot be changed",
  );
  expect(first.upload).not.toHaveBeenCalled();
  first.unmount();
  const second = fixture({ readOnly: true });
  expect(paste(second.target, [png()]).defaultPrevented).toBe(false);
  expect(second.upload).not.toHaveBeenCalled();
});

test("unmounted upload completion cannot update a different draft", async () => {
  const { target, upload, changed, busy, unmount } = fixture();
  let release!: (value: AttachmentInfo[]) => void;
  upload.mockReturnValue(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  paste(target, [png()]);
  unmount();
  expect(busy.mock.calls).toEqual([[true], [false]]);
  await act(async () => release([image]));
  expect(changed).not.toHaveBeenCalled();
  expect(busy.mock.calls).toEqual([[true], [false]]);
  expect(paste(target, [png()]).defaultPrevented).toBe(false);
});

test("a pasted upload with an expired session follows the authentication failure path", async () => {
  const { target, upload, failed, changed } = fixture();
  const error = new ApiError(401, "Synthetic expired session");
  upload.mockRejectedValueOnce(error);
  paste(target, [png()]);
  await waitFor(() => expect(failed).toHaveBeenCalledWith(error));
  expect(changed).not.toHaveBeenCalled();
  expect(target).toHaveValue("Keep this prompt");
});

test("card removal uses attachment identity and moves focus to the next card or Attach", async () => {
  const second = { ...image, id: "second-image" };
  const { changed, target } = fixture({ initial: [image, second] });
  const buttons = screen.getAllByRole("button", { name: /Remove from draft/ });
  expect(buttons[0].closest(".attachment-item")).not.toBeNull();
  await userEvent.click(buttons[0]);
  expect(changed).toHaveBeenLastCalledWith([second]);
  expect(
    screen.getByRole("button", { name: /Remove from draft/ }),
  ).toHaveFocus();
  expect(target).toHaveValue("Keep this prompt");
  await userEvent.click(
    screen.getByRole("button", { name: /Remove from draft/ }),
  );
  expect(changed).toHaveBeenLastCalledWith([]);
  expect(screen.getByLabelText("Attach files")).toHaveFocus();
});

test("immutable previews have no removal action and locked drafts cannot remove files", async () => {
  const view = render(<AttachmentPreview items={[image]} />);
  expect(screen.getByRole("img")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Remove from draft/ }),
  ).not.toBeInTheDocument();
  view.unmount();
  const { changed } = fixture({ disabled: true, initial: [image] });
  const remove = screen.getByRole("button", { name: /Remove from draft/ });
  expect(remove).toBeDisabled();
  await userEvent.click(remove);
  expect(changed).not.toHaveBeenCalled();
  expect(screen.getByRole("img")).toBeInTheDocument();
});
