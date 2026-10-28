import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import App from "../src/App";
import Markdown from "../src/features/chat/Markdown";

const configuration = {
  auth_mode: "password",
  requires_code: false,
  environment: "test",
  provider_mode: "mock",
};
const ownerSession = {
  owner_id: "primary",
  csrf_token: "synthetic-csrf",
  expires_at: 9999999999,
  environment: "test",
  provider_mode: "mock",
};
const model = {
  id: "mock/steady",
  name: "Local steady",
  input_modalities: ["text"],
  output_modalities: ["text"],
  supported_parameters: ["max_tokens"],
  context_length: 32000,
  pricing: { prompt: "0.0000001", completion: "0.0000002" },
  simulated: true,
  api_family: "chat",
};
function reply(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status });
}

function mockRequests(
  signedIn: boolean,
  fails = false,
  providerBudget = false,
) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, options) => {
      const url = String(input);
      if (url.endsWith("/auth/login") && options?.method === "POST")
        return reply(ownerSession);
      if (url.endsWith("/auth/login")) return reply(configuration);
      if (url.endsWith("/auth/session"))
        return signedIn
          ? reply({
              ...ownerSession,
              provider_mode: providerBudget ? "openrouter" : "mock",
            })
          : reply({}, 401);
      if (url.endsWith("/attachments/limits"))
        return reply({
          files: 5,
          file_bytes: 10485760,
          total_bytes: 26214400,
          allowed_extensions: [".png", ".txt"],
          vision_allowance_microusd: 0,
        });
      if (url.endsWith("/comparisons")) return reply([]);
      if (url.endsWith("/models"))
        return reply({
          models: [model],
          fetched_at: 1,
          stale: false,
          ranking: "Simulated catalog",
        });
      if (url.endsWith("/preferences")) return reply({ favorites: [] });
      if (url.endsWith("/usage"))
        return reply({
          spend_control: providerBudget ? "provider" : "application",
          provider_key_budget: providerBudget
            ? {
                limit_usd: "9.9",
                remaining_usd: "8.5",
                used_usd: "1.4",
                checked_at: 1700000000,
              }
            : null,
          daily_actual_microusd: 0,
          outstanding_microusd: 0,
          uncertain_count: 0,
          simulated: !providerBudget,
        });
      if (url.includes("/conversations?q=")) return reply([]);
      if (url.endsWith("/conversations"))
        return reply({ id: "synthetic-conversation", title: "Hello" });
      if (url.endsWith("/runs"))
        return fails
          ? reply({ error: { message: "Synthetic failure" } }, 503)
          : reply({
              id: "synthetic-run",
              conversation_id: "synthetic-conversation",
              turn: 1,
              model_id: model.id,
              model_name: model.name,
              prompt: "Hello",
              output: "**Local simulation**",
              status: "succeeded",
              provider: "Mock",
              accounting_state: "settled",
              actual_microusd: 0,
              reserved_microusd: 100,
              settings: {},
            });
      throw new Error("Unexpected route");
    });
}

test("provider balance shows the shared key budget and refresh never generates", async () => {
  const fetcher = mockRequests(true, false, true);
  render(<App />);
  expect(
    await screen.findByText("Spending controlled by OpenRouter"),
  ).toBeVisible();
  expect(screen.getByText("Key budget: $9.90")).toBeVisible();
  expect(screen.getByText("Key remaining: $8.500000")).toBeVisible();
  await userEvent.click(
    screen.getByRole("button", { name: "Refresh balance" }),
  );
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/usage")),
  ).toHaveLength(2);
  expect(
    fetcher.mock.calls.some(([, options]) => options?.method === "POST"),
  ).toBe(false);
});

test("sign-in gates chat and credentials stay out of browser storage", async () => {
  mockRequests(false);
  render(<App />);
  expect(await screen.findByLabelText("Owner passphrase")).toBeVisible();
  expect(
    screen.queryByLabelText("Message", { exact: true }),
  ).not.toBeInTheDocument();
  await userEvent.type(
    screen.getByLabelText("Owner passphrase"),
    "synthetic-browser-passphrase",
  );
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(
    await screen.findByLabelText("Message", { exact: true }),
  ).toBeVisible();
  expect(localStorage.length + sessionStorage.length).toBe(0);
});

