import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
}

test("copy feedback confirms exact response/code content, expires and permits retry", async ({
  page,
}, info) => {
  await signIn(page);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  let generations = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/runs")
      generations++;
  });
  const input = page.getByLabel("Message", { exact: true });
  await input.fill(
    `Copy feedback ${info.project.name}\n\n\`\`\`js\nconst example = 42;\n\`\`\``,
  );
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      new URL(r.url()).pathname === "/api/runs",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const run = await (await response).json();
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  const saved = await (await page.request.get(`/api/runs/${run.id}`)).json();
  await input.fill("Keep this draft while copying");
  const button = page.getByRole("button", {
    name: "Copy response",
    exact: true,
  });
  const before = (await button.boundingBox())!.width;
  await button.click();
  await expect(button).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    saved.output,
  );
  expect((await button.boundingBox())!.width).toBeCloseTo(before, 0);
  await page.screenshot({
    path: `../artifacts/ui1-copy-${info.project.name}.png`,
    fullPage: true,
  });
  await expect(button).toHaveText("Copy response", { timeout: 4000 });
  const code = page.locator(".code-block");
  const codeText = await code.locator("pre").innerText();
  await code.getByRole("button", { name: "Copy code", exact: true }).click();
  await expect(
    code.getByRole("button", { name: "Copy code", exact: true }),
  ).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    codeText,
  );
  await page.evaluate(() =>
    Object.defineProperty(navigator.clipboard, "writeText", {
      configurable: true,
      value: async () => {
        throw new DOMException("Synthetic denied", "NotAllowedError");
      },
    }),
  );
  await button.click();
  await expect(page.getByRole("alert")).toContainText(
    "Select the response text",
  );
  await expect(button).toHaveText("Copy response");
  await page.evaluate(() =>
    Reflect.deleteProperty(navigator.clipboard, "writeText"),
  );
  await button.click();
  await expect(button).toHaveText("Copied");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(input).toHaveValue("Keep this draft while copying");
  expect(generations).toBe(1);
});
