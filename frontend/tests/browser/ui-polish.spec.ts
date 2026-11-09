import { expect, test, type Page } from "@playwright/test";
import type { CatalogInfo, ImageCatalogInfo } from "../../src/lib/api";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
}

test("sidebar logo toggles reclaim desktop space and preserve drafts through responsive transitions", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 1100, height: 800 });
  await signIn(page);
  const posts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST")
      posts.push(new URL(request.url()).pathname);
  });
  const sidebar = page.getByRole("complementary", { name: "Navigation" });
  const draft = page.getByLabel("Message", { exact: true });
  const show = page.getByRole("button", { name: "Show sidebar", exact: true });
  const hide = page.getByRole("button", { name: "Hide sidebar", exact: true });
  await draft.fill("Preserve this draft while arranging two browser windows");
  await page.getByText("Options", { exact: true }).click();
  await page
    .getByRole("textbox", { name: "System prompt", exact: true })
    .fill("Keep these instructions");
  const before = (await page.locator(".chat-workspace > main").boundingBox())!
    .width;
  await hide.focus();
  await hide.press("Enter");
  await expect(sidebar).toBeHidden();
  await expect(show).toBeFocused();
  await expect(show).toHaveAttribute("aria-expanded", "false");
  expect(
    (await page.locator(".chat-workspace > main").boundingBox())!.width,
  ).toBeGreaterThan(before + 240);
  const bounds = (await show.boundingBox())!;
  expect(bounds.width).toBeGreaterThanOrEqual(44);
  expect(bounds.height).toBeGreaterThanOrEqual(44);
  await expect(draft).toHaveValue(
    "Preserve this draft while arranging two browser windows",
  );
  await page.getByText("Options", { exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "System prompt", exact: true }),
  ).toHaveValue("Keep these instructions");
  await draft.click();
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.screenshot({
      path: `../artifacts/sidebar-collapsed-${info.project.name}-${scheme}.png`,
    });
  }
  await show.press("Enter");
  await expect(sidebar).toBeVisible();
  await expect(hide).toBeFocused();
  await hide.click();
  await page.reload();
  await expect(show).toBeVisible();
  await expect(sidebar).toBeHidden();
  await draft.fill("Keep this draft while resizing");
  for (const width of [960, 761, 760, 412, 360]) {
    await page.setViewportSize({ width, height: 800 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(draft).toHaveValue("Keep this draft while resizing");
  }
  const mobileOpen = page.getByRole("button", {
    name: "Open navigation",
    exact: true,
  });
  await expect(mobileOpen).toBeVisible();
  await mobileOpen.click();
  await expect(sidebar).toBeVisible();
  await expect(hide).toBeFocused();
  await hide.press("Escape");
  await expect(sidebar).toBeHidden();
  await expect(mobileOpen).toBeFocused();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("lab-chatbot.sidebar-collapsed"),
    ),
  ).toBe("true");
  await mobileOpen.click();
  await page.setViewportSize({ width: 960, height: 800 });
  await expect(sidebar).toBeHidden();
  await expect(show).toBeFocused();
  await show.click();
  await expect(sidebar).toBeVisible();
  await page.setViewportSize({ width: 412, height: 800 });
  await expect(sidebar).toBeHidden();
  await mobileOpen.click();
  await page
    .getByRole("button", { name: "Close navigation", exact: true })
    .click();
  await page.setViewportSize({ width: 960, height: 800 });
  await expect(sidebar).toBeVisible();
  expect(posts).toEqual([]);
});

