import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import SavedPrompt from "../src/features/chat/SavedPrompt";

test("copies the exact saved prompt without submitting its surrounding form", async () => {
  const text =
    "  Describe esta imagen 🖼️\n\nKeep **formatting** and `code`.\t ";
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const submit = vi.fn((event) => event.preventDefault());
  const { rerender } = render(
    <form onSubmit={submit}>
      <SavedPrompt text={text} />
    </form>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith(text));
  expect(submit).not.toHaveBeenCalled();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Prompt copied to clipboard.",
  );
  rerender(<SavedPrompt text="Another saved prompt" />);
  expect(screen.getByRole("button", { name: "Copy prompt" })).toHaveTextContent(
    "Copy prompt",
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("reports clipboard rejection and allows a successful retry", async () => {
  const writeText = vi
    .fn()
    .mockRejectedValueOnce(new DOMException("Denied", "NotAllowedError"))
    .mockResolvedValueOnce(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  render(<SavedPrompt text="Saved text" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not copy. Select the prompt text and copy it manually.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Prompt copied to clipboard.",
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(writeText).toHaveBeenCalledTimes(2);
});

test("missing clipboard access keeps selectable text and reports failure", async () => {
  vi.stubGlobal("navigator", { clipboard: undefined });
  render(<SavedPrompt text="Available for manual copying" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy prompt" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.getByText("Available for manual copying")).toBeVisible();
});
