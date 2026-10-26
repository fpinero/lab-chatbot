import { render, screen } from "@testing-library/react";
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

function mockRequests(signedIn: boolean, fails = false) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, options) => {
      const url = String(input);
      if (url.endsWith("/auth/login") && options?.method === "POST")
        return reply(ownerSession);
      if (url.endsWith("/auth/login")) return reply(configuration);
      if (url.endsWith("/auth/session"))
        return signedIn ? reply(ownerSession) : reply({}, 401);
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
          daily_actual_microusd: 0,
          outstanding_microusd: 0,
          uncertain_count: 0,
          simulated: true,
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