test("attachment-only Chat applies System prompt and supports empty-text replay and edits", async ({
  page,
}, info) => {
  await signIn(page);
  const draft = page.getByLabel("Message", { exact: true });
  const send = page.getByRole("button", { name: "Send message", exact: true });
  const options = page.getByText("Options", { exact: true });
  await expect(send).toBeDisabled();
  await options.click();
  await page
    .locator(".chat-composer")
    .getByRole("textbox", { name: "System prompt", exact: true })
    .fill("Analyze only the current screenshot");
  await page
    .getByRole("checkbox", { name: "Send without previous context" })
    .check();
  await expect(send).toBeDisabled();
  await draft.click();
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 24;
    canvas.height = 16;
    canvas.getContext("2d")!.fillRect(0, 0, 24, 16);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("Attach files to chat", { exact: true }).setInputFiles({
    name: "image-only.png",
    mimeType: "image/png",
    buffer: Buffer.from(png, "base64"),
  });
  await expect(send).toBeEnabled();
  await options.click();
  const system = page.getByRole("textbox", {
    name: "System prompt",
    exact: true,
  });
  await system.fill("");
  await expect(send).toBeDisabled();
  await system.fill(" \n\t");
  await expect(send).toBeDisabled();
  await draft.fill("Analyze this screenshot");
  await expect(send).toBeEnabled();
  await draft.fill("");
  await expect(send).toBeDisabled();
  await options.click();
  await system.fill("Analyze only the current screenshot");
  await expect(send).toBeEnabled();
  await draft.click();
  await expect(draft).toHaveValue("");
  await page.screenshot({
    path: `../artifacts/attachment-only-${info.project.name}.png`,
  });
  const request = page.waitForRequest(
    (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/runs",
  );
  await send.click();
  expect((await request).postDataJSON()).toMatchObject({
    prompt: "",
    system_prompt: "Analyze only the current screenshot",
    without_context: true,
  });
  await expect(
    page.locator("article.answer").last().getByRole("status"),
  ).toHaveText("Completed");
  await expect(send).toBeDisabled();
  await expect(page.locator(".compact-picker .attachment-item")).toHaveCount(0);
  await expect(page.locator("article.answer .attachment-item")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Copy prompt", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  if (info.project.use.hasTouch)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "image-only.png", exact: true })
    .click();
  await expect(page.locator("article.answer")).toHaveCount(1);
  await page
    .getByRole("button", { name: "Repeat with selected model", exact: true })
    .click();
  await expect(page.locator("article.answer")).toHaveCount(2);
  await expect(
    page.locator("article.answer").last().getByRole("status"),
  ).toHaveText("Completed");
  await options.click();
  await page
    .getByRole("textbox", { name: "System prompt", exact: true })
    .fill("");
  await draft.click();
  await page
    .getByRole("button", { name: "Edit as a new run", exact: true })
    .last()
    .click();
  await expect(draft).toHaveValue("");
  await expect(send).toBeEnabled();
  await send.click();
  await expect(page.locator("article.answer")).toHaveCount(3);
  await expect(
    page.locator("article.answer").last().getByRole("status"),
  ).toHaveText("Completed");
  await expect(send).toBeDisabled();
});

test("independent Chat mode stays compact, restores from history and resets for a new conversation", async ({
  page,
}, info) => {
  await signIn(page);
  const requests: { without_context: boolean; prompt: string }[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/runs"
    )
      requests.push(request.postDataJSON());
  });
  const draft = page.getByLabel("Message", { exact: true });
  const options = page.getByText("Options", { exact: true });
  const checkbox = page.getByRole("checkbox", {
    name: "Send without previous context",
  });
  await options.click();
  await expect(checkbox).not.toBeChecked();
  const title = `Baseline context ${info.project.name}`;
  await draft.fill(title);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.locator("article.answer").last().getByRole("status"),
  ).toHaveText("Completed");
  await options.click();
  await checkbox.check();
  const bounds = (await checkbox.locator("..").boundingBox())!;
  expect(bounds.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({
    path: `../artifacts/independent-options-${info.project.name}.png`,
  });
  expect(requests).toHaveLength(1);
  await draft.fill("Analyze only this unrelated input");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator("article.answer")).toHaveCount(2);
  await expect(
    page.locator("article.answer").last().getByRole("status"),
  ).toHaveText("Completed");
  expect(requests[1].without_context).toBe(true);
  expect(requests[0].without_context).toBe(false);
  await page.reload();
  await expect(draft).toBeVisible();
  if (info.project.use.hasTouch)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: title, exact: true }).click();
  await expect(page.locator("article.answer")).toHaveCount(2);
  await options.click();
  await expect(checkbox).toBeChecked();
  await checkbox.uncheck();
  await draft.fill("Use saved textual context again");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator("article.answer")).toHaveCount(3);
  await expect(
    page.locator("article.answer").last().getByRole("status"),
  ).toHaveText("Completed");
  expect(requests[2].without_context).toBe(false);
  await options.click();
  await checkbox.check();
  if (info.project.use.hasTouch)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await options.click();
  await expect(checkbox).not.toBeChecked();
  await expect(draft).toHaveValue("");
  expect(requests).toHaveLength(3);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("favorites persist without changing startup selection and catalog refresh recovers with local feedback", async ({
  page,
}, info) => {
  const generations: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      ["/api/runs", "/api/comparisons", "/api/images/jobs"].includes(
        new URL(request.url()).pathname,
      )
    )
      generations.push(request.url());
  });
  let chatCatalog!: CatalogInfo;
  let imageCatalog!: ImageCatalogInfo;
  await page.route("**/api/models", async (route) => {
    const response = await route.fetch();
    chatCatalog = { ...(await response.json()), refresh_after_seconds: 1 };
    await route.fulfill({ response, json: chatCatalog });
  });
  await page.route("**/api/images/models", async (route) => {
    const response = await route.fetch();
    imageCatalog = { ...(await response.json()), refresh_after_seconds: 1 };
    await route.fulfill({ response, json: imageCatalog });
  });
  let attempts = 0;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/models/refresh", async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await pending;
      await route.fulfill({
        status: 503,
        headers: { "Retry-After": "2" },
        json: { error: { message: "Synthetic catalog refresh failure" } },
      });
    } else if (attempts === 2) {
      await route.fulfill({
        status: 429,
        headers: { "Retry-After": "1" },
        json: { error: { message: "Synthetic catalog rate limit" } },
      });
    } else {
      await route.fulfill({
        json: {
          ...chatCatalog,
          fetched_at: chatCatalog.fetched_at + 180,
          refresh_after_seconds: 2,
        },
      });
    }
  });
  await signIn(page);
  const picker = page.getByRole("combobox", { name: "Model", exact: true });
  await picker.fill("clear");
  await page.getByRole("option", { name: /Local clear/ }).click();
  await page.getByText("Options", { exact: true }).click();
  await page
    .getByRole("button", { name: "Add to favorites", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Remove from favorites", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await picker.click();
  await expect(
    page
      .getByRole("listbox", { name: "Model", exact: true })
      .getByRole("option")
      .first(),
  ).toContainText("Favorites: Local clear");
  await picker.press("Escape");
  await page.reload();
  await expect(picker).toHaveValue("Local steady");
  await picker.fill("clear");
  await page.getByRole("option", { name: /Local clear/ }).click();
  const draft = page.getByLabel("Message", { exact: true });
  await draft.fill("Keep this prompt while refreshing the catalog");
  await page.getByText("Options", { exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Remove from favorites", exact: true }),
  ).toBeVisible();
  const options = page.locator(".composer-options-content").first();
  const control = options.locator(".catalog-refresh");
  const refresh = control.getByRole("button", {
    name: "Refresh models",
    exact: true,
  });
  const timestamp = await options
    .locator("p")
    .filter({ hasText: "Refreshed:" })
    .textContent();
  await expect(refresh).toBeEnabled();
  await refresh.click();
  await expect(refresh).toHaveText("Refreshing models...");
  await refresh.evaluate((button: HTMLButtonElement) => button.click());
  expect(attempts).toBe(1);
  if (info.project.use.hasTouch)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(draft).toHaveValue("");
  await draft.fill("Keep this prompt while refreshing the catalog");
  await page.getByText("Options", { exact: true }).click();
  await expect(refresh).toHaveText("Refreshing models...");
  expect(attempts).toBe(1);
  release();
  await expect(control.getByRole("alert")).toHaveText(
    "Synthetic catalog refresh failure",
  );
  await expect(page.locator(".chat-composer > .error")).toHaveCount(0);
  await expect(refresh).toBeEnabled();
  await refresh.click();
  await expect(control.getByRole("alert")).toHaveCount(0);
  await expect(control.getByRole("status")).toContainText("refreshed recently");
  await expect(refresh).toBeEnabled();
  await expect(control.getByRole("status")).toHaveCount(0);
  await refresh.click();
  await expect(control.getByRole("status")).toHaveText("Models refreshed.");
  await expect(
    options.locator("p").filter({ hasText: "Refreshed:" }),
  ).not.toHaveText(timestamp!);
  await expect(picker).toHaveValue("Local clear");
  await expect(draft).toHaveValue(
    "Keep this prompt while refreshing the catalog",
  );
  await page.screenshot({
    path: `../artifacts/catalog-refresh-${info.project.name}.png`,
  });
  await page
    .getByRole("button", { name: "Remove from favorites", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Add to favorites", exact: true }),
  ).toBeVisible();
  let imageAttempts = 0;
  await page.route("**/api/images/models/refresh", async (route) => {
    imageAttempts += 1;
    if (imageAttempts === 1)
      await route.fulfill({
        status: 429,
        headers: { "Retry-After": "1" },
        json: { error: { message: "Synthetic image catalog limit" } },
      });
    else if (imageAttempts === 2)
      await route.fulfill({
        status: 503,
        headers: { "Retry-After": "1" },
        json: { error: { message: "Synthetic image catalog failure" } },
      });
    else
      await route.fulfill({
        json: {
          ...imageCatalog,
          fetched_at: imageCatalog.fetched_at + 180,
          refresh_after_seconds: 1,
        },
      });
  });
  await page.getByLabel("Mode", { exact: true }).selectOption("images");
  const region = page.getByRole("region", { name: "Image", exact: true });
  const imageDraft = region.getByLabel("Image prompt", { exact: true });
  await imageDraft.fill("Keep this image prompt");
  const imageControl = region.locator(".catalog-refresh");
  const imageRefresh = imageControl.getByRole("button", {
    name: "Refresh models",
    exact: true,
  });
  await expect(imageRefresh).toBeEnabled();
  await imageRefresh.click();
  await expect(imageControl.getByRole("status")).toContainText(
    "refreshed recently",
  );
  await expect(imageRefresh).toBeEnabled();
  await imageRefresh.click();
  await expect(imageControl.getByRole("alert")).toHaveText(
    "Synthetic image catalog failure",
  );
  await expect(imageRefresh).toBeEnabled();
  await imageRefresh.click();
  await expect(imageControl.getByRole("alert")).toHaveCount(0);
  await expect(imageControl.getByRole("status")).toHaveText(
    "Models refreshed.",
  );
  await expect(imageDraft).toHaveValue("Keep this image prompt");
  await page.unrouteAll({ behavior: "wait" });
  expect(generations).toHaveLength(0);
});

test("attachment help keeps the composer clean and opens with touch or keyboard without submitting", async ({
  page,
}, info) => {
  const generations: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      ["/api/runs", "/api/comparisons", "/api/images/jobs"].includes(
        new URL(request.url()).pathname,
      )
    )
      generations.push(request.url());
  });
  await page.route("**/api/attachments/limits", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), spend_control: "provider" },
    });
  });
  await signIn(page);
  const draft = page.getByLabel("Message", { exact: true });
  await draft.fill("Preserve this prompt while reading attachment help");
  const picker = page.locator(".compact-picker");
  const trigger = picker.getByRole("button", {
    name: "About attachments",
    exact: true,
  });
  const panel = picker.locator(".attachment-help-popover");
  await expect(panel).toBeHidden();
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 80;
    canvas.height = 48;
    canvas.getContext("2d")!.fillRect(0, 0, 80, 48);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.getByLabel("Attach files to chat", { exact: true }).setInputFiles({
    name: "synthetic-help.png",
    mimeType: "image/png",
    buffer: Buffer.from(png, "base64"),
  });
  await expect(picker.locator(".attachment-item")).toHaveCount(1);
  await expect(picker.locator(".attachment-feedback")).not.toContainText(
    "Documents are extracted locally",
  );
  await expect(picker.locator(".attachment-feedback")).not.toContainText(
    "Uses the shared OpenRouter key budget",
  );
  const before = (await picker.boundingBox())!;
  const triggerBounds = (await trigger.boundingBox())!;
  expect(triggerBounds.width).toBeGreaterThanOrEqual(44);
  expect(triggerBounds.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({
    path: `../artifacts/attachment-help-closed-${info.project.name}.png`,
  });
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    if (info.project.use.hasTouch) await trigger.tap();
    else {
      await trigger.focus();
      await trigger.press("Enter");
    }
    await expect(panel).toBeVisible();
    await expect(
      page.getByRole("note", { name: "About attachments" }),
    ).toBeVisible();
    await expect(panel).toContainText(
      "Documents are extracted locally and sent as text",
    );
    await expect(panel).toContainText("Uses the shared OpenRouter key budget");
    const bounds = (await panel.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(
      page.viewportSize()!.width,
    );
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(
      page.viewportSize()!.height,
    );
    expect((await picker.boundingBox())!.height).toBe(before.height);
    await page.screenshot({
      path: `../artifacts/attachment-help-open-${scheme}-${info.project.name}.png`,
    });
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(trigger).toBeFocused();
  }
  await trigger.click();
  await page
    .getByRole("heading", { name: "A little room for big ideas.", exact: true })
    .click();
  await expect(panel).toBeHidden();
  await draft.click();
  await expect(draft).toBeFocused();
  await trigger.click();
  await panel.getByRole("button", { name: "Close attachment help" }).click();
  await expect(panel).toBeHidden();
  await expect(trigger).toBeFocused();
  await expect(draft).toHaveValue(
    "Preserve this prompt while reading attachment help",
  );
  await expect(picker.locator(".attachment-item")).toHaveCount(1);
  for (const mode of ["compare", "images"] as const) {
    await page.getByLabel("Mode", { exact: true }).selectOption(mode);
    const region = page.getByRole("region", {
      name: mode === "compare" ? "Compare" : "Image",
      exact: true,
    });
    const help = region.locator(".attachment-help-popover");
    await region
      .getByRole("button", { name: "About attachments", exact: true })
      .click();
    await expect(help).toBeVisible();
    await expect(help).toContainText(
      mode === "compare"
        ? "Documents are extracted locally"
        : "Reference images are sent to the selected generation provider",
    );
    await page.keyboard.press("Escape");
    await expect(help).toBeHidden();
  }
  await page.unrouteAll({ behavior: "wait" });
  expect(generations).toHaveLength(0);
});