test("typing and model selection do not spend; submission includes CSRF and keeps unknown dispatch idempotent", async () => {
  const fetcher = mockRequests(true, true);
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  await userEvent.type(input, "Hello");
  expect(
    fetcher.mock.calls.some(([url]) => String(url).endsWith("/runs")),
  ).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Synthetic failure",
  );
  expect(input).toHaveValue("Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  const calls = fetcher.mock.calls.filter(([url]) =>
    String(url).endsWith("/runs"),
  );
  expect(calls).toHaveLength(2);
  expect(calls[0][1]?.headers).toMatchObject({
    "X-CSRF-Token": "synthetic-csrf",
  });
  expect(JSON.parse(calls[0][1]?.body as string).idempotency_key).toBe(
    JSON.parse(calls[1][1]?.body as string).idempotency_key,
  );
});

test("Markdown disables raw HTML, executable links and external image loading", () => {
  const { container } = render(
    <Markdown
      text={
        "<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))\n\n![external](https://example.invalid/track.png)\n\n```js\nconst safe = true;\n```"
      }
    />,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("a")?.getAttribute("href")).not.toContain(
    "javascript:",
  );
  expect(screen.getByRole("button", { name: "Copy code" })).toBeVisible();
});

test("switching modes preserves independent drafts without dispatch", async () => {
  const fetcher = mockRequests(true);
  render(<App />);
  await userEvent.type(
    await screen.findByLabelText("Message", { exact: true }),
    "Chat draft",
  );
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "compare");
  await userEvent.type(
    screen.getByLabelText("Comparison prompt"),
    "Compare draft",
  );
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "chat");
  expect(screen.getByLabelText("Message", { exact: true })).toHaveValue(
    "Chat draft",
  );
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "compare");
  expect(screen.getByLabelText("Comparison prompt")).toHaveValue(
    "Compare draft",
  );
  expect(
    fetcher.mock.calls.some(
      ([url, options]) =>
        options?.method === "POST" &&
        (String(url).endsWith("/runs") || String(url).endsWith("/comparisons")),
    ),
  ).toBe(false);
});

function mobileViewport() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((media: string) => ({
      matches: true,
      media,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}
async function enableCollapse() {
  await userEvent.click(screen.getByText("Options", { exact: true }));
  await userEvent.click(
    screen.getByRole("checkbox", {
      name: "Collapse after sending on this device",
    }),
  );
  await userEvent.click(screen.getByText("Options", { exact: true }));
}

test("privacy remains available when usage fails and the compact controls keep semantic labels", async () => {
  const fetcher = mockRequests(true, false, true);
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((input, options) =>
    String(input).endsWith("/usage")
      ? Promise.resolve(reply({ error: { message: "Usage unavailable" } }, 503))
      : original(input, options),
  );
  render(<App />);
  const privacy = await screen.findByRole("region", { name: "Privacy" });
  expect(privacy).toHaveTextContent("Submitted content is sent to OpenRouter");
  expect(
    screen.getAllByText(/Provider retention policies may vary/),
  ).toHaveLength(1);
  expect(
    await screen.findByLabelText("Attach files to chat"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Send message" }),
  ).toHaveTextContent("Send");
});

test("Options dismisses when the reader returns to the prompt without submitting", async () => {
  const fetcher = mockRequests(true);
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  const summary = screen.getByText("Options", { exact: true });
  await userEvent.click(summary);
  expect(summary.closest("details")).toHaveAttribute("open");
  await userEvent.click(input);
  expect(summary.closest("details")).not.toHaveAttribute("open");
  expect(
    fetcher.mock.calls.some(([url]) => String(url).endsWith("/runs")),
  ).toBe(false);
});

test.each(["button", "Enter"])(
  "mobile preference folds only an accepted %s submission and stores no credentials",
  async (method) => {
    mobileViewport();
    mockRequests(true);
    render(<App />);
    const input = await screen.findByLabelText("Message", { exact: true });
    await enableCollapse();
    await userEvent.type(input, "Hello");
    if (method === "Enter") await userEvent.keyboard("{Enter}");
    else
      await userEvent.click(
        screen.getByRole("button", { name: "Send message" }),
      );
    const write = await screen.findByRole("button", {
      name: "Write a message",
    });
    expect(input).not.toBeVisible();
    expect(localStorage.getItem("lab-chatbot.mobile-collapse")).toBe("true");
    expect(Object.keys(localStorage)).toEqual(["lab-chatbot.mobile-collapse"]);
    expect(sessionStorage.length).toBe(0);
    await userEvent.click(write);
    expect(input).toBeVisible();
    expect(input).toHaveFocus();
    expect(input).toHaveValue("");
  },
);

test("submission failure keeps the mobile draft visible and retries its original idempotency key", async () => {
  mobileViewport();
  const fetcher = mockRequests(true, true);
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  await enableCollapse();
  await userEvent.type(input, "Keep this draft");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Synthetic failure",
  );
  expect(input).toBeVisible();
  expect(input).toHaveValue("Keep this draft");
  expect(
    screen.queryByRole("button", { name: "Write a message" }),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  const posts = fetcher.mock.calls.filter(([url]) =>
    String(url).endsWith("/runs"),
  );
  expect(JSON.parse(posts[0][1]?.body as string).idempotency_key).toBe(
    JSON.parse(posts[1][1]?.body as string).idempotency_key,
  );
});

test("collapsed streaming retains cancellation and editing restores the unrelated unsent draft", async () => {
  mobileViewport();
  vi.stubGlobal(
    "EventSource",
    class {
      addEventListener() {}
      close() {}
    },
  );
  const fetcher = mockRequests(true);
  const original = fetcher.getMockImplementation()!;
  const run = {
    id: "live-run",
    conversation_id: "synthetic-conversation",
    turn: 1,
    model_id: model.id,
    model_name: model.name,
    prompt: "Hello",
    output: "Partial reply",
    status: "running",
    provider: "Mock",
    accounting_state: "reserved",
    actual_microusd: null,
    reserved_microusd: 100,
    settings: {},
    attachments: [],
  };
  fetcher.mockImplementation((input, options) => {
    const path = String(input);
    if (path.endsWith("/runs")) return Promise.resolve(reply(run));
    if (path.endsWith("/live-run/cancel"))
      return Promise.resolve(reply({ ...run, status: "cancelled" }));
    return original(input, options);
  });
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  await enableCollapse();
  await userEvent.type(input, "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByRole("button", { name: "Write a message" });
  const stop = screen.getByRole("button", { name: "Stop generation" });
  expect(stop).toBeVisible();
  await userEvent.click(stop);
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Stop generation" }),
    ).not.toBeInTheDocument(),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Write a message" }),
  );
  await userEvent.type(input, "Unsent follow-up");
  await userEvent.click(
    screen.getByRole("button", { name: "Edit as a new run" }),
  );
  expect(input).toHaveValue("Hello");
  expect(screen.getByLabelText("Attach files to chat")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));
  expect(input).toHaveValue("Unsent follow-up");
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/runs")),
  ).toHaveLength(1);
});

