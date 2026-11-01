import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import CopyButton from "../src/features/chat/CopyButton";

const props = {
  text: "Exact **response**\n  with whitespace",
  label: "Copy response",
  successMessage: "Response copied to clipboard.",
  failureMessage: "Could not copy the response.",
};
afterEach(() => vi.useRealTimers());

test("confirms only after clipboard success and restores its label after two seconds", async () => {
  vi.useFakeTimers();
  let resolve!: () => void;
  const writeText = vi.fn(
    () =>
      new Promise<void>((done) => {
        resolve = done;
      }),
  );
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const submit = vi.fn((event) => event.preventDefault());
  render(
    <form onSubmit={submit}>
      <CopyButton {...props} />
    </form>,
  );
  const button = screen.getByRole("button", { name: props.label });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(writeText).toHaveBeenCalledTimes(1);
  expect(writeText).toHaveBeenCalledWith(props.text);
  expect(button).toHaveTextContent("Copy response");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  await act(async () => resolve());
  expect(button).toHaveTextContent("Copied");
  expect(screen.getByRole("status")).toHaveTextContent(props.successMessage);
  await act(async () => vi.advanceTimersByTime(1999));
  expect(button).toHaveTextContent("Copied");
  await act(async () => vi.advanceTimersByTime(1));
  expect(button).toHaveTextContent("Copy response");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(submit).not.toHaveBeenCalled();
});

test("copying again restarts the feedback timer without changing copied text", async () => {
  vi.useFakeTimers();
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  render(<CopyButton {...props} />);
  const button = screen.getByRole("button", { name: props.label });
  await act(async () => fireEvent.click(button));
  await act(async () => vi.advanceTimersByTime(1500));
  await act(async () => fireEvent.click(button));
  await act(async () => vi.advanceTimersByTime(500));
  expect(button).toHaveTextContent("Copied");
  await act(async () => vi.advanceTimersByTime(1500));
  expect(button).toHaveTextContent("Copy response");
  expect(writeText.mock.calls).toEqual([[props.text], [props.text]]);
});

test("failed copies show a retryable error and never claim success", async () => {
  const writeText = vi
    .fn()
    .mockRejectedValueOnce(new Error("denied"))
    .mockResolvedValueOnce(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  render(<CopyButton {...props} />);
  const button = screen.getByRole("button", { name: props.label });
  await act(async () => fireEvent.click(button));
  expect(screen.getByRole("alert")).toHaveTextContent(props.failureMessage);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(button).toHaveTextContent("Copy response");
  await act(async () => fireEvent.click(button));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(button).toHaveTextContent("Copied");
});

test("a changed or unmounted response ignores a late clipboard completion", async () => {
  vi.useFakeTimers();
  let resolve!: () => void;
  vi.stubGlobal("navigator", {
    clipboard: {
      writeText: () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    },
  });
  const { rerender, unmount } = render(<CopyButton {...props} />);
  fireEvent.click(screen.getByRole("button", { name: props.label }));
  rerender(<CopyButton {...props} text="Changed response" />);
  await act(async () => resolve());
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: props.label }));
  unmount();
  await act(async () => resolve());
  expect(vi.getTimerCount()).toBe(0);
});

test("changing away from copied text clears feedback even if it later returns", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("navigator", {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
  const { rerender, unmount } = render(<CopyButton {...props} />);
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: props.label })),
  );
  expect(vi.getTimerCount()).toBe(1);
  rerender(<CopyButton {...props} text="Another text" />);
  rerender(<CopyButton {...props} />);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(vi.getTimerCount()).toBe(0);
  unmount();
});

test("each copy control owns its feedback and reads lazy content at click time", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  let code = "first";
  render(
    <>
      <CopyButton {...props} />
      <CopyButton {...props} label="Copy code" text={() => code} />
    </>,
  );
  code = "const example = 2;\n";
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Copy code" })),
  );
  expect(writeText).toHaveBeenCalledWith(code);
  expect(
    screen.getByRole("button", { name: "Copy response" }),
  ).toHaveTextContent("Copy response");
  expect(screen.getByRole("button", { name: "Copy code" })).toHaveTextContent(
    "Copied",
  );
});