test("prompt Enter follows input capabilities across narrow desktop and wide touch layouts", async ({
  page,
}, info) => {
  const touch = info.project.use.hasTouch === true;
  const posts: string[] = [];
  await page.route("**/api/runs", async (route) => {
    posts.push(route.request().postData()!);
    await route.fulfill({
      status: 503,
      json: { error: { message: "Synthetic keyboard submission" } },
    });
  });
  await signIn(page);
  const input = page.getByLabel("Message", { exact: true });
  const send = page.getByRole("button", { name: "Send message", exact: true });
  expect(
    await page.evaluate(
      () => matchMedia("(hover: hover) and (pointer: fine)").matches,
    ),
  ).toBe(!touch);
  await expect(input).toHaveAttribute("enterkeyhint", touch ? "enter" : "send");
  await input.fill("First paragraph");
  await input.press(touch ? "Enter" : "Shift+Enter");
  await expect(input).toHaveValue("First paragraph\n");
  expect(posts).toHaveLength(0);
  await input.pressSequentially("Second paragraph");
  await input.dispatchEvent("keydown", { key: "Enter", isComposing: true });
  await input.dispatchEvent("keydown", { key: "Enter", keyCode: 229 });
  expect(posts).toHaveLength(0);
  await page.setViewportSize(
    touch ? { width: 1100, height: 800 } : { width: 412, height: 740 },
  );
  await expect(input).toHaveAttribute("enterkeyhint", touch ? "enter" : "send");
  await expect(send).toBeVisible();
  await expect(send).toBeEnabled();
  if (touch) {
    await input.press("End");
    await input.press("Enter");
    await input.press("Enter");
    await input.press("T");
    await expect(input).toHaveValue("First paragraph\nSecond paragraph\n\nT");
    expect(posts).toHaveLength(0);
    await send.click();
  } else {
    await input.press("Enter");
  }
  await expect(page.getByRole("alert")).toHaveText(
    "Synthetic keyboard submission",
  );
  expect(posts).toHaveLength(1);
  const expected = touch
    ? "First paragraph\nSecond paragraph\n\nT"
    : "First paragraph\nSecond paragraph";
  expect(JSON.parse(posts[0]).prompt).toBe(expected);
  await expect(input).toHaveValue(expected);
  await page.screenshot({
    path: `../artifacts/enter-${info.project.name}.png`,
  });
});

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
  await input.fill("Typing after code copy must keep its confirmation");
  await expect(
    code.getByRole("button", { name: "Copy code", exact: true }),
  ).toHaveText("Copied");
  await input.fill("Keep this draft while copying");
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

