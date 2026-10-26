import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import App from "../src/App";

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
function reply(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status });
}

function mockRequests(signedIn: boolean, previewFails = false) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, options) => {
      const url = String(input);
      if (url.endsWith("/auth/login") && options?.method === "POST")
        return reply(ownerSession);
      if (url.endsWith("/auth/login")) return reply(configuration);
      if (url.endsWith("/auth/session"))
        return signedIn ? reply(ownerSession) : reply({}, 401);
      if (url.endsWith("/dev/preview"))
        return previewFails
          ? reply({}, 503)
          : reply({ text: "Local preview: Hello", simulated: true });
      throw new Error("Unexpected route");
    });
}

test("sign-in gates the preview and credentials stay out of browser storage", async () => {
  mockRequests(false);
  render(<App />);
  expect(await screen.findByLabelText("Owner passphrase")).toBeVisible();
  expect(screen.queryByLabelText("Preview prompt")).not.toBeInTheDocument();
  await userEvent.type(
    screen.getByLabelText("Owner passphrase"),
    "synthetic-browser-passphrase",
  );
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByLabelText("Preview prompt")).toBeVisible();
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
});

test("preview submission is deliberate and visibly simulated", async () => {
  const fetcher = mockRequests(true);
  render(<App />);
  await userEvent.type(await screen.findByLabelText("Preview prompt"), "Hello");
  expect(
    fetcher.mock.calls.some(([url]) => String(url).endsWith("/dev/preview")),
  ).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: /Run preview/ }));
  expect(await screen.findByText("Local preview: Hello")).toBeVisible();
  const submission = fetcher.mock.calls.find(([url]) =>
    String(url).endsWith("/dev/preview"),
  );
  expect(submission?.[1]?.headers).toMatchObject({
    "X-CSRF-Token": "synthetic-csrf",
  });
});

test("a failed preview preserves its draft for explicit retry", async () => {
  mockRequests(true, true);
  render(<App />);
  await userEvent.type(
    await screen.findByLabelText("Preview prompt"),
    "Keep my draft",
  );
  await userEvent.click(screen.getByRole("button", { name: /Run preview/ }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Try again"),
  );
  expect(screen.getByLabelText("Preview prompt")).toHaveValue("Keep my draft");
});