test("saved mobile folding preference never hides the desktop composer", async () => {
  localStorage.setItem("lab-chatbot.mobile-collapse", "true");
  mockRequests(true);
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  await userEvent.type(input, "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(input).toHaveValue(""));
  expect(input).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Write a message" }),
  ).not.toBeInTheDocument();
});

test("editing uses the saved input fork and restores the prior draft after acceptance", async () => {
  mobileViewport();
  const fetcher = mockRequests(true);
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  await enableCollapse();
  await userEvent.type(input, "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Write a message" }),
  );
  await userEvent.type(input, "Unsent follow-up");
  await userEvent.click(
    screen.getByRole("button", { name: "Edit as a new run" }),
  );
  await userEvent.clear(input);
  await userEvent.keyboard("{Enter}");
  expect(
    fetcher.mock.calls.filter(([url]) => String(url).endsWith("/runs")),
  ).toHaveLength(1);
  await userEvent.type(input, "Edited hello");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await userEvent.click(
    await screen.findByRole("button", { name: "Continue draft" }),
  );
  expect(input).toHaveValue("Unsent follow-up");
  const posts = fetcher.mock.calls.filter(([url]) =>
    String(url).endsWith("/runs"),
  );
  expect(posts).toHaveLength(2);
  expect(JSON.parse(posts[1][1]?.body as string)).toMatchObject({
    retry_of: "synthetic-run",
    prompt: "Edited hello",
    attachment_ids: [],
  });
});

test("a draft changed while awaiting acknowledgement is neither cleared nor folded", async () => {
  mobileViewport();
  const fetcher = mockRequests(true),
    original = fetcher.getMockImplementation()!;
  let release: (() => void) | undefined;
  fetcher.mockImplementation((input, options) => {
    const response = original(input, options);
    return String(input).endsWith("/runs")
      ? new Promise((resolve) => {
          release = () => resolve(response);
        })
      : response;
  });
  render(<App />);
  const input = await screen.findByLabelText("Message", { exact: true });
  await enableCollapse();
  await userEvent.type(input, "Hello");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(release).toBeTypeOf("function"));
  await userEvent.type(input, " next draft");
  release!();
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Send message" }),
    ).toHaveTextContent("Send"),
  );
  expect(input).toBeVisible();
  expect(input).toHaveValue("Hello next draft");
  expect(
    screen.queryByRole("button", { name: "Write a message" }),
  ).not.toBeInTheDocument();
});