test("long prompts keep an exterior focus cue and bounded scrolling without hiding actions", async ({
  page,
}, info) => {
  await signIn(page);
  const input = page.getByLabel("Message", { exact: true });
  const frame = page.locator("#composer-editor");
  const text = Array.from(
    { length: 45 },
    (_, i) => `Synthetic prompt line ${i + 1}: ${"long-input-".repeat(12)}`,
  ).join("\n");
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.getByLabel("Mode", { exact: true }).focus();
    const inactiveBorder = await frame.evaluate(
      (element) => getComputedStyle(element).borderTopColor,
    );
    await input.fill(text);
    await input.focus();
    await expect(input).toHaveCSS("outline-style", "none");
    const state = await input.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        height: element.getBoundingClientRect().height,
        max: parseFloat(style.maxHeight),
        scroll: element.scrollHeight,
        client: element.clientHeight,
        wide: element.scrollWidth > element.clientWidth,
        overflow: style.overflowY,
      };
    });
    expect(state.height).toBeLessThanOrEqual(state.max + 1);
    expect(state.scroll).toBeGreaterThan(state.client);
    expect(state.overflow).toBe("auto");
    expect(state.wide).toBe(false);
    expect(
      await frame.evaluate(
        (element) => getComputedStyle(element).borderTopColor,
      ),
    ).not.toBe(inactiveBorder);
    expect(
      (await input.boundingBox())!.y - (await frame.boundingBox())!.y,
    ).toBeGreaterThanOrEqual(6);
    expect(
      await frame.evaluate((element) => getComputedStyle(element).boxShadow),
    ).not.toBe("none");
    await expect(
      page.getByRole("button", { name: "Send message", exact: true }),
    ).toBeInViewport();
    await input.evaluate((element) => {
      element.scrollTop = 0;
    });
    expect(await input.evaluate((element) => element.scrollTop)).toBe(0);
    await input.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    expect(
      await input.evaluate((element) => element.scrollTop),
    ).toBeGreaterThan(0);
    await page.screenshot({
      path: `../artifacts/ui2-prompt-${info.project.name}-${scheme}.png`,
      fullPage: true,
    });
  }
  // A 640x450 CSS viewport exercises the reflow geometry of 1280x900 at 200% zoom.
  const width =
    info.project.name === "polish-desktop"
      ? 640
      : info.project.name === "polish-mobile"
        ? 360
        : 412;
  await page.setViewportSize({ width, height: 450 });
  await expect(
    page.getByRole("button", { name: "Send message", exact: true }),
  ).toBeInViewport();
  await page.getByText("Options", { exact: true }).click();
  const options = page.locator(".composer-options-content").first();
  await expect(options).toBeInViewport();
  const bounds = (await options.boundingBox())!;
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(451);
  await input.focus();
  await expect(page.locator(".composer-options").first()).not.toHaveAttribute(
    "open",
  );
  await expect(input).toHaveValue(text);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await input.fill("Short again");
  expect((await input.boundingBox())!.height).toBeLessThan(70);
  await input.press("Tab");
  await expect(page.getByLabel("Attach files to chat")).toBeFocused();
});

