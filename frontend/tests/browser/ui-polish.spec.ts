import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page
    .getByLabel("Owner passphrase")
    .fill("synthetic-browser-passphrase");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toBeVisible();
}

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
