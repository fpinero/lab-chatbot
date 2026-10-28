import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
}
async function copyImage(page: Page) {
  await page.evaluate(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 240;
    canvas.height = 120;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#345d4d";
    context.fillRect(0, 0, 240, 120);
    context.fillStyle = "#ffffff";
    context.font = "18px sans-serif";
    context.fillText("Clipboard fixture", 24, 65);
    const blob = await new Promise<Blob>((resolve) =>
      canvas.toBlob((value) => resolve(value!), "image/png"),
    );
    await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
  });
}
function generations(page: Page) {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      ["/api/runs", "/api/comparisons", "/api/images/jobs"].includes(
        new URL(request.url()).pathname,
      )
    )
      requests.push(request.url());
  });
  return requests;
}

test("native desktop clipboard paste preserves text and attaches only after explicit Send", async ({
  page,
}) => {
  const posts = generations(page);
  await page.route("**/api/models", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.models.push({
      ...data.models[0],
      id: "mock/text-only",
      name: "Local text only",
      input_modalities: ["text"],
    });
    await route.fulfill({ response, json: data });
  });
  await signIn(page);
  const input = page.getByLabel("Message", { exact: true });
  const picker = page.locator(".compact-picker");
  await input.fill("Clipboard prompt");
  await page.evaluate(() => navigator.clipboard.writeText(" with normal text"));
  await input.press("End");
  await input.press("ControlOrMeta+V");
  await expect(input).toHaveValue("Clipboard prompt with normal text");
  await expect(picker.locator(".attachment-item")).toHaveCount(0);
  await copyImage(page);
  await input.press("ControlOrMeta+V");
  await expect(picker.locator(".attachment-item")).toHaveCount(1);
  await expect(picker.locator(".attachment-item img")).toBeVisible();
  await expect(picker).toContainText(
    "Image normalized to WebP; metadata removed.",
  );
  await expect(input).toHaveValue("Clipboard prompt with normal text");
  expect(posts).toHaveLength(0);
  const model = page.getByRole("combobox", { name: "Model", exact: true });
  await model.fill("text only");
  await page.getByRole("option", { name: /Local text only/ }).click();
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("support image input");
  await model.fill("steady");
  await page.getByRole("option", { name: /Local steady/ }).click();
  await page.screenshot({
    path: "../artifacts/clipboard-desktop.png",
    fullPage: true,
  });
  await picker.getByRole("button", { name: /Remove from draft/ }).click();
  await expect(picker.locator(".attachment-item")).toHaveCount(0);
  await input.press("ControlOrMeta+V");
  await expect(picker.locator(".attachment-item")).toHaveCount(1);
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      new URL(r.url()).pathname === "/api/runs",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const saved = await (await response).json();
  expect(saved.attachments).toHaveLength(1);
  expect(saved.attachments[0].display_name).toMatch(/^pasted-image-.*\.png$/);
  expect(posts).toHaveLength(1);
  await expect(picker.locator(".attachment-item")).toHaveCount(0);
  await expect(page.locator(".turn .attachment-item")).toHaveCount(1);
});

test("Compare and Image paste uses real uploads, preserves drafts and allows retry", async ({
  page,
}) => {
  const posts = generations(page);
  await signIn(page);
  await copyImage(page);
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  const comparison = page.getByRole("region", { name: "Compare", exact: true });
  const prompt = comparison.getByLabel("Comparison prompt");
  await prompt.fill("Compare this screenshot");
  let reject = true;
  await page.route("**/api/attachments", async (route) => {
    if (route.request().method() === "POST" && reject) {
      reject = false;
      await route.fulfill({
        status: 503,
        json: { error: { message: "Synthetic temporary upload failure" } },
      });
    } else await route.continue();
  });
  await prompt.press("ControlOrMeta+V");
  await expect(comparison.getByRole("alert")).toContainText(
    "Synthetic temporary upload failure",
  );
  await expect(prompt).toHaveValue("Compare this screenshot");
  await prompt.press("ControlOrMeta+V");
  await expect(comparison.locator(".attachment-item")).toHaveCount(1);
  await expect(comparison.getByRole("alert")).toHaveCount(0);
  await page.getByLabel("Mode", { exact: true }).selectOption("images");
  const images = page.getByRole("region", { name: "Image", exact: true });
  const imagePrompt = images.getByLabel("Image prompt", { exact: true });
  await imagePrompt.fill("Use this as a reference");
  await imagePrompt.press("ControlOrMeta+V");
  await expect(images.locator(".attachment-item")).toHaveCount(1);
  await expect(imagePrompt).toHaveValue("Use this as a reference");
  await page.getByLabel("Mode", { exact: true }).selectOption("chat");
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(0);
  await page.getByLabel("Mode", { exact: true }).selectOption("compare");
  await expect(prompt).toHaveValue("Compare this screenshot");
  await expect(comparison.locator(".attachment-item")).toHaveCount(1);
  expect(posts).toHaveLength(0);
});