test("draft card remove buttons replace wrong files without changing text or saved history", async ({
  page,
}, info) => {
  await signIn(page);
  const generated: string[] = [],
    deleted: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (
      request.method() === "POST" &&
      ["/api/runs", "/api/comparisons", "/api/images/jobs"].includes(path)
    )
      generated.push(path);
    if (request.method() === "DELETE" && path.startsWith("/api/attachments"))
      deleted.push(path);
  });
  const png = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 80;
    canvas.height = 48;
    canvas.getContext("2d")!.fillRect(0, 0, 80, 48);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  const upload = async (label: string, names: string[]) => {
    const response = page.waitForResponse(
      (r) =>
        r.request().method() === "POST" &&
        new URL(r.url()).pathname === "/api/attachments",
    );
    await page.getByLabel(label, { exact: true }).setInputFiles(
      names.map((name) => ({
        name,
        mimeType: "image/png",
        buffer: Buffer.from(png, "base64"),
      })),
    );
    return (await (await response).json()) as {
      id: string;
      display_name: string;
    }[];
  };
  const draft = page.getByLabel("Message", { exact: true });
  const text = `Preserve this prompt ${info.project.name}`;
  await draft.fill(text);
  const initial = await upload("Attach files to chat", [
    `wrong-${"long-name-".repeat(10)}.png`,
    "also-wrong.png",
  ]);
  const picker = page.locator(".compact-picker");
  await expect(picker.locator(".attachment-item")).toHaveCount(2);
  const remove = picker.locator(".attachment-remove");
  const bounds = (await remove.first().boundingBox())!;
  expect(bounds.width).toBeGreaterThanOrEqual(44);
  expect(bounds.height).toBeGreaterThanOrEqual(44);
  await page.screenshot({
    path: `../artifacts/ui3-draft-${info.project.name}.png`,
    fullPage: true,
  });
  await remove.first().click();
  await expect(picker.locator(".attachment-item")).toHaveCount(1);
  await expect(remove.first()).toBeFocused();
  await expect(draft).toHaveValue(text);
  await remove.first().click();
  await expect(picker.locator(".attachment-item")).toHaveCount(0);
  await expect(
    page.getByLabel("Attach files to chat", { exact: true }),
  ).toBeFocused();
  const correct = await upload("Attach files to chat", ["correct.png"]);
  await expect(picker.locator(".attachment-item")).toHaveCount(1);
  for (const mode of ["compare", "images"] as const) {
    await page.getByLabel("Mode", { exact: true }).selectOption(mode);
    const region = page.getByRole("region", {
      name: mode === "compare" ? "Compare" : "Image",
      exact: true,
    });
    const input = region.getByLabel(
      mode === "compare" ? "Comparison prompt" : "Image prompt",
      { exact: true },
    );
    await input.fill(`Preserve ${mode} draft`);
    await upload(
      mode === "compare"
        ? "Attach files to comparison"
        : "Attach reference images",
      [`wrong-${mode}.png`],
    );
    await expect(region.locator(".attachment-item")).toHaveCount(1);
    await region.getByRole("button", { name: /Remove from draft/ }).click();
    await expect(region.locator(".attachment-item")).toHaveCount(0);
    await expect(input).toHaveValue(`Preserve ${mode} draft`);
  }
  await page.getByLabel("Mode", { exact: true }).selectOption("chat");
  await expect(draft).toHaveValue(text);
  await expect(picker.locator(".attachment-item strong")).toHaveText(
    "correct.png",
  );
  expect(generated).toHaveLength(0);
  expect(deleted).toHaveLength(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const response = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      new URL(r.url()).pathname === "/api/runs",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const saved = await (await response).json();
  expect(saved.attachments.map((item: { id: string }) => item.id)).toEqual([
    correct[0].id,
  ]);
  expect(
    saved.attachments.some((item: { id: string }) =>
      initial.some((old) => old.id === item.id),
    ),
  ).toBe(false);
  await expect(
    page.getByRole("status").filter({ hasText: "Completed" }),
  ).toHaveCount(1);
  await expect(page.locator(".answer .attachment-item strong")).toHaveText(
    "correct.png",
  );
  await expect(page.locator(".answer .attachment-remove")).toHaveCount(0);
  expect(generated).toHaveLength(1);
});

