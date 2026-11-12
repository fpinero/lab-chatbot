import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { RunInfo } from "../src/lib/api";
import RunCard from "../src/features/chat/RunCard";

const run: RunInfo = {
  id: "synthetic-run",
  conversation_id: "synthetic-chat",
  model_id: "mock/steady",
  model_name: "Current answer",
  turn: 1,
  prompt: "Synthetic prompt",
  output: "",
  status: "queued",
  error_code: null,
  provider: null,
  generation_id: null,
  sequence: 0,
  created_at: 1,
  started_at: null,
  completed_at: null,
  first_token_ms: null,
  elapsed_ms: null,
  reserved_microusd: 0,
  actual_microusd: null,
  queue_delay_ms: null,
  comparison_id: null,
  attachments: [],
  accounting_state: "reserved",
  usage: null,
  simulated: true,
  settings: {},
};

test.each(["queued", "running", "cancel_requested"])(
  "%s answers retain their indicator and never expose response copy, including partial text",
  (status) => {
    const { rerender, container } = render(
      <RunCard run={{ ...run, status }} />,
    );
    expect(container.querySelector(".processing-dots")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(
      screen.queryByRole("button", { name: "Copy response" }),
    ).not.toBeInTheDocument();
    rerender(<RunCard run={{ ...run, status, output: "Partial output" }} />);
    expect(screen.getByText("Partial output")).toBeVisible();
    expect(container.querySelector(".processing-dots")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Copy response" }),
    ).not.toBeInTheDocument();
  },
);

test.each(["succeeded", "failed", "cancelled", "interrupted"])(
  "%s answers stop indicating and offer copy only for actual text",
  (status) => {
    const { rerender, container } = render(
      <RunCard run={{ ...run, status, output: "Saved text" }} />,
    );
    expect(container.querySelector(".processing-dots")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy response" })).toBeEnabled();
    for (const output of ["", " \n\t"]) {
      rerender(<RunCard run={{ ...run, status, output }} />);
      expect(
        screen.queryByRole("button", { name: "Copy response" }),
      ).not.toBeInTheDocument();
    }
  },
);

test("finishing a streamed answer enables exact copying without blocking completed older answers", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const older = {
    ...run,
    id: "older",
    model_name: "Older answer",
    status: "succeeded",
    output: "Older saved response",
  };
  const current = (status: string, output = "") => (
    <>
      <RunCard run={older} />
      <RunCard run={{ ...run, status, output }} />
    </>
  );
  const { rerender } = render(current("queued"));
  const old = within(screen.getByRole("article", { name: "Older answer" }));
  const latest = within(
    screen.getByRole("article", { name: "Current answer" }),
  );
  await act(async () =>
    fireEvent.click(old.getByRole("button", { name: "Copy response" })),
  );
  expect(writeText).toHaveBeenLastCalledWith(older.output);
  rerender(current("running", "Streaming partial"));
  expect(
    latest.queryByRole("button", { name: "Copy response" }),
  ).not.toBeInTheDocument();
  const finalText = "Final **Markdown**\n  with whitespace\n";
  rerender(current("succeeded", finalText));
  await act(async () =>
    fireEvent.click(latest.getByRole("button", { name: "Copy response" })),
  );
  expect(writeText).toHaveBeenLastCalledWith(finalText);
  expect(old.getByRole("button", { name: "Copy response" })).toBeEnabled();
});