test("New conversation clears old drafts, settings, feedback and comparison input", async () => {
  const fetcher = mockRequests(true, true);
  render(<App />);
  const option = (label: string) =>
    within(
      screen
        .getByLabelText("Message", { exact: true })
        .closest(".compact-picker") as HTMLElement,
    ).getByLabelText(label);
  await screen.findByLabelText("Message", { exact: true });
  await userEvent.selectOptions(
    screen.getByLabelText("Mode", { exact: true }),
    "compare",
  );
  await userEvent.type(
    screen.getByLabelText("Comparison prompt"),
    "Old comparison draft",
  );
  await userEvent.selectOptions(
    screen.getByLabelText("Mode", { exact: true }),
    "chat",
  );
  await userEvent.click(screen.getByText("Options", { exact: true }));
  await userEvent.type(option("System prompt"), "Old context");
  await userEvent.clear(option("Maximum output tokens"));
  await userEvent.type(option("Maximum output tokens"), "128");
  await userEvent.type(
    screen.getByLabelText("Message", { exact: true }),
    "Old failed draft",
  );
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Synthetic failure",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "New conversation" }),
  );
  expect(screen.getByLabelText("Message", { exact: true })).toHaveValue("");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  await userEvent.click(screen.getByText("Options", { exact: true }));
  expect(option("System prompt")).toHaveValue("");
  expect(option("Maximum output tokens")).toHaveValue(2048);
  await userEvent.selectOptions(
    screen.getByLabelText("Mode", { exact: true }),
    "compare",
  );
  expect(screen.getByLabelText("Comparison prompt")).toHaveValue("");
  await userEvent.selectOptions(
    screen.getByLabelText("Mode", { exact: true }),
    "chat",
  );
  await userEvent.type(
    screen.getByLabelText("Message", { exact: true }),
    "Fresh draft",
  );
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await screen.findByRole("alert");
  const requests = fetcher.mock.calls
    .filter(([url]) => String(url).endsWith("/runs"))
    .map(([, options]) => JSON.parse(options?.body as string));
  expect(requests).toHaveLength(2);
  expect(requests[0].idempotency_key).not.toBe(requests[1].idempotency_key);
  expect(requests[1]).toMatchObject({
    prompt: "Fresh draft",
    system_prompt: "",
    max_tokens: 2048,
    attachment_ids: [],
  });
});

test("provider usage keeps unknown accounting visible without a duplicate balance reservation", async () => {
  const fetcher = mockRequests(true, false, true);
  const original = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((input, options) =>
    String(input).endsWith("/usage")
      ? Promise.resolve(
          reply({
            spend_control: "provider",
            provider_key_budget: {
              limit_usd: "9.9",
              remaining_usd: "9.8",
              used_usd: "0.1",
              checked_at: 1700000000,
            },
            daily_actual_microusd: 100000,
            outstanding_microusd: 9800000,
            uncertain_count: 1,
            simulated: false,
          }),
        )
      : original(input, options),
  );
  render(<App />);
  expect(await screen.findByText("Unknown billing records: 1")).toBeVisible();
  expect(
    screen.getByText(/Available credit comes from OpenRouter/),
  ).toBeVisible();
  expect(
    screen.queryByText(/Outstanding reservations/),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Key remaining: $9.800000")).toBeVisible();
});

test("a late history response cannot reopen a conversation after New conversation", async () => {
  const fetcher = mockRequests(true);
  const original = fetcher.getMockImplementation()!;
  let release!: (response: Response) => void;
  const delayed = new Promise<Response>((resolve) => {
    release = resolve;
  });
  fetcher.mockImplementation((input, options) => {
    const url = String(input);
    if (url.includes("/conversations?q="))
      return Promise.resolve(
        reply([{ id: "old-conversation", title: "Previous conversation" }]),
      );
    if (url.endsWith("/conversations/old-conversation")) return delayed;
    return original(input, options);
  });
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", {
      name: "Previous conversation",
    }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "New conversation" }),
  );
  await userEvent.type(
    screen.getByLabelText("Message", { exact: true }),
    "New independent draft",
  );
  await act(async () => {
    release(
      reply({
        id: "old-conversation",
        title: "Previous conversation",
        runs: [],
      }),
    );
  });
  await waitFor(() =>
    expect(screen.getByLabelText("Message", { exact: true })).toHaveValue(
      "New independent draft",
    ),
  );
  expect(
    screen.queryByRole("button", { name: "Rename conversation" }),
  ).not.toBeInTheDocument();
});