test("image version remains reachable below Privacy with long history and a short drawer", async ({
  page,
}, info) => {
  let tag = "9.8.7-rc.1";
  for (const routePath of ["**/api/auth/login", "**/api/auth/session"]) {
    await page.route(routePath, async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      await route.fulfill({
        response,
        json: data.owner_id ? { ...data, image_version: tag } : data,
      });
    });
  }
  await page.route("**/api/conversations?q=*", async (route) => {
    await route.fulfill({
      json: Array.from({ length: 60 }, (_, i) => ({
        id: `version-history-${i}`,
        title: `Long synthetic history ${i}`,
        created_at: 1,
        updated_at: 1,
      })),
    });
  });
  await signIn(page);
  const footer = page.getByLabel("Application version", { exact: true });
  const sidebar = page.getByRole("complementary", {
    name: "Navigation",
    exact: true,
  });
  const mobile = info.project.name !== "polish-desktop";
  if (mobile)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await footer.scrollIntoViewIfNeeded();
  await expect(footer).toBeInViewport();
  await expect(footer).toHaveText("labchatbot v9.8.7-rc.1");
  expect(
    await footer.evaluate(
      (node) => node.parentElement?.lastElementChild === node,
    ),
  ).toBe(true);
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.screenshot({
      path: `../artifacts/image-version-${info.project.name}-${scheme}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: mobile ? 360 : 1280, height: 450 });
  if (!mobile)
    await page.getByRole("button", { name: "Sign out", exact: true }).focus();
  await footer.scrollIntoViewIfNeeded();
  await expect(footer).toBeInViewport();
  expect(
    await sidebar.evaluate((node) => node.scrollWidth <= node.clientWidth),
  ).toBe(true);
  tag = "v9";
  await page.reload();
  if (mobile)
    await page.getByRole("button", { name: "Open navigation" }).click();
  await footer.scrollIntoViewIfNeeded();
  await expect(footer).toHaveText("labchatbot v9");
});
